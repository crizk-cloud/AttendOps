"""JWT access tokens (short-lived, stateless) and refresh tokens (long-lived, tracked in the DB).

Refresh tokens rotate on every use. Re-using an already-rotated refresh token is treated as theft:
the whole token family is revoked and the user must log in again.
"""

import uuid
from dataclasses import dataclass
from datetime import timedelta

import jwt
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import AppUser, RefreshToken
from app.timeutil import utcnow

ACCESS = "access"
REFRESH = "refresh"


class TokenError(Exception):
    pass


@dataclass
class TokenPair:
    access_token: str
    refresh_token: str
    access_expires_in: int  # seconds
    refresh_expires_in: int  # seconds


def _encode(claims: dict) -> str:
    s = get_settings()
    return jwt.encode(claims, s.jwt_secret.get_secret_value(), algorithm=s.jwt_algorithm)


def decode(token: str, expected_type: str) -> dict:
    s = get_settings()
    try:
        claims = jwt.decode(token, s.jwt_secret.get_secret_value(), algorithms=[s.jwt_algorithm],
                            options={"require": ["exp", "iat", "sub", "typ"]})
    except jwt.PyJWTError as exc:
        raise TokenError(str(exc)) from exc
    if claims.get("typ") != expected_type:
        raise TokenError("wrong token type")
    return claims


def issue_tokens(db: Session, user: AppUser, family_id: uuid.UUID | None = None) -> TokenPair:
    s = get_settings()
    now = utcnow()
    access_ttl = timedelta(minutes=s.access_token_minutes)
    refresh_ttl = timedelta(days=s.refresh_token_days)
    access = _encode({"sub": str(user.id), "role": user.role.value, "typ": ACCESS,
                      "iat": now, "exp": now + access_ttl})
    jti = uuid.uuid4()
    family_id = family_id or uuid.uuid4()
    refresh = _encode({"sub": str(user.id), "typ": REFRESH, "jti": str(jti), "fam": str(family_id),
                       "iat": now, "exp": now + refresh_ttl})
    db.add(RefreshToken(jti=jti, user_id=user.id, family_id=family_id, issued_at=now,
                        expires_at=now + refresh_ttl))
    return TokenPair(access, refresh, int(access_ttl.total_seconds()), int(refresh_ttl.total_seconds()))


def rotate_refresh_token(db: Session, token: str) -> tuple[AppUser, TokenPair]:
    claims = decode(token, REFRESH)
    jti = uuid.UUID(claims["jti"])
    record = db.get(RefreshToken, jti, with_for_update=True)
    if record is None:
        raise TokenError("unknown refresh token")
    if record.revoked_at is not None:
        # Reuse of a rotated/revoked token: assume it was stolen and kill the family.
        revoke_family(db, record.family_id)
        db.commit()
        raise TokenError("refresh token reuse detected")
    user = record.user
    if not user.is_active:
        raise TokenError("account disabled")
    pair = issue_tokens(db, user, family_id=record.family_id)
    new_claims = decode(pair.refresh_token, REFRESH)
    record.revoked_at = utcnow()
    record.replaced_by = uuid.UUID(new_claims["jti"])
    return user, pair


def revoke_refresh_token(db: Session, token: str) -> None:
    try:
        claims = decode(token, REFRESH)
    except TokenError:
        return
    record = db.get(RefreshToken, uuid.UUID(claims["jti"]))
    if record is not None:
        revoke_family(db, record.family_id)


def revoke_family(db: Session, family_id: uuid.UUID) -> None:
    db.execute(update(RefreshToken)
               .where(RefreshToken.family_id == family_id, RefreshToken.revoked_at.is_(None))
               .values(revoked_at=utcnow()))


def revoke_all_for_user(db: Session, user_id: int) -> None:
    db.execute(update(RefreshToken)
               .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
               .values(revoked_at=utcnow()))


def purge_expired(db: Session) -> int:
    rows = db.scalars(select(RefreshToken).where(RefreshToken.expires_at < utcnow())).all()
    for r in rows:
        db.delete(r)
    return len(rows)
