"""User accounts: hashing, lookup and management.

Passwords are stored as PBKDF2 hashes (via werkzeug.security), never in
plain text. Accounts live in the `users` table of the database.
"""

import hashlib

from werkzeug.security import check_password_hash, generate_password_hash

from config import DEFAULT_USERS
from database import connect


def hash_password(password):
    return generate_password_hash(password)


def verify_password(password_hash, password):
    return check_password_hash(password_hash, password)


def hash_token(raw):
    """Hash an API key so the raw value is never stored."""
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def find_user(username):
    """Return a user as a dict, or None."""
    connection = connect()
    cursor = connection.cursor()
    cursor.execute(
        "SELECT username, password_hash, role, is_active, session_version, linked_reg_no "
        "FROM users WHERE username = ?",
        (username,),
    )
    row = cursor.fetchone()
    connection.close()
    if row is None:
        return None
    return {
        "username": row[0],
        "password_hash": row[1],
        "role": row[2],
        "is_active": bool(row[3]),
        "session_version": row[4],
        "linked_reg_no": row[5],
    }


def session_version(username):
    user = find_user(username)
    return user["session_version"] if user else 0


def list_users():
    connection = connect()
    cursor = connection.cursor()
    cursor.execute(
        "SELECT username, role, is_active, created_at, linked_reg_no "
        "FROM users ORDER BY username"
    )
    rows = cursor.fetchall()
    connection.close()
    return rows


def count_users():
    connection = connect()
    cursor = connection.cursor()
    cursor.execute("SELECT COUNT(*) FROM users")
    total = cursor.fetchone()[0]
    connection.close()
    return total


def create_user(username, password, role, linked_reg_no=""):
    connection = connect()
    cursor = connection.cursor()
    cursor.execute(
        "INSERT INTO users (username, password_hash, role, linked_reg_no) VALUES (?, ?, ?, ?)",
        (username, hash_password(password), role, linked_reg_no),
    )
    connection.commit()
    connection.close()


def set_linked_reg_no(username, reg_no):
    connection = connect()
    cursor = connection.cursor()
    cursor.execute(
        "UPDATE users SET linked_reg_no = ? WHERE username = ?",
        (reg_no, username),
    )
    connection.commit()
    connection.close()


def set_password(username, password):
    connection = connect()
    cursor = connection.cursor()
    cursor.execute(
        "UPDATE users SET password_hash = ?, session_version = session_version + 1 "
        "WHERE username = ?",
        (hash_password(password), username),
    )
    connection.commit()
    connection.close()


def set_role(username, role):
    connection = connect()
    cursor = connection.cursor()
    cursor.execute("UPDATE users SET role = ? WHERE username = ?", (role, username))
    connection.commit()
    connection.close()


def set_active(username, active):
    connection = connect()
    cursor = connection.cursor()
    cursor.execute("UPDATE users SET is_active = ? WHERE username = ?", (1 if active else 0, username))
    connection.commit()
    connection.close()


def delete_user(username):
    connection = connect()
    cursor = connection.cursor()
    cursor.execute("DELETE FROM users WHERE username = ?", (username,))
    connection.commit()
    connection.close()


def seed_default_users():
    """Create the starter accounts on a fresh database."""
    if count_users() > 0:
        return
    for username, password, role in DEFAULT_USERS:
        create_user(username, password, role)
