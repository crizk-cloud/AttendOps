"""Admin management of app accounts (people who log into this web app)."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.deps import require_admin
from app.auth.passwords import hash_password
from app.auth.tokens import revoke_all_for_user
from app.db import get_db
from app.models import AppUser, Role
from app.schemas.auth import AppUserCreate, AppUserOut, AppUserUpdate

router = APIRouter(prefix="/api/app-users", tags=["app users"])


@router.get("", response_model=list[AppUserOut])
def list_users(_: AppUser = Depends(require_admin), db: Session = Depends(get_db)) -> list[AppUser]:
    return list(db.scalars(select(AppUser).order_by(AppUser.email)))


@router.post("", response_model=AppUserOut, status_code=status.HTTP_201_CREATED)
def create_user(body: AppUserCreate, _: AppUser = Depends(require_admin),
                db: Session = Depends(get_db)) -> AppUser:
    email = body.email.lower()
    if db.scalar(select(AppUser).where(func.lower(AppUser.email) == email)):
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists")
    user = AppUser(email=email, full_name=body.full_name, role=body.role,
                   password_hash=hash_password(body.password))
    db.add(user)
    db.commit()
    return user


def _active_admin_count(db: Session) -> int:
    return db.scalar(select(func.count()).select_from(AppUser)
                     .where(AppUser.role == Role.admin, AppUser.is_active.is_(True))) or 0


@router.patch("/{user_id}", response_model=AppUserOut)
def update_user(user_id: int, body: AppUserUpdate, admin: AppUser = Depends(require_admin),
                db: Session = Depends(get_db)) -> AppUser:
    user = db.get(AppUser, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    changes = body.model_dump(exclude_unset=True)
    loses_admin = user.role == Role.admin and user.is_active and (
        changes.get("role", Role.admin) != Role.admin or changes.get("is_active") is False)
    if loses_admin and _active_admin_count(db) <= 1:
        raise HTTPException(status.HTTP_409_CONFLICT, "Cannot remove the last active admin")
    if "full_name" in changes:
        user.full_name = body.full_name
    if body.role is not None:
        user.role = body.role
    if body.is_active is not None:
        user.is_active = body.is_active
    if body.password is not None:
        user.password_hash = hash_password(body.password)
    if body.password is not None or body.is_active is False:
        revoke_all_for_user(db, user.id)
    db.commit()
    return user
