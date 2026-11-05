"""Cross-cutting security helpers.

Provides the response security headers and a small in-memory, per-key
rate limiter used to protect the login and JSON API endpoints.
"""

import time
from collections import defaultdict, deque

from config import (
    RATE_LIMIT_ENABLED,
    SECURITY_HEADERS,
)


def client_ip(request):
    """Best-effort client IP, honouring a single proxy hop."""
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.remote_addr or "unknown"


def apply_security_headers(app):
    """Attach conservative security headers to every response."""
    if not SECURITY_HEADERS:
        return

    @app.after_request
    def _add_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' data:; "
            "style-src 'self' 'unsafe-inline'; "
            "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net",
        )
        return response


class RateLimiter:
    """Fixed-window rate limiter keyed by client IP, held in memory."""

    def __init__(self, limit, window_seconds=60):
        self.limit = limit
        self.window = window_seconds
        self._hits = defaultdict(deque)

    def allow(self, key):
        if not RATE_LIMIT_ENABLED or self.limit <= 0:
            return True
        now = time.time()
        bucket = self._hits[key]
        while bucket and bucket[0] <= now - self.window:
            bucket.popleft()
        if len(bucket) >= self.limit:
            return False
        bucket.append(now)
        return True
