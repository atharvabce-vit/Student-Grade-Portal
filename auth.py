from config import PERMISSIONS, USERS


def login(username, password):
    user = USERS.get(username)
    if user is not None and user["password"] == password:
        return user["role"]
    return None


def can(role, action):
    return action in PERMISSIONS.get(role, [])
