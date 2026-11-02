"""Demo authentication, JWT token issuance, password hashing, and role-based access control."""

from __future__ import annotations

import os
import secrets
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal

import bcrypt
import jwt
from dotenv import load_dotenv
from fastapi import Depends, HTTPException, Request, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

# Load optional .env file from project root if present
load_dotenv(Path(__file__).resolve().parents[2] / ".env")

JWT_SECRET = os.environ.get("RESQ_JWT_SECRET") or secrets.token_hex(32)
JWT_ALGORITHM = "HS256"
JWT_EXPIRY_MINUTES = int(os.environ.get("RESQ_JWT_EXPIRY_MINUTES", "60"))

security_bearer = HTTPBearer(auto_error=False)

# In-memory rate limiting: ip -> list of failed attempt timestamps
_FAILED_LOGINS: dict[str, list[float]] = defaultdict(list)
RATE_LIMIT_WINDOW_SECONDS = 60
MAX_FAILED_ATTEMPTS = 5


class User(BaseModel):
    username: str
    role: Literal["viewer", "operator"]


class LoginRequest(BaseModel):
    username: str = Field(min_length=1)
    password: str = Field(min_length=1)


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: Literal["viewer", "operator"]
    username: str
    expires_in_seconds: int


# User store with hashed passwords only (never plaintext)
_USERS_DB: dict[str, dict[str, str]] = {}


def _init_users() -> None:
    """Initialize seed users with bcrypt hashed passwords read from environment or defaults."""
    if _USERS_DB:
        return
    viewer_pwd = os.environ.get("RESQ_VIEWER_PASSWORD", "viewer2026")
    operator_pwd = os.environ.get("RESQ_OPERATOR_PASSWORD", "operator2026")

    viewer_hash = bcrypt.hashpw(viewer_pwd.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    operator_hash = bcrypt.hashpw(operator_pwd.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    _USERS_DB["viewer"] = {
        "username": "viewer",
        "role": "viewer",
        "password_hash": viewer_hash,
    }
    _USERS_DB["operator"] = {
        "username": "operator",
        "role": "operator",
        "password_hash": operator_hash,
    }


def _verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
    except Exception:
        return False


def _check_rate_limit(client_ip: str) -> None:
    now = time.time()
    recent = [t for t in _FAILED_LOGINS[client_ip] if now - t < RATE_LIMIT_WINDOW_SECONDS]
    _FAILED_LOGINS[client_ip] = recent
    if len(recent) >= MAX_FAILED_ATTEMPTS:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"code": "rate_limited", "message": "Too many failed login attempts. Please wait 1 minute."},
        )


def _record_failed_attempt(client_ip: str) -> None:
    _FAILED_LOGINS[client_ip].append(time.time())


def _reset_failed_attempts(client_ip: str) -> None:
    _FAILED_LOGINS.pop(client_ip, None)


def reset_rate_limiter() -> None:
    """Clear all recorded rate limiting entries (for test suites)."""
    _FAILED_LOGINS.clear()


def create_access_token(username: str, role: str, expiry_minutes: int | None = None) -> str:
    minutes = expiry_minutes if expiry_minutes is not None else JWT_EXPIRY_MINUTES
    now = datetime.now(timezone.utc)
    expire = now + timedelta(minutes=minutes)
    payload = {
        "sub": username,
        "role": role,
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> User:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        username = payload.get("sub")
        role = payload.get("role")
        if not username or role not in ("viewer", "operator"):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"code": "invalid_token", "message": "Invalid token payload."},
            )
        return User(username=username, role=role)
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "token_expired", "message": "Session expired. Please log in again."},
        )
    except jwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "invalid_token", "message": "Invalid authentication token."},
        )


def authenticate_user(credentials: LoginRequest, client_ip: str) -> User:
    _init_users()
    _check_rate_limit(client_ip)

    user_record = _USERS_DB.get(credentials.username)
    if not user_record or not _verify_password(credentials.password, user_record["password_hash"]):
        _record_failed_attempt(client_ip)
        # Generic error message without revealing whether username or password was incorrect
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "invalid_credentials", "message": "Invalid username or password."},
        )

    _reset_failed_attempts(client_ip)
    return User(username=user_record["username"], role=user_record["role"])  # type: ignore[arg-type]


async def get_current_user(
    request: Request,
    bearer: HTTPAuthorizationCredentials | None = Depends(security_bearer),
) -> User:
    token: str | None = None
    if bearer and bearer.credentials:
        token = bearer.credentials
    elif "resq_session" in request.cookies:
        token = request.cookies.get("resq_session")

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "unauthorized", "message": "Authentication required. Please log in."},
        )

    return decode_access_token(token)


def require_role(allowed_role: Literal["viewer", "operator"]):
    def _dependency(user: User = Depends(get_current_user)) -> User:
        if allowed_role == "operator" and user.role != "operator":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"code": "forbidden", "message": "Operator role required for this action."},
            )
        return user

    return _dependency
