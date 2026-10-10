"""FastAPI dependencies: current user and role checks."""

from collections.abc import Callable

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.auth.tokens import ACCESS, TokenError, decode
from app.db import get_db
from app.models import AppUser, Role

_bearer = HTTPBearer(auto_error=False)


def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> AppUser:
    unauthorized = HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated",
                                 headers={"WWW-Authenticate": "Bearer"})
    if creds is None:
        raise unauthorized
    try:
        claims = decode(creds.credentials, ACCESS)
    except TokenError:
        raise unauthorized from None
    user = db.get(AppUser, int(claims["sub"]))
    # Role is re-read from the DB on every request, so demotions take effect immediately.
    if user is None or not user.is_active:
        raise unauthorized
    return user


def require_role(minimum: Role) -> Callable[..., AppUser]:
    def checker(user: AppUser = Depends(get_current_user)) -> AppUser:
        if not user.role.at_least(minimum):
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"Requires role '{minimum.value}' or higher")
        return user

    return checker


require_viewer = require_role(Role.viewer)
require_operator = require_role(Role.operator)
require_admin = require_role(Role.admin)
