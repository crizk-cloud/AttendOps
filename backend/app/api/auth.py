"""Login, token refresh, logout, current user.

The access token is returned in the JSON body (the frontend keeps it in memory only).
The refresh token is set as an httpOnly cookie scoped to /api/auth, so page scripts can't read it.
"""

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.auth.deps import get_current_user
from app.auth.passwords import hash_password, verify_password
from app.auth.providers import get_provider
from app.auth.tokens import (
    TokenError,
    TokenPair,
    issue_tokens,
    revoke_all_for_user,
    revoke_refresh_token,
    rotate_refresh_token,
)
from app.config import get_settings
from app.db import get_db
from app.models import AppUser
from app.schemas.auth import AppUserOut, LoginRequest, PasswordChange, TokenResponse
from app.timeutil import utcnow

router = APIRouter(prefix="/api/auth", tags=["auth"])

REFRESH_COOKIE = "attendops_refresh"
COOKIE_PATH = "/api/auth"


def _set_refresh_cookie(response: Response, pair: TokenPair) -> None:
    response.set_cookie(
        REFRESH_COOKIE, pair.refresh_token, max_age=pair.refresh_expires_in, path=COOKIE_PATH,
        httponly=True, samesite="strict", secure=get_settings().cookie_secure,
    )


def _token_response(response: Response, pair: TokenPair) -> TokenResponse:
    _set_refresh_cookie(response, pair)
    response.headers["Cache-Control"] = "no-store"
    return TokenResponse(access_token=pair.access_token, expires_in=pair.access_expires_in)


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, response: Response, db: Session = Depends(get_db)) -> TokenResponse:
    result = get_provider("local").authenticate(db, body.model_dump())
    if result.user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, result.error or "Login failed")
    result.user.last_login_at = utcnow()
    pair = issue_tokens(db, result.user)
    db.commit()
    return _token_response(response, pair)


@router.post("/refresh", response_model=TokenResponse)
def refresh(response: Response, db: Session = Depends(get_db),
            token: str | None = Cookie(default=None, alias=REFRESH_COOKIE)) -> TokenResponse:
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "No refresh token")
    try:
        _, pair = rotate_refresh_token(db, token)
    except TokenError:
        response.delete_cookie(REFRESH_COOKIE, path=COOKIE_PATH)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session expired, please log in again") from None
    db.commit()
    return _token_response(response, pair)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(request: Request, response: Response, db: Session = Depends(get_db)) -> Response:
    token = request.cookies.get(REFRESH_COOKIE)
    if token:
        revoke_refresh_token(db, token)
        db.commit()
    response.status_code = status.HTTP_204_NO_CONTENT
    response.delete_cookie(REFRESH_COOKIE, path=COOKIE_PATH)
    return response


@router.get("/me", response_model=AppUserOut)
def me(user: AppUser = Depends(get_current_user)) -> AppUser:
    return user


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(body: PasswordChange, response: Response, user: AppUser = Depends(get_current_user),
                    db: Session = Depends(get_db)) -> Response:
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Current password is incorrect")
    user.password_hash = hash_password(body.new_password)
    revoke_all_for_user(db, user.id)  # sign out other sessions
    db.commit()
    response.status_code = status.HTTP_204_NO_CONTENT
    response.delete_cookie(REFRESH_COOKIE, path=COOKIE_PATH)
    return response
