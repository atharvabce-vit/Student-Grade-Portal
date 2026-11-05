DB_NAME = "students.db"

CSV_FILE = "student_records.csv"

SUBJECTS = ["Maths", "Physics", "Chemistry", "English", "Computer"]

MAX_MARK = 50

PASS_MARK = 20

GRADE_SCALE = [
    (90, "A+"),
    (80, "A"),
    (70, "B+"),
    (60, "B"),
    (50, "C"),
    (40, "D"),
]

REG_PREFIX = "SGP"

REG_START_MIN = 1000

REG_START_MAX = 9000

USERS = {
    "admin": {"password": "admin123", "role": "admin"},
    "faculty": {"password": "faculty123", "role": "faculty"},
}

PERMISSIONS = {
    "admin": ["add", "view", "search", "update", "delete", "export", "stats"],
    "faculty": ["add", "view", "search", "update", "export", "stats"],
}
