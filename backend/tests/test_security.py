from datetime import UTC, datetime

import pytest
from cryptography.fernet import Fernet
from pydantic import ValidationError

from app.auth.passwords import hash_password, verify_password
from app.config import Settings
from app.models import Role
from app.security import crypto
from app.timeutil import to_local


def test_credential_encryption_round_trip():
    token = crypto.encrypt_secret("dahua-pass")
    assert "dahua-pass" not in token
    assert crypto.decrypt_secret(token) == "dahua-pass"


def test_credential_decrypt_with_wrong_key_fails(monkeypatch):
    token = crypto.encrypt_secret("dahua-pass")
    other = Fernet(Fernet.generate_key())
    monkeypatch.setattr(crypto, "_fernet", lambda: other)
    with pytest.raises(crypto.CredentialDecryptError):
        crypto.decrypt_secret(token)


def test_password_hashing():
    h = hash_password("a-long-password")
    assert h.startswith("$argon2id$")
    assert verify_password("a-long-password", h)
    assert not verify_password("wrong-password", h)
    assert not verify_password("anything", None)


def test_role_hierarchy():
    assert Role.admin.at_least(Role.operator)
    assert Role.operator.at_least(Role.viewer)
    assert not Role.viewer.at_least(Role.operator)


@pytest.mark.parametrize("field,value", [("JWT_SECRET", "short"), ("DEVICE_CREDENTIALS_KEY", "not-a-key"),
                                         ("APP_TIMEZONE", "Mars/Olympus")])
def test_settings_reject_bad_values(monkeypatch, field, value):
    monkeypatch.setenv(field, value)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_beirut_time_conversion_handles_dst():
    winter = to_local(datetime(2026, 1, 15, 12, 0, tzinfo=UTC))
    summer = to_local(datetime(2026, 7, 15, 12, 0, tzinfo=UTC))
    assert (winter.hour, str(winter.tzinfo)) == (14, "Asia/Beirut")  # UTC+2
    assert summer.hour == 15  # UTC+3 (daylight saving)
    with pytest.raises(ValueError):
        to_local(datetime(2026, 1, 1))
