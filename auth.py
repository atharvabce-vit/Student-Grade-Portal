"""Login, login lockout and permission checks.

Passwords are verified against PBKDF2 hashes stored in the database. Repeated
failures for the same username trigger a temporary lockout.
"""

import threading
import time

from config import LOGIN_LOCKOUT_SECONDS, LOGIN_MAX_ATTEMPTS, PERMISSIONS
from users import find_user, verify_password

_failures = {}
_lock = threading.Lock()


def lockout_remaining(username):
    """Seconds left on a lockout for this username (0 when not locked)."""
    with _lock:
        entry = _failures.get(username)
        if entry is None:
            return 0
        remaining = int(entry["until"] - time.time())
        if remaining <= 0:
            _failures.pop(username, None)
            return 0
        return remaining


def register_failure(username):
    with _lock:
        entry = _failures.get(username, {"count": 0, "until": 0})
        entry["count"] += 1
        if entry["count"] >= LOGIN_MAX_ATTEMPTS:
            entry["until"] = time.time() + LOGIN_LOCKOUT_SECONDS
            entry["count"] = 0
        _failures[username] = entry


def clear_failures(username):
    with _lock:
        _failures.pop(username, None)


def login(username, password):
    """Return the user's role on success, otherwise None."""
    if lockout_remaining(username) > 0:
        return None

    user = find_user(username)
    if user is not None and user["is_active"] and verify_password(user["password_hash"], password):
        clear_failures(username)
        return user["role"]

    register_failure(username)
    return None


def can(role, action):
    return action in PERMISSIONS.get(role, [])
