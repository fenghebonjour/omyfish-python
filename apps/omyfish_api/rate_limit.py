"""Minimal per-IP sliding-window rate limiter for billing endpoints that call out to
Stripe. In-process only (fine for this app's single-instance deployment) — no Redis
dependency. Not applied to /billing/webhook/*, which is Stripe calling us, not a user.
"""
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request, status

WINDOW_SECONDS = 60
MAX_REQUESTS = 5

_hits: dict[str, deque] = defaultdict(deque)


def limit_by_ip(request: Request) -> None:
    ip = request.client.host if request.client else "unknown"
    now = time.monotonic()
    hits = _hits[ip]
    while hits and now - hits[0] > WINDOW_SECONDS:
        hits.popleft()
    if len(hits) >= MAX_REQUESTS:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS, "Too many requests — try again in a minute."
        )
    hits.append(now)


def reset_rate_limits() -> None:
    """Test-only: clear all tracked hits between tests."""
    _hits.clear()
