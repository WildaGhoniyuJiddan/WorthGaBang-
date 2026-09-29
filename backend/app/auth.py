"""Auth helpers for the WorthBang mobile API (B1).

- Passwords: bcrypt-hashed server-side only (never in the app).
- Tokens: JWT access (15 min) + refresh (7 days). Refresh tokens are also
  registered server-side (sha256 hash) so logout can revoke them.
"""
from __future__ import annotations

import hashlib
import hmac
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
import jwt
from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .db import get_db
from .models import RefreshToken, User, utcnow


# --- Password hashing -------------------------------------------------------

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except (ValueError, TypeError):
        return False


# --- JWT --------------------------------------------------------------------

def _jwt_settings():
    s = get_settings()
    return s.jwt_secret_key, s.jwt_algorithm


def create_access_token(user_id: int) -> str:
    secret, alg = _jwt_settings()
    now = utcnow()
    s = get_settings()
    payload = {
        "sub": str(user_id),
        "type": "access",
        "jti": uuid.uuid4().hex,
        "iat": now,
        "exp": now + timedelta(minutes=s.jwt_access_minutes),
    }
    return jwt.encode(payload, secret, algorithm=alg)


def create_refresh_token(user_id: int) -> str:
    secret, alg = _jwt_settings()
    now = utcnow()
    s = get_settings()
    payload = {
        "sub": str(user_id),
        "type": "refresh",
        "jti": uuid.uuid4().hex,
        "iat": now,
        "exp": now + timedelta(days=s.jwt_refresh_days),
    }
    return jwt.encode(payload, secret, algorithm=alg)


def decode_token(token: str, expected_type: str) -> int:
    """Return user_id or raise HTTPException(401)."""
    secret, alg = _jwt_settings()
    try:
        payload = jwt.decode(token, secret, algorithms=[alg])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")
    if payload.get("type") != expected_type or not payload.get("sub"):
        raise HTTPException(status_code=401, detail="Invalid token")
    return int(payload["sub"])


def refresh_token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def issue_token_pair(db: Session, user: User) -> tuple[str, str]:
    """Create access+refresh pair and register the refresh token server-side."""
    access = create_access_token(user.id)
    refresh = create_refresh_token(user.id)
    s = get_settings()
    db.add(
        RefreshToken(
            user_id=user.id,
            token_hash=refresh_token_hash(refresh),
            expires_at=utcnow() + timedelta(days=s.jwt_refresh_days),
        )
    )
    db.commit()
    return access, refresh


def revoke_refresh_token(db: Session, token: str) -> bool:
    row = db.scalar(
        select(RefreshToken).where(RefreshToken.token_hash == refresh_token_hash(token))
    )
    if row is None or row.revoked:
        return False
    row.revoked = True
    db.commit()
    return True


def revoke_all_user_tokens(db: Session, user_id: int) -> None:
    rows = db.scalars(
        select(RefreshToken).where(
            RefreshToken.user_id == user_id, RefreshToken.revoked.is_(False)
        )
    ).all()
    for row in rows:
        row.revoked = True
    db.commit()


def refresh_is_active(db: Session, token: str) -> bool:
    row = db.scalar(
        select(RefreshToken).where(RefreshToken.token_hash == refresh_token_hash(token))
    )
    if row is None or row.revoked:
        return False
    exp = row.expires_at
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    return exp > utcnow()


# --- Dependencies -----------------------------------------------------------

def _bearer_token(request: Request) -> Optional[str]:
    auth = request.headers.get("Authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip() or None
    return None


def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
) -> User:
    token = _bearer_token(request)
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    user_id = decode_token(token, "access")
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid token")
    return user


def get_optional_user(
    request: Request,
    db: Session = Depends(get_db),
) -> Optional[User]:
    """Like get_current_user but returns None instead of 401 (for additive logging)."""
    token = _bearer_token(request)
    if not token:
        return None
    try:
        user_id = decode_token(token, "access")
    except HTTPException:
        return None
    return db.get(User, user_id)


def sign_payload(payload: bytes) -> str:
    """HMAC signature for stateless tokens (game question ids)."""
    secret, _ = _jwt_settings()
    return hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
