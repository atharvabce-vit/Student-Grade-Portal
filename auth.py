"""Login, login lockout and permission checks.

Passwords are verified against PBKDF2 hashes stored in the database. Repeated
failures for the same username trigger a temporary lockout that is persisted in
the database, so it survives restarts and is shared across worker processes.
"""

import time

from config import LOGIN_LOCKOUT_SECONDS, LOGIN_MAX_ATTEMPTS, PERMISSIONS
from database import clear_login_attempt, get_login_attempt, save_login_attempt
from users import find_user, verify_password


def lockout_remaining(username):
    """Seconds left on a lockout for this username (0 when not locked)."""
    _failures, locked_until = get_login_attempt(username)
    remaining = int(locked_until - time.time())
    return remaining if remaining > 0 else 0


def register_failure(username):
    failures, locked_until = get_login_attempt(username)
    failures += 1
    if failures >= LOGIN_MAX_ATTEMPTS:
        locked_until = time.time() + LOGIN_LOCKOUT_SECONDS
        failures = 0
    save_login_attempt(username, failures, locked_until)


def clear_failures(username):
    clear_login_attempt(username)


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
