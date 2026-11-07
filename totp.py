"""Time-based one-time passwords (RFC 6238) for account two-factor login.

Implemented with the standard library only, so no extra dependency is needed.
The shared secret is stored per user and the current code is derived from the
clock; authenticator apps (Google Authenticator, Authy, ...) accept the same
``otpauth://`` provisioning URI.
"""

import base64
import hashlib
import hmac
import secrets
import struct
import time
import urllib.parse

DIGITS = 6
PERIOD = 30
_SECRET_BYTES = 20


def generate_secret():
    """Return a new base32-encoded shared secret."""
    return base64.b32encode(secrets.token_bytes(_SECRET_BYTES)).decode("ascii").rstrip("=")


def _counter(at):
    return int(at // PERIOD)


def code_at(secret, at=None):
    """Return the 6-digit code for ``secret`` at time ``at`` (defaults to now)."""
    at = time.time() if at is None else at
    padding = "=" * (-len(secret) % 8)
    key = base64.b32decode(secret.upper() + padding)
    digest = hmac.new(key, struct.pack(">Q", _counter(at)), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    truncated = struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF
    return str(truncated % (10 ** DIGITS)).zfill(DIGITS)


def verify(secret, code, at=None, window=1):
    """Check ``code`` against the secret, allowing +/- ``window`` periods of drift."""
    if not secret or not code:
        return False
    code = code.strip()
    at = time.time() if at is None else at
    for step in range(-window, window + 1):
        if hmac.compare_digest(code_at(secret, at + step * PERIOD), code):
            return True
    return False


def provisioning_uri(secret, account, issuer="Student Grade Portal"):
    """Build the otpauth:// URI an authenticator app understands."""
    label = urllib.parse.quote(f"{issuer}:{account}")
    params = urllib.parse.urlencode({
        "secret": secret,
        "issuer": issuer,
        "digits": DIGITS,
        "period": PERIOD,
    })
    return f"otpauth://totp/{label}?{params}"
