import hashlib
import os
import re
import secrets
import base64
from datetime import datetime, timedelta
from urllib.parse import urlencode

import httpx

SWIGGY_MCP_URLS = {
    "food": "https://mcp.swiggy.com/food",
    "im": "https://mcp.swiggy.com/im",
}

# Updated when production credentials arrive
CLIENT_ID = os.getenv("SWIGGY_CLIENT_ID", "mcp-remote")


def _generate_pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return verifier, challenge


async def _discover_oauth_server(server: str) -> dict:
    """Fetch OAuth 2.1 server metadata from the Swiggy MCP server."""
    async with httpx.AsyncClient(timeout=10) as client:
        # 1. Try root well-known endpoint
        for url in [
            "https://mcp.swiggy.com/.well-known/oauth-authorization-server",
            f"{SWIGGY_MCP_URLS[server]}/.well-known/oauth-authorization-server",
        ]:
            try:
                r = await client.get(url)
                if r.status_code == 200:
                    return r.json()
            except Exception:
                continue

        # 2. Make an unauthenticated MCP request; parse realm from 401 WWW-Authenticate
        try:
            r = await client.post(
                SWIGGY_MCP_URLS[server],
                json={
                    "jsonrpc": "2.0",
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {},
                        "clientInfo": {"name": "foodbudget", "version": "1.0"},
                    },
                    "id": 1,
                },
                headers={"Content-Type": "application/json"},
            )
            www_auth = r.headers.get("www-authenticate", "")
            realm_match = re.search(r'realm="([^"]+)"', www_auth)
            if realm_match:
                realm = realm_match.group(1).rstrip("/")
                meta_url = f"{realm}/.well-known/oauth-authorization-server"
                meta_r = await client.get(meta_url)
                if meta_r.status_code == 200:
                    return meta_r.json()
        except Exception:
            pass

    raise RuntimeError(f"Could not discover OAuth endpoints for Swiggy MCP '{server}'")


async def build_auth_url(server: str, callback_url: str) -> tuple[str, str, str]:
    """Return (auth_url, state, code_verifier) to kick off the OAuth flow."""
    meta = await _discover_oauth_server(server)
    auth_endpoint = meta["authorization_endpoint"]

    state = secrets.token_urlsafe(16)
    verifier, challenge = _generate_pkce_pair()

    params = {
        "response_type": "code",
        "client_id": CLIENT_ID,
        "redirect_uri": callback_url,
        "scope": "openid",
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }

    auth_url = f"{auth_endpoint}?{urlencode(params)}"
    return auth_url, state, verifier


async def exchange_code(
    server: str, code: str, verifier: str, callback_url: str
) -> tuple[str, datetime]:
    """Exchange authorization code for access token. Returns (token, expiry)."""
    meta = await _discover_oauth_server(server)
    token_endpoint = meta["token_endpoint"]

    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.post(
            token_endpoint,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": callback_url,
                "client_id": CLIENT_ID,
                "code_verifier": verifier,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        r.raise_for_status()
        data = r.json()

    access_token = data["access_token"]
    expires_in = data.get("expires_in", 432000)  # Swiggy tokens live 5 days
    expiry = datetime.utcnow() + timedelta(seconds=expires_in)
    return access_token, expiry
