"""Authentication, authorization and CSRF.

* Passwords: bcrypt.
* Session: signed JWT in an HttpOnly cookie. The token carries the user's
  session_version so password changes / deactivation revoke old sessions.
* CSRF: the JWT also carries a random CSRF token. Every state-changing request
  must echo it in the X-CSRF-Token header (a cross-site page cannot read it).
* Scheduler endpoint: separate bearer token compared in constant time.
"""
from __future__ import annotations

import hmac
import secrets
from datetime import timedelta

import bcrypt
import jwt
from fastapi import Depends, HTTPException, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from .clock import now_utc
from .config import get_settings
from .db import get_session
from .models import User

SESSION_COOKIE = "pt_session"
CSRF_HEADER = "X-CSRF-Token"
_ALGO = "HS256"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("ascii")


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("ascii"))
    except ValueError:
        return False


# A real hash used to equalise timing when the e-mail does not exist.
_DUMMY_HASH = bcrypt.hashpw(b"timing-equaliser", bcrypt.gensalt(rounds=12)).decode("ascii")


def dummy_verify() -> None:
    verify_password("not-the-password", _DUMMY_HASH)


def validate_password_strength(password: str) -> None:
    if len(password) < 10:
        raise HTTPException(422, "Password must be at least 10 characters long")
    if len(password.encode("utf-8")) > 72:
        raise HTTPException(422, "Password must be at most 72 bytes")


def issue_session(response: Response, user: User) -> str:
    settings = get_settings()
    csrf = secrets.token_urlsafe(32)
    now = now_utc()
    token = jwt.encode(
        {
            "sub": str(user.id),
            "ver": user.session_version,
            "csrf": csrf,
            "exp": int((now + timedelta(hours=settings.session_hours)).timestamp()),
        },
        settings.secret_key,
        algorithm=_ALGO,
    )
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=settings.session_hours * 3600,
        httponly=True,
        secure=settings.cookie_secure or settings.cookie_samesite == "none",
        samesite=settings.cookie_samesite,
        path="/",
        partitioned=settings.cookie_samesite == "none",  # CHIPS: lets the cookie work inside the HF iframe
    )
    return csrf


def clear_session(response: Response) -> None:
    settings = get_settings()
    response.delete_cookie(
        SESSION_COOKIE,
        path="/",
        secure=settings.cookie_secure or settings.cookie_samesite == "none",
        httponly=True,
        samesite=settings.cookie_samesite,
    )


def _decode(token: str) -> dict | None:
    try:
        claims = jwt.decode(token, get_settings().secret_key, algorithms=[_ALGO],
                            options={"require": ["exp", "sub"], "verify_exp": False})
    except jwt.PyJWTError:
        return None
    # Expiry is checked against the application clock (same source that issued it).
    if not isinstance(claims.get("exp"), (int, float)) or claims["exp"] < now_utc().timestamp():
        return None
    return claims


async def current_user(request: Request, session: AsyncSession = Depends(get_session)) -> User:
    token = request.cookies.get(SESSION_COOKIE)
    claims = _decode(token) if token else None
    if not claims:
        raise HTTPException(401, "Not authenticated")
    try:
        user_id = int(claims["sub"])
    except (KeyError, ValueError):
        raise HTTPException(401, "Not authenticated") from None
    user = await session.get(User, user_id)
    if user is None or not user.is_active or user.session_version != claims.get("ver"):
        raise HTTPException(401, "Session expired. Please sign in again.")
    if request.method not in SAFE_METHODS:
        sent = request.headers.get(CSRF_HEADER, "")
        expected = str(claims.get("csrf", ""))
        if not sent or not expected or not hmac.compare_digest(sent, expected):
            raise HTTPException(403, "CSRF token missing or invalid")
    request.state.csrf = claims.get("csrf")
    return user


async def require_admin(user: User = Depends(current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(403, "Administrator access required")
    return user


def verify_scheduler_token(request: Request) -> None:
    expected = get_settings().scheduler_token
    # X-Scheduler-Token wins so that, on a private Space, Authorization can carry the Hugging Face token.
    supplied = request.headers.get("X-Scheduler-Token", "").strip()
    if not supplied:
        auth = request.headers.get("Authorization", "")
        supplied = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
    if not supplied or not expected or not hmac.compare_digest(supplied.encode(), expected.encode()):
        raise HTTPException(401, "Invalid scheduler token")
