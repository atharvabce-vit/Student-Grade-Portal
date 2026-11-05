import random
import sqlite3

from config import DB_NAME, REG_PREFIX, REG_START_MAX, REG_START_MIN, SUBJECTS

# Extra per-student fields kept outside the positional mark columns so the
# (reg_no, name, *marks) row contract used across the app stays intact.
STUDENT_FIELDS = [
    "email",
    "phone",
    "student_class",
    "section",
    "gender",
    "dob",
    "guardian",
    "academic_year",
    "term",
]

STUDENTS_TABLE = """
    CREATE TABLE IF NOT EXISTS students (
        reg_no        TEXT PRIMARY KEY,
        name          TEXT NOT NULL,
        email         TEXT NOT NULL DEFAULT '',
        phone         TEXT NOT NULL DEFAULT '',
        student_class TEXT NOT NULL DEFAULT '',
        section       TEXT NOT NULL DEFAULT '',
        gender        TEXT NOT NULL DEFAULT '',
        dob           TEXT NOT NULL DEFAULT '',
        guardian      TEXT NOT NULL DEFAULT '',
        academic_year TEXT NOT NULL DEFAULT '',
        term          TEXT NOT NULL DEFAULT '',
        is_deleted    INTEGER NOT NULL DEFAULT 0,
        created_at    TEXT NOT NULL DEFAULT (datetime('now'))
    )
"""

MARKS_TABLE = """
    CREATE TABLE IF NOT EXISTS marks (
        reg_no  TEXT NOT NULL,
        subject TEXT NOT NULL,
        mark    INTEGER NOT NULL,
        PRIMARY KEY (reg_no, subject),
        FOREIGN KEY (reg_no) REFERENCES students (reg_no) ON DELETE CASCADE
    )
"""

SUBJECTS_TABLE = """
    CREATE TABLE IF NOT EXISTS subjects (
        name     TEXT PRIMARY KEY,
        position INTEGER NOT NULL,
        weight   REAL NOT NULL DEFAULT 1
    )
"""

SETTINGS_TABLE = """
    CREATE TABLE IF NOT EXISTS settings (
        name  TEXT PRIMARY KEY,
        value INTEGER
    )
"""

USERS_TABLE = """
    CREATE TABLE IF NOT EXISTS users (
        username      TEXT PRIMARY KEY,
        password_hash TEXT NOT NULL,
        role          TEXT NOT NULL,
        is_active     INTEGER NOT NULL DEFAULT 1,
        created_at    TEXT NOT NULL DEFAULT (datetime('now'))
    )
"""

AUDIT_TABLE = """
    CREATE TABLE IF NOT EXISTS audit_log (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        username   TEXT,
        action     TEXT NOT NULL,
        target     TEXT,
        details    TEXT,
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
    )
"""

ATTENDANCE_TABLE = """
    CREATE TABLE IF NOT EXISTS attendance (
        reg_no TEXT NOT NULL,
        day    TEXT NOT NULL,
        status TEXT NOT NULL,
        PRIMARY KEY (reg_no, day),
        FOREIGN KEY (reg_no) REFERENCES students (reg_no) ON DELETE CASCADE
    )
"""


def connect():
    connection = sqlite3.connect(DB_NAME)
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def _table_exists(cursor, table):
    cursor.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?", (table,))
    return cursor.fetchone() is not None


def _table_columns(cursor, table):
    cursor.execute(f"PRAGMA table_info({table})")
    return [row[1] for row in cursor.fetchall()]


def _migrate_old_students(cursor):
    if not _table_exists(cursor, "students"):
        return
    if "maths" not in _table_columns(cursor, "students"):
        return

    cursor.execute("SELECT * FROM students")
    old_rows = cursor.fetchall()

    cursor.execute("ALTER TABLE students RENAME TO students_legacy")
    cursor.execute(STUDENTS_TABLE)
    cursor.execute(MARKS_TABLE)

    for row in old_rows:
        cursor.execute("INSERT INTO students (reg_no, name) VALUES (?, ?)", (row[0], row[1]))
        for index, subject in enumerate(SUBJECTS):
            value = row[2 + index] if 2 + index < len(row) else 0
            cursor.execute(
                "INSERT INTO marks (reg_no, subject, mark) VALUES (?, ?, ?)",
                (row[0], subject, value)
            )

    cursor.execute("DROP TABLE students_legacy")


def _add_missing_columns(cursor, table, columns):
    existing = _table_columns(cursor, table)
    for name, definition in columns:
        if name not in existing:
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")


def _migrate_student_columns(cursor):
    if not _table_exists(cursor, "students"):
        return
    _add_missing_columns(cursor, "students", [
        ("email", "TEXT NOT NULL DEFAULT ''"),
        ("phone", "TEXT NOT NULL DEFAULT ''"),
        ("student_class", "TEXT NOT NULL DEFAULT ''"),
        ("section", "TEXT NOT NULL DEFAULT ''"),
        ("gender", "TEXT NOT NULL DEFAULT ''"),
        ("dob", "TEXT NOT NULL DEFAULT ''"),
        ("guardian", "TEXT NOT NULL DEFAULT ''"),
        ("academic_year", "TEXT NOT NULL DEFAULT ''"),
        ("term", "TEXT NOT NULL DEFAULT ''"),
        ("is_deleted", "INTEGER NOT NULL DEFAULT 0"),
        ("created_at", "TEXT NOT NULL DEFAULT ''"),
    ])


def create_table():
    connection = connect()
    cursor = connection.cursor()
    _migrate_old_students(cursor)
    cursor.execute(STUDENTS_TABLE)
    cursor.execute(MARKS_TABLE)
    cursor.execute(SUBJECTS_TABLE)
    cursor.execute(SETTINGS_TABLE)
    cursor.execute(USERS_TABLE)
    cursor.execute(AUDIT_TABLE)
    cursor.execute(ATTENDANCE_TABLE)
    _migrate_student_columns(cursor)
    connection.commit()
    connection.close()
    seed_subjects()


def seed_subjects():
    """Populate the subjects table from config on first run."""
    connection = connect()
    cursor = connection.cursor()
    cursor.execute("SELECT COUNT(*) FROM subjects")
    if cursor.fetchone()[0] == 0:
        for position, name in enumerate(SUBJECTS):
            cursor.execute(
                "INSERT INTO subjects (name, position, weight) VALUES (?, ?, 1)",
                (name, position),
            )
        connection.commit()
    connection.close()


def get_subjects():
    """Return subjects ordered by position as (name, weight) tuples."""
    connection = connect()
    cursor = connection.cursor()
    cursor.execute("SELECT name, weight FROM subjects ORDER BY position, name")
    rows = cursor.fetchall()
    connection.close()
    return rows


def subject_names():
    return [name for name, _weight in get_subjects()]


def subject_weights():
    return [weight for _name, weight in get_subjects()]


def add_subject(name):
    name = name.strip()
    if name == "":
        return False
    connection = connect()
    cursor = connection.cursor()
    cursor.execute("SELECT COALESCE(MAX(position), -1) + 1 FROM subjects")
    position = cursor.fetchone()[0]
    try:
        cursor.execute(
            "INSERT INTO subjects (name, position, weight) VALUES (?, ?, 1)",
            (name, position),
        )
        connection.commit()
        added = True
    except sqlite3.IntegrityError:
        added = False
    connection.close()
    return added


def remove_subject(name):
    connection = connect()
    cursor = connection.cursor()
    cursor.execute("DELETE FROM marks WHERE subject = ?", (name,))
    cursor.execute("DELETE FROM subjects WHERE name = ?", (name,))
    connection.commit()
    connection.close()


def set_subject_weight(name, weight):
    connection = connect()
    cursor = connection.cursor()
    cursor.execute("UPDATE subjects SET weight = ? WHERE name = ?", (weight, name))
    connection.commit()
    connection.close()


def generate_reg_no():
    connection = connect()
    cursor = connection.cursor()
    cursor.execute("SELECT value FROM settings WHERE name = 'last_reg_no'")
    row = cursor.fetchone()

    if row is None:
        number = random.randint(REG_START_MIN, REG_START_MAX)
    else:
        number = row[0] + 1

    cursor.execute(
        "INSERT INTO settings (name, value) VALUES ('last_reg_no', ?) "
        "ON CONFLICT(name) DO UPDATE SET value = ?",
        (number, number)
    )
    connection.commit()
    connection.close()
    return REG_PREFIX + f"{number:04d}"


def _subject_names(cursor):
    cursor.execute("SELECT name FROM subjects ORDER BY position, name")
    names = [row[0] for row in cursor.fetchall()]
    return names if names else list(SUBJECTS)


def _write_marks(cursor, reg_no, marks):
    names = _subject_names(cursor)
    for index, subject in enumerate(names):
        value = marks[index] if index < len(marks) else 0
        cursor.execute(
            "INSERT INTO marks (reg_no, subject, mark) VALUES (?, ?, ?)",
            (reg_no, subject, value)
        )


def _attach_marks(cursor, students):
    cursor.execute("SELECT reg_no, subject, mark FROM marks")
    stored = {}
    for reg_no, subject, mark in cursor.fetchall():
        stored.setdefault(reg_no, {})[subject] = mark

    names = _subject_names(cursor)
    rows = []
    for reg_no, name in students:
        marks = stored.get(reg_no, {})
        rows.append((reg_no, name) + tuple(marks.get(subject, 0) for subject in names))
    return rows


def _insert_student_row(cursor, name, marks, details):
    reg_no = generate_reg_no()
    cursor.execute("INSERT INTO students (reg_no, name) VALUES (?, ?)", (reg_no, name))
    _write_marks(cursor, reg_no, marks)
    _update_details(cursor, reg_no, details or {})
    return reg_no


def insert_student(name, marks, details=None):
    connection = connect()
    cursor = connection.cursor()
    reg_no = _insert_student_row(cursor, name, marks, details)
    connection.commit()
    connection.close()
    return reg_no


def _update_details(cursor, reg_no, details):
    fields = [field for field in STUDENT_FIELDS if field in details]
    if not fields:
        return
    assignments = ", ".join(f"{field} = ?" for field in fields)
    values = [details[field] for field in fields]
    cursor.execute(
        f"UPDATE students SET {assignments} WHERE reg_no = ?",
        values + [reg_no],
    )


def update_student_details(reg_no, details):
    connection = connect()
    cursor = connection.cursor()
    _update_details(cursor, reg_no, details)
    connection.commit()
    connection.close()


def fetch_student_details(reg_no):
    connection = connect()
    cursor = connection.cursor()
    columns = ", ".join(STUDENT_FIELDS)
    cursor.execute(
        f"SELECT {columns}, is_deleted, created_at FROM students WHERE reg_no = ?",
        (reg_no,),
    )
    row = cursor.fetchone()
    connection.close()
    if row is None:
        return None
    details = {field: row[index] for index, field in enumerate(STUDENT_FIELDS)}
    details["is_deleted"] = bool(row[len(STUDENT_FIELDS)])
    details["created_at"] = row[len(STUDENT_FIELDS) + 1]
    return details


def fetch_details_map():
    """Return {reg_no: {field: value}} for every active student."""
    connection = connect()
    cursor = connection.cursor()
    columns = ", ".join(STUDENT_FIELDS)
    cursor.execute(f"SELECT reg_no, {columns} FROM students WHERE is_deleted = 0")
    rows = cursor.fetchall()
    connection.close()

    details = {}
    for row in rows:
        reg_no = row[0]
        details[reg_no] = {field: row[index + 1] for index, field in enumerate(STUDENT_FIELDS)}
    return details


def fetch_all_students():
    connection = connect()
    cursor = connection.cursor()
    cursor.execute("SELECT reg_no, name FROM students WHERE is_deleted = 0 ORDER BY reg_no")
    students = cursor.fetchall()
    rows = _attach_marks(cursor, students)
    connection.close()
    return rows


def fetch_deleted_students():
    connection = connect()
    cursor = connection.cursor()
    cursor.execute("SELECT reg_no, name FROM students WHERE is_deleted = 1 ORDER BY reg_no")
    students = cursor.fetchall()
    rows = _attach_marks(cursor, students)
    connection.close()
    return rows


def fetch_student(reg_no):
    connection = connect()
    cursor = connection.cursor()
    cursor.execute(
        "SELECT reg_no, name FROM students WHERE reg_no = ? AND is_deleted = 0",
        (reg_no,),
    )
    row = cursor.fetchone()
    rows = _attach_marks(cursor, [row]) if row else []
    connection.close()
    return rows[0] if rows else None


def search_students(keyword):
    connection = connect()
    cursor = connection.cursor()
    cursor.execute(
        "SELECT reg_no, name FROM students "
        "WHERE is_deleted = 0 AND (reg_no = ? OR name LIKE ?) ORDER BY reg_no",
        (keyword, "%" + keyword + "%")
    )
    students = cursor.fetchall()
    rows = _attach_marks(cursor, students)
    connection.close()
    return rows


def update_student_record(reg_no, name, marks):
    connection = connect()
    cursor = connection.cursor()
    cursor.execute("UPDATE students SET name = ? WHERE reg_no = ?", (name, reg_no))
    cursor.execute("DELETE FROM marks WHERE reg_no = ?", (reg_no,))
    _write_marks(cursor, reg_no, marks)
    connection.commit()
    connection.close()


def soft_delete_student(reg_no):
    connection = connect()
    cursor = connection.cursor()
    cursor.execute("UPDATE students SET is_deleted = 1 WHERE reg_no = ?", (reg_no,))
    connection.commit()
    connection.close()


def restore_student(reg_no):
    connection = connect()
    cursor = connection.cursor()
    cursor.execute("UPDATE students SET is_deleted = 0 WHERE reg_no = ?", (reg_no,))
    connection.commit()
    connection.close()


def delete_student_record(reg_no):
    connection = connect()
    cursor = connection.cursor()
    cursor.execute("DELETE FROM marks WHERE reg_no = ?", (reg_no,))
    cursor.execute("DELETE FROM attendance WHERE reg_no = ?", (reg_no,))
    cursor.execute("DELETE FROM students WHERE reg_no = ?", (reg_no,))
    connection.commit()
    connection.close()


def existing_signatures():
    signatures = set()
    for row in fetch_all_students():
        name = row[1].strip().lower()
        marks = tuple(row[2:])
        signatures.add((name, marks))
    return signatures


def record_audit(username, action, target="", details=""):
    connection = connect()
    cursor = connection.cursor()
    cursor.execute(
        "INSERT INTO audit_log (username, action, target, details) VALUES (?, ?, ?, ?)",
        (username, action, target, details),
    )
    connection.commit()
    connection.close()


def fetch_audit_log(limit=100, target=None):
    connection = connect()
    cursor = connection.cursor()
    if target is None:
        cursor.execute(
            "SELECT created_at, username, action, target, details FROM audit_log "
            "ORDER BY id DESC LIMIT ?",
            (limit,),
        )
    else:
        cursor.execute(
            "SELECT created_at, username, action, target, details FROM audit_log "
            "WHERE target = ? ORDER BY id DESC LIMIT ?",
            (target, limit),
        )
    rows = cursor.fetchall()
    connection.close()
    return rows


def marks_for_subject(subject):
    """Return {reg_no: mark} for one subject across active students."""
    connection = connect()
    cursor = connection.cursor()
    cursor.execute(
        "SELECT m.reg_no, m.mark FROM marks m "
        "JOIN students s ON s.reg_no = m.reg_no "
        "WHERE m.subject = ? AND s.is_deleted = 0",
        (subject,),
    )
    rows = cursor.fetchall()
    connection.close()
    return {reg_no: mark for reg_no, mark in rows}


def set_subject_mark(reg_no, subject, mark):
    connection = connect()
    cursor = connection.cursor()
    cursor.execute(
        "INSERT INTO marks (reg_no, subject, mark) VALUES (?, ?, ?) "
        "ON CONFLICT(reg_no, subject) DO UPDATE SET mark = ?",
        (reg_no, subject, mark, mark),
    )
    connection.commit()
    connection.close()


def mark_attendance(reg_no, day, status):
    connection = connect()
    cursor = connection.cursor()
    cursor.execute(
        "INSERT INTO attendance (reg_no, day, status) VALUES (?, ?, ?) "
        "ON CONFLICT(reg_no, day) DO UPDATE SET status = ?",
        (reg_no, day, status, status),
    )
    connection.commit()
    connection.close()


def fetch_attendance(day):
    connection = connect()
    cursor = connection.cursor()
    cursor.execute(
        "SELECT a.reg_no, s.name, a.status FROM attendance a "
        "JOIN students s ON s.reg_no = a.reg_no "
        "WHERE a.day = ? AND s.is_deleted = 0 ORDER BY a.reg_no",
        (day,),
    )
    rows = cursor.fetchall()
    connection.close()
    return rows


def attendance_for_student(reg_no):
    connection = connect()
    cursor = connection.cursor()
    cursor.execute(
        "SELECT day, status FROM attendance WHERE reg_no = ? ORDER BY day DESC LIMIT 60",
        (reg_no,),
    )
    rows = cursor.fetchall()
    connection.close()
    return rows


def attendance_summary():
    """Return (reg_no, name, present, total) for every active student."""
    connection = connect()
    cursor = connection.cursor()
    cursor.execute(
        "SELECT s.reg_no, s.name, "
        "SUM(CASE WHEN a.status = 'present' THEN 1 ELSE 0 END), COUNT(a.day) "
        "FROM students s LEFT JOIN attendance a ON a.reg_no = s.reg_no "
        "WHERE s.is_deleted = 0 GROUP BY s.reg_no, s.name ORDER BY s.reg_no",
    )
    rows = cursor.fetchall()
    connection.close()
    return [(reg_no, name, present or 0, total or 0) for reg_no, name, present, total in rows]
