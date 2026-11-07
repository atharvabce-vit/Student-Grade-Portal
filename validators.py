import datetime
import re

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PHONE_RE = re.compile(r"^[0-9+\-\s()]{7,20}$")
DATE_FORMAT = "%Y-%m-%d"


def is_valid_email(value):
    return bool(EMAIL_RE.match(value))


def is_valid_phone(value):
    return bool(PHONE_RE.match(value))


def is_valid_date(value):
    try:
        datetime.datetime.strptime(value, DATE_FORMAT)
        return True
    except ValueError:
        return False


def validate_mark(value, max_mark):
    if value == "":
        return "A mark is required."
    try:
        mark = int(value)
    except (TypeError, ValueError):
        return "Enter a whole number."
    if mark < 0 or mark > max_mark:
        return f"Marks must be between 0 and {max_mark}."
    return ""


def validate_details(details):
    errors = []
    email = details.get("email", "").strip()
    phone = details.get("phone", "").strip()
    dob = details.get("dob", "").strip()

    if email and not is_valid_email(email):
        errors.append("Enter a valid email address.")
    if phone and not is_valid_phone(phone):
        errors.append("Enter a valid phone number (digits, spaces, + and - only).")
    if dob and not is_valid_date(dob):
        errors.append("Enter the date of birth as YYYY-MM-DD.")

    return errors
