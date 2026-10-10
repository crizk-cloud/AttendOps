"""Encryption of device credentials at rest (Fernet = AES-128-CBC + HMAC-SHA256).

Ciphertext lives in the database; the key lives only in DEVICE_CREDENTIALS_KEY.
Decrypted values must never be logged or returned by the API.
"""

from cryptography.fernet import Fernet, InvalidToken

from app.config import get_settings


class CredentialDecryptError(Exception):
    """Ciphertext could not be decrypted (wrong key or tampered data)."""


def _fernet() -> Fernet:
    return Fernet(get_settings().device_credentials_key.get_secret_value().encode())


def encrypt_secret(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt_secret(ciphertext: str) -> str:
    try:
        return _fernet().decrypt(ciphertext.encode()).decode()
    except InvalidToken as exc:
        raise CredentialDecryptError(
            "cannot decrypt stored credential; check DEVICE_CREDENTIALS_KEY") from exc
