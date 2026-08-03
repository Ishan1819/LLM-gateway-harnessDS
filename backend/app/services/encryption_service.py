"""Fernet encryption for client-supplied provider API keys.

Keys are written encrypted and only ever decrypted in-process, at the moment a
request is forwarded upstream. They are never returned by any API route.
"""

from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from app.config import settings


def _build_fernet() -> Fernet:
    key = (settings.ENCRYPTION_KEY or "").strip()
    if not key:
        raise RuntimeError(
            "ENCRYPTION_KEY is not set. Generate one with:\n"
            '  python -c "from cryptography.fernet import Fernet; '
            'print(Fernet.generate_key().decode())"'
        )
    try:
        return Fernet(key.encode())
    except (ValueError, TypeError):
        # Accept a plain passphrase too, so a misconfigured deploy still boots
        # deterministically instead of crashing at request time.
        derived = base64.urlsafe_b64encode(hashlib.sha256(key.encode()).digest())
        return Fernet(derived)


_fernet: Fernet | None = None


def _fernet_instance() -> Fernet:
    global _fernet
    if _fernet is None:
        _fernet = _build_fernet()
    return _fernet


def encrypt(plaintext: str) -> str:
    return _fernet_instance().encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str:
    try:
        return _fernet_instance().decrypt(ciphertext.encode()).decode()
    except InvalidToken as exc:
        raise ValueError(
            "Stored API key could not be decrypted. The ENCRYPTION_KEY likely "
            "changed since the key was saved — re-enter it in Settings."
        ) from exc


def mask(plaintext: str) -> str:
    """Display form for the dashboard: sk-...a1b2."""
    if not plaintext:
        return ""
    if len(plaintext) <= 8:
        return "•" * len(plaintext)
    return f"{plaintext[:3]}...{plaintext[-4:]}"
