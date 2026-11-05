import random
import sqlite3

from config import DB_NAME, REG_PREFIX, REG_START_MAX, REG_START_MIN, SUBJECTS


STUDENTS_TABLE = """
    CREATE TABLE IF NOT EXISTS students (
        reg_no TEXT PRIMARY KEY,
        name   TEXT NOT NULL
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

SETTINGS_TABLE = """
    CREATE TABLE IF NOT EXISTS settings (
        name  TEXT PRIMARY KEY,
        value INTEGER
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


def create_table():
    connection = connect()
    cursor = connection.cursor()
    _migrate_old_students(cursor)
    cursor.execute(STUDENTS_TABLE)
    cursor.execute(MARKS_TABLE)
    cursor.execute(SETTINGS_TABLE)
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


def _write_marks(cursor, reg_no, marks):
    for index, subject in enumerate(SUBJECTS):
        cursor.execute(
            "INSERT INTO marks (reg_no, subject, mark) VALUES (?, ?, ?)",
            (reg_no, subject, marks[index])
        )


def _attach_marks(cursor, students):
    cursor.execute("SELECT reg_no, subject, mark FROM marks")
    stored = {}
    for reg_no, subject, mark in cursor.fetchall():
        stored.setdefault(reg_no, {})[subject] = mark

    rows = []
    for reg_no, name in students:
        marks = stored.get(reg_no, {})
        rows.append((reg_no, name) + tuple(marks.get(subject, 0) for subject in SUBJECTS))
    return rows


def insert_student(name, marks):
    reg_no = generate_reg_no()
    connection = connect()
    cursor = connection.cursor()
    cursor.execute("INSERT INTO students (reg_no, name) VALUES (?, ?)", (reg_no, name))
    _write_marks(cursor, reg_no, marks)
    connection.commit()
    connection.close()
    return reg_no


def fetch_all_students():
    connection = connect()
    cursor = connection.cursor()
    cursor.execute("SELECT reg_no, name FROM students ORDER BY reg_no")
    students = cursor.fetchall()
    rows = _attach_marks(cursor, students)
    connection.close()
    return rows


def fetch_student(reg_no):
    connection = connect()
    cursor = connection.cursor()
    cursor.execute("SELECT reg_no, name FROM students WHERE reg_no = ?", (reg_no,))
    row = cursor.fetchone()
    rows = _attach_marks(cursor, [row]) if row else []
    connection.close()
    return rows[0] if rows else None


def search_students(keyword):
    connection = connect()
    cursor = connection.cursor()
    cursor.execute(
        "SELECT reg_no, name FROM students WHERE reg_no = ? OR name LIKE ? ORDER BY reg_no",
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


def delete_student_record(reg_no):
    connection = connect()
    cursor = connection.cursor()
    cursor.execute("DELETE FROM marks WHERE reg_no = ?", (reg_no,))
    cursor.execute("DELETE FROM students WHERE reg_no = ?", (reg_no,))
    connection.commit()
    connection.close()


def existing_signatures():
    signatures = set()
    for row in fetch_all_students():
        name = row[1].strip().lower()
        marks = tuple(row[2:2 + len(SUBJECTS)])
        signatures.add((name, marks))
    return signatures
