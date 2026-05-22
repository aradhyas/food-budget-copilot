from datetime import datetime
from sqlalchemy.orm import Session
from app.models import User


class UserRepository:

    @staticmethod
    def get_by_whatsapp(db: Session, whatsapp_number: str) -> User | None:
        return db.query(User).filter(User.whatsapp_number == whatsapp_number).first()

    @staticmethod
    def get_by_id(db: Session, user_id: int) -> User | None:
        return db.query(User).filter(User.id == user_id).first()

    @staticmethod
    def create(db: Session, whatsapp_number: str) -> User:
        user = User(whatsapp_number=whatsapp_number, setup_step="new")
        db.add(user)
        db.commit()
        db.refresh(user)
        return user

    @staticmethod
    def set_oauth_pending(db: Session, user: User, server: str, state: str, verifier: str) -> User:
        user.oauth_pending_server = server
        user.oauth_state = state
        user.oauth_code_verifier = verifier
        user.setup_step = f"{server}_auth_sent"
        db.commit()
        db.refresh(user)
        return user

    @staticmethod
    def save_token(
        db: Session,
        user: User,
        server: str,
        access_token: str,
        expiry: datetime,
    ) -> User:
        if server == "food":
            user.food_access_token = access_token
            user.food_token_expiry = expiry
        else:
            user.im_access_token = access_token
            user.im_token_expiry = expiry

        user.oauth_state = None
        user.oauth_code_verifier = None
        user.oauth_pending_server = None

        # Advance setup step
        if server == "food":
            user.setup_step = "im_auth_pending"
        elif server == "im" and user.food_access_token:
            user.setup_step = "budget_pending"

        db.commit()
        db.refresh(user)
        return user

    @staticmethod
    def set_active(db: Session, user: User) -> User:
        user.setup_step = "active"
        db.commit()
        db.refresh(user)
        return user

    @staticmethod
    def get_by_oauth_state(db: Session, state: str) -> User | None:
        return db.query(User).filter(User.oauth_state == state).first()
