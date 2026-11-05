import random
import sqlite3

from config import DB_NAME, REG_PREFIX, REG_START_MAX, REG_START_MIN


def connect():
    return sqlite3.connect(DB_NAME)


def create_table():
    conn = connect()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS students (
            reg_no    TEXT PRIMARY KEY,
            name      TEXT NOT NULL,
            maths     INTEGER,
            physics   INTEGER,
            chemistry INTEGER,
            english   INTEGER,
            computer  INTEGER
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            name  TEXT PRIMARY KEY,
            value INTEGER
        )
    """)
    conn.commit()
    conn.close()


def generate_reg_no():
    conn = connect()
    cur = conn.cursor()
    cur.execute("SELECT value FROM settings WHERE name = 'last_reg_no'")
    row = cur.fetchone()

    if row is None:
        number = random.randint(REG_START_MIN, REG_START_MAX)
    else:
        number = row[0] + 1

    cur.execute(
        "INSERT INTO settings (name, value) VALUES ('last_reg_no', ?) "
        "ON CONFLICT(name) DO UPDATE SET value = ?",
        (number, number)
    )
    conn.commit()
    conn.close()
    return REG_PREFIX + f"{number:04d}"


def insert_student(name, marks):
    reg_no = generate_reg_no()
    conn = connect()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO students (reg_no, name, maths, physics, chemistry, english, computer)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (reg_no, name, marks[0], marks[1], marks[2], marks[3], marks[4]))
    conn.commit()
    conn.close()
    return reg_no


def fetch_all_students():
    conn = connect()
    cur = conn.cursor()
    cur.execute("SELECT * FROM students ORDER BY reg_no")
    rows = cur.fetchall()
    conn.close()
    return rows


def fetch_student(reg_no):
    conn = connect()
    cur = conn.cursor()
    cur.execute("SELECT * FROM students WHERE reg_no = ?", (reg_no,))
    row = cur.fetchone()
    conn.close()
    return row


def search_students(keyword):
    conn = connect()
    cur = conn.cursor()
    cur.execute(
        "SELECT * FROM students WHERE reg_no = ? OR name LIKE ? ORDER BY reg_no",
        (keyword, "%" + keyword + "%")
    )
    rows = cur.fetchall()
    conn.close()
    return rows


def update_student_record(reg_no, name, marks):
    conn = connect()
    cur = conn.cursor()
    cur.execute("""
        UPDATE students
        SET name = ?, maths = ?, physics = ?, chemistry = ?, english = ?, computer = ?
        WHERE reg_no = ?
    """, (name, marks[0], marks[1], marks[2], marks[3], marks[4], reg_no))
    conn.commit()
    conn.close()


def delete_student_record(reg_no):
    conn = connect()
    cur = conn.cursor()
    cur.execute("DELETE FROM students WHERE reg_no = ?", (reg_no,))
    conn.commit()
    conn.close()
