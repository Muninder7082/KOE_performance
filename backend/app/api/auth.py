from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from ..clock import now_utc
from ..db import get_session
from ..models import User
from ..ratelimit import client_ip, limiter
from ..repositories import UserRepository
from ..schemas import LoginIn, PasswordChange, UserOut
from ..security import (clear_session, current_user, dummy_verify, hash_password, issue_session,
                        validate_password_strength, verify_password)

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login")
async def login(body: LoginIn, request: Request, response: Response, session: AsyncSession = Depends(get_session)):
    ip = client_ip(request)
    limiter.hit(f"login-ip:{ip}", 10, 300)
    limiter.hit(f"login-email:{body.email.lower()}", 10, 900)
    user = await UserRepository(session).by_email(body.email)
    if user is None:
        dummy_verify()
        raise HTTPException(401, "Invalid e-mail or password")
    if not verify_password(body.password, user.password_hash) or not user.is_active:
        raise HTTPException(401, "Invalid e-mail or password")
    user.last_login_at = now_utc()
    await session.commit()
    csrf = issue_session(response, user)
    return {"user": UserOut.model_validate(user), "csrf_token": csrf}


@router.post("/logout")
async def logout(response: Response, user: User = Depends(current_user)):
    clear_session(response)
    return {"ok": True}


@router.get("/me")
async def me(request: Request, user: User = Depends(current_user)):
    return {"user": UserOut.model_validate(user), "csrf_token": request.state.csrf}


@router.post("/change-password")
async def change_password(body: PasswordChange, request: Request, response: Response,
                          user: User = Depends(current_user), session: AsyncSession = Depends(get_session)):
    limiter.hit(f"pwchange:{user.id}", 5, 900)
    db_user = await session.get(User, user.id)
    assert db_user is not None
    if not verify_password(body.current_password, db_user.password_hash):
        raise HTTPException(400, "Current password is incorrect")
    validate_password_strength(body.new_password)
    db_user.password_hash = hash_password(body.new_password)
    db_user.session_version += 1  # revoke other sessions
    await session.commit()
    csrf = issue_session(response, db_user)
    return {"ok": True, "csrf_token": csrf}
