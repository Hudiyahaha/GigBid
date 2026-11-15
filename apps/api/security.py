"""Password hashing (bcrypt) and session tokens (JWT, HS256). Tokens/passwords are never logged."""

from __future__ import annotations

import os
import time
import uuid

import bcrypt
import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from apps.api.db import User, session

_bearer = HTTPBearer(auto_error=False)


def _secret() -> str:
    return os.getenv("APP_SECRET_KEY") or "dev-only-secret-change-me"


def hash_pw(pw: str) -> str:
    return bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()


def check_pw(pw: str, h: str) -> bool:
    try:
        return bcrypt.checkpw(pw.encode(), h.encode())
    except ValueError:
        return False


def issue(user_id: str, hours: int = 72) -> str:
    return jwt.encode({"sub": user_id, "exp": int(time.time()) + hours * 3600, "jti": uuid.uuid4().hex}, _secret(), "HS256")


def current_user(cred: HTTPAuthorizationCredentials | None = Depends(_bearer)) -> User:
    if not cred:
        raise HTTPException(401, "not signed in")
    try:
        sub = jwt.decode(cred.credentials, _secret(), algorithms=["HS256"])["sub"]
    except jwt.PyJWTError as e:
        raise HTTPException(401, "invalid session") from e
    with session() as s:
        u = s.get(User, sub)
    if not u:
        raise HTTPException(401, "unknown user")
    return u
