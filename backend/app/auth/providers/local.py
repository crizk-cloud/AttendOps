from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.passwords import hash_password, needs_rehash, verify_password
from app.auth.providers.base import AuthResult
from app.models import AppUser

INVALID = "Invalid email or password"


class LocalPasswordProvider:
    name = "local"

    def authenticate(self, db: Session, credentials: dict[str, Any]) -> AuthResult:
        email = str(credentials.get("email", "")).strip().lower()
        password = str(credentials.get("password", ""))
        user = db.scalar(select(AppUser).where(func.lower(AppUser.email) == email))
        # Always run a verification so missing users take as long as wrong passwords.
        ok = verify_password(password, user.password_hash if user else None)
        if not user or not ok:
            return AuthResult(None, INVALID)
        if not user.is_active:
            return AuthResult(None, "Account is disabled")
        if needs_rehash(user.password_hash):
            user.password_hash = hash_password(password)
        return AuthResult(user)
