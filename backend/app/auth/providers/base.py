"""Authentication provider interface.

A provider only answers "who is this person?" and returns an existing, active AppUser.
Token issuing, roles and sessions are shared by all providers. A future Google provider
would verify a Google ID token and look the user up by verified email; it would not
auto-create accounts unless that is explicitly decided.
"""

from dataclasses import dataclass
from typing import Any, Protocol

from sqlalchemy.orm import Session

from app.models import AppUser


@dataclass
class AuthResult:
    user: AppUser | None
    error: str | None = None


class AuthProvider(Protocol):
    name: str

    def authenticate(self, db: Session, credentials: dict[str, Any]) -> AuthResult: ...
