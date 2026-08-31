"""Lightweight, dependency-free security hardening for the API.

- SecurityHeadersMiddleware: sets HSTS, X-Content-Type-Options, X-Frame-Options,
  Referrer-Policy, and a restrictive CSP (no inline scripts needed by the API).
- RateLimitMiddleware: per-client-IP sliding-window limiter (in-memory).
- require_job_token: dependency that FAILS CLOSED — job endpoints are never
  reachable without a valid JOB_TOKEN, even if the env var is unset.

ponytail: the in-memory limiter is per-serverless-instance, so it only
dampens single-instance bursts. For distributed limiting on Vercel, swap to
Upstash Ratelimit (edge KV) — upgrade path noted, not added to keep deps zero.
"""
from __future__ import annotations

import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request, Security
from fastapi.responses import JSONResponse
from fastapi.security import APIKeyHeader
from starlette.middleware.base import BaseHTTPMiddleware

from .config import get_settings

# --- Security headers -------------------------------------------------------

SECURITY_HEADERS = {
    "Strict-Transport-Security": "max-age=63072000; includeSubDomains; preload",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
    "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
}


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        for k, v in SECURITY_HEADERS.items():
            response.headers.setdefault(k, v)
        return response


# --- Rate limiting ----------------------------------------------------------

_RATE_WINDOW_SECONDS = 60
_DEFAULT_LIMIT = 120  # requests / minute / IP (read-heavy frontend + API usage)


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, limit_per_minute: int = _DEFAULT_LIMIT):
        super().__init__(app)
        self.limit = limit_per_minute
        self._hits: defaultdict[str, deque] = defaultdict(deque)

    def _client_ip(self, request: Request) -> str:
        fwd = request.headers.get("x-forwarded-for")
        if fwd:
            return fwd.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    async def dispatch(self, request: Request, call_next):
        now = time.time()
        ip = self._client_ip(request)
        window = self._hits[ip]
        # drop timestamps outside the window
        while window and window[0] <= now - _RATE_WINDOW_SECONDS:
            window.popleft()
        if len(window) >= self.limit:
            retry = int(window[0] + _RATE_WINDOW_SECONDS - now) + 1
            return JSONResponse(
                status_code=429,
                content={"detail": "Too many requests. Slow down."},
                headers={"Retry-After": str(retry)},
            )
        window.append(now)
        return await call_next(request)


# --- Job token (fail-closed) ------------------------------------------------

_JOB_HEADER = APIKeyHeader(name="X-Job-Token", auto_error=False)


def require_job_token(token: str | None = Security(_JOB_HEADER)) -> str:
    """Reject job endpoints unless a correct JOB_TOKEN is presented.

    Unlike the previous `if token and ...` guard, this NEVER opens the
    endpoint when JOB_TOKEN is unset — fail closed.
    """
    expected = get_settings().internal_job_token
    if not expected or token != expected:
        raise HTTPException(status_code=401, detail="Invalid or missing job token")
    return token
