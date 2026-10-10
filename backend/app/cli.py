"""Admin command line.

    python -m app.cli create-admin --email you@example.com      # prompts for the password
    python -m app.cli generate-keys     # prints a fresh JWT_SECRET and DEVICE_CREDENTIALS_KEY
"""

import argparse
import getpass
import os
import secrets
import sys

from cryptography.fernet import Fernet
from sqlalchemy import func, select


def create_admin(email: str) -> int:
    from app.auth.passwords import MIN_PASSWORD_LENGTH, hash_password
    from app.db import get_sessionmaker
    from app.models import AppUser, Role

    email = email.strip().lower()
    password = os.environ.get("ATTENDOPS_ADMIN_PASSWORD") or getpass.getpass("New admin password: ")
    if len(password) < MIN_PASSWORD_LENGTH:
        print(f"Password must be at least {MIN_PASSWORD_LENGTH} characters", file=sys.stderr)
        return 1
    with get_sessionmaker()() as db:
        user = db.scalar(select(AppUser).where(func.lower(AppUser.email) == email))
        if user:
            print(f"Account {email} already exists; promoting to admin and resetting its password.")
            user.role, user.is_active = Role.admin, True
            user.password_hash = hash_password(password)
        else:
            db.add(AppUser(email=email, role=Role.admin, password_hash=hash_password(password)))
            print(f"Created admin {email}.")
        db.commit()
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(prog="python -m app.cli")
    sub = ap.add_subparsers(dest="cmd", required=True)
    ca = sub.add_parser("create-admin")
    ca.add_argument("--email", required=True)
    sub.add_parser("generate-keys")
    args = ap.parse_args()
    if args.cmd == "create-admin":
        return create_admin(args.email)
    print(f"JWT_SECRET={secrets.token_urlsafe(48)}")
    print(f"DEVICE_CREDENTIALS_KEY={Fernet.generate_key().decode()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
