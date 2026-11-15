"""Encrypted per-user token store (A4, E4). Tokens are Fernet-encrypted with TOKEN_ENCRYPTION_KEY, never
logged and never returned to the browser."""

from __future__ import annotations

import base64
import hashlib
import json
import os

from cryptography.fernet import Fernet
from sqlalchemy import select

from apps.api.db import OAuthToken, session


def _fernet() -> Fernet:
    key = os.getenv("TOKEN_ENCRYPTION_KEY")
    if not key:  # derive a stable dev key; production must set TOKEN_ENCRYPTION_KEY
        seed = (os.getenv("APP_SECRET_KEY") or "dev-only-secret").encode()
        key = base64.urlsafe_b64encode(hashlib.sha256(seed).digest()).decode()
    return Fernet(key.encode())


def put(user_id: str, provider: str, data: dict) -> None:
    ct = _fernet().encrypt(json.dumps(data).encode()).decode()
    with session() as s:
        row = s.execute(select(OAuthToken).where(OAuthToken.user_id == user_id, OAuthToken.provider == provider)).scalar_one_or_none()
        if row:
            row.ciphertext = ct
        else:
            s.add(OAuthToken(user_id=user_id, provider=provider, ciphertext=ct))


def get(user_id: str, provider: str) -> dict | None:
    with session() as s:
        row = s.execute(select(OAuthToken).where(OAuthToken.user_id == user_id, OAuthToken.provider == provider)).scalar_one_or_none()
        return json.loads(_fernet().decrypt(row.ciphertext.encode())) if row else None


def delete(user_id: str, provider: str) -> None:
    with session() as s:
        row = s.execute(select(OAuthToken).where(OAuthToken.user_id == user_id, OAuthToken.provider == provider)).scalar_one_or_none()
        if row:
            s.delete(row)


def connected(user_id: str) -> list[str]:
    with session() as s:
        return [r.provider for r in s.execute(select(OAuthToken).where(OAuthToken.user_id == user_id)).scalars()]
