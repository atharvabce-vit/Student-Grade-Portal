import hashlib

from config import PASSWORD_SALT, PERMISSIONS, USERS


def hash_password(password):
    return hashlib.sha256((PASSWORD_SALT + password).encode()).hexdigest()


def login(username, password):
    user = USERS.get(username)
    if user is not None and user["password"] == hash_password(password):
        return user["role"]
    return None


def can(role, action):
    return action in PERMISSIONS.get(role, [])
