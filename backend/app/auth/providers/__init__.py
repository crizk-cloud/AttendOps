from app.auth.providers.base import AuthProvider, AuthResult
from app.auth.providers.local import LocalPasswordProvider

__all__ = ["AuthProvider", "AuthResult", "LocalPasswordProvider", "get_provider"]

_PROVIDERS: dict[str, AuthProvider] = {LocalPasswordProvider.name: LocalPasswordProvider()}


def get_provider(name: str) -> AuthProvider | None:
    return _PROVIDERS.get(name)
