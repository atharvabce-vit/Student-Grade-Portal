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

PAGE_SIZE = 10

PASSWORD_SALT = "sgp_salt_2026"

USERS = {
    "admin": {
        "password": "c4aad0196a9a86deb56ae8165237bcc7c8d66158d9049b539556d058af2db240",
        "role": "admin",
    },
    "faculty": {
        "password": "b58b4f92f2d8b39842157b6a6faaee37cfbf1409a251c6d8f2ebfe1e138240cb",
        "role": "faculty",
    },
}

PERMISSIONS = {
    "admin": ["add", "view", "search", "update", "delete", "export", "stats", "report"],
    "faculty": ["add", "view", "search", "update", "export", "stats", "report"],
}
