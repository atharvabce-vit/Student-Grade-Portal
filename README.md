# Student Grade Portal

[![CI](https://github.com/atharvabce-vit/Student-Grade-Portal/actions/workflows/ci.yml/badge.svg)](https://github.com/atharvabce-vit/Student-Grade-Portal/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/Flask-3.1.3-black)](https://flask.palletsprojects.com/)
[![Tests](https://img.shields.io/badge/tests-27%20passing-brightgreen)](#tests)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)

A CRUD application to manage student academic records, built with Python and SQLite.

It can be used two ways, from the same codebase and the same database:

- a command line program
- a web app in the browser (Flask)

## Features

- Add a student (name, marks per subject out of 50, plus optional profile fields such
  as class, section, term, guardian and contact details). The registration number is
  generated automatically, so it is never typed by the user.
- View all students with pagination (10 per page), search by registration number / name,
  and filter by class, section and term
- Update a student's marks or details
- Quick marks entry: pick a subject and fill in the marks for the whole class at once
- Attendance: mark present / absent / late per day and see a running summary per student
- Delete a student record. Deletes are soft by default, so records move to the Archive
  and can be restored or purged (admin only)
- Manage subjects and their weights, so the subject list and percentage calculation are
  not fixed in code (admin only)
- Automatic total, percentage, letter grade and PASS / FAIL per student (weights aware)
- Per-student report card page with the profile, attendance and change history, plus a
  clean printable layout (Print / Save as PDF)
- Class statistics: average, topper, lowest scorer, pass percentage, subject averages
- Subject averages and a grade distribution shown as charts
- Sort by registration number, name, percentage or total, and filter by pass / fail
- Export all records to CSV, Excel (.xlsx) or a single PDF of report cards
- Import students from a document (CSV, TSV, Excel, PDF, Word or plain text). The
  names and subject marks are read out of the file automatically, each student gets a
  generated registration number, and duplicate rows are skipped and reported.
- Login with two roles: admin and faculty. Passwords are stored as PBKDF2 hashes in the
  database, with a temporary lockout after repeated failures.
- User management (create accounts, change roles, reset passwords, enable/disable) and
  an audit log of actions (both admin only)
- A token protected JSON API and a light / dark theme for the web app

## Screenshots

| Students | Report card |
|----------|-------------|
| ![Students list](docs/screenshots/students.png) | ![Report card](docs/screenshots/report.png) |

| Statistics | Import |
|------------|--------|
| ![Class statistics](docs/screenshots/stats.png) | ![Import page](docs/screenshots/import.png) |

## Tech Stack

- Python 3
- SQLite (built into Python, no server needed)
- Flask for the web version, Flask-WTF for CSRF protection
- openpyxl, pdfplumber and python-docx for the file import
- reportlab for the PDF report cards, openpyxl again for the Excel export
- python-dotenv for optional `.env` configuration
- waitress for running the web app in production

## Project Structure

```
Student-Grade-Portal-Project/
├── main.py          # Command line entry point
├── app.py           # Web app entry point (Flask) and JSON API
├── config.py        # Settings: env vars, subjects, marks, grade scale, permissions
├── database.py      # All SQLite code (students, marks, subjects, users, audit, attendance)
├── grading.py       # Total, percentage (weights aware), result and letter grade
├── reports.py       # Class statistics, sorting, filtering
├── auth.py          # Login, login lockout and permission checks
├── users.py         # User accounts: hashing, lookup and management
├── logging_setup.py # Console + rotating file logging
├── students.py      # Command line menu actions
├── importer.py      # Reads CSV, Excel, PDF, Word and text files
├── export.py        # CSV and Excel export
├── pdf_reports.py   # Batch PDF report cards
├── templates/       # HTML pages for the web app
├── static/          # CSS and JS for the web app
├── tests/           # Unit tests (unittest)
├── docs/screenshots # Screenshots used in this README
├── Dockerfile       # Container image for deployment
├── .dockerignore
├── .env.example     # Sample environment configuration
├── .github/workflows/ci.yml   # GitHub Actions test workflow
├── requirements.txt
├── .gitignore
├── LICENSE
└── README.md
```

## Setup

Install the dependencies:

```
pip install -r requirements.txt
```

The command line version and CSV / TSV / text import only need the standard library
plus Werkzeug (pulled in by Flask) for password hashing. Flask and Flask-WTF are needed
for the web version, reportlab for the PDF export, and openpyxl, pdfplumber and
python-docx only when importing or exporting Excel, PDF or Word files.

## Run the command line version

```
python main.py
```

## Run the web version

```
python app.py
```

Then open http://127.0.0.1:5000 in your browser.

For a production-style run (no debug reloader), use waitress:

```
waitress-serve --host=0.0.0.0 --port=5000 app:app
```

## Run with Docker

Build and start the container:

```
docker build -t student-grade-portal .
docker run -p 5000:5000 student-grade-portal
```

Then open http://127.0.0.1:5000.

## Configuration

Settings live in `config.py` and every value can be overridden with an environment
variable or a `.env` file. Copy `.env.example` to `.env` and adjust as needed. The
defaults work out of the box for development; set `SGP_ENV=production` to force a
secure session cookie and turn the debug reloader off.

## Login

Two demo accounts are created automatically the first time the database is
initialised (on first run, or on first login with the command line version):

| Username | Password   | Role    | Can do |
|----------|------------|---------|--------|
| admin    | admin123   | admin   | everything, including archive, subjects, users and audit |
| faculty  | faculty123 | faculty | add, view, search, update, marks, attendance, import, stats, report, export (no archive, subjects, users or audit) |

Passwords are never stored in plain text: `users.py` stores a PBKDF2 hash of each
password and `auth.py` verifies whatever is typed at login. After several failed
attempts for the same username the account is locked out temporarily. Manage accounts
(create, change roles, reset passwords, enable/disable, delete) from the Users page,
which is admin only. Change the demo passwords after the first login.

## Tests

The `tests/` folder holds a unit test suite (grading, reports, importer and the
database) built with the standard library `unittest`. Run it with:

```
python -m unittest discover -v
```

The same command runs in CI on every push and pull request via
`.github/workflows/ci.yml`.

## Grading

Defined in `config.py`:

| Setting | Value |
|---------|-------|
| Subjects | Maths, Physics, Chemistry, English, Computer |
| Marks per subject | Out of 50 |
| Pass mark | 20 in every subject |

Percentage is calculated as `total / (number of subjects * 50) * 100`. Each subject also
has a weight (1 by default, editable on the Subjects page); when weights are set the
percentage becomes `sum(mark * weight) / sum(50 * weight) * 100`, so a heavier subject
counts for more.

The subject list itself is stored in the database and can be changed on the Subjects
page (admin only), so it is not fixed to the five subjects in `config.py` at runtime.

Letter grade comes from the percentage:

| Percentage | Grade |
|------------|-------|
| 90 and above | A+ |
| 80 - 89 | A |
| 70 - 79 | B+ |
| 60 - 69 | B |
| 50 - 59 | C |
| 40 - 49 | D |
| below 40 | F |

A student is marked FAIL if any single subject is below the pass mark.

## Registration numbers

Registration numbers are generated by the program, not entered by the user.

The first number is chosen at random between 1000 and 9000, and every student after
that gets the previous number plus one. So the numbers look like:

```
SGP4821
SGP4822
SGP4823
```

The prefix and the random range are set in `config.py` (`REG_PREFIX`, `REG_START_MIN`,
`REG_START_MAX`). The last used number is stored in a small `settings` table in the
database, so the sequence continues even after a record is deleted, and it keeps
count across restarts.

## Import students from a file

Instead of typing every student, you can upload a file that already contains the
names and subject marks and the program will read them out and add each student
automatically. Registration numbers are generated for the imported students, and
any row that is wrong is skipped and reported instead of stopping the whole import.
Rows that match a student already in the database (same name and marks) are skipped
as duplicates.

Supported file types:

| Type | Extensions | Needs |
|------|------------|-------|
| CSV | .csv | standard library |
| Tab separated | .tsv | standard library |
| Plain text | .txt | standard library |
| Excel | .xlsx, .xlsm | openpyxl |
| PDF | .pdf | pdfplumber |
| Word | .docx | python-docx |

The file must have a header row with a name column and one column per subject. The
column names are matched loosely, so `Name`, `Student Name` or `Full Name` all work,
and subjects are recognised in short forms too (`Math`, `Phy`, `Chem`, `Eng`, `CS`).
A typical file looks like this:

```
Name,Maths,Physics,Chemistry,English,Computer
Riya Sharma,42,38,45,40,47
Arjun Mehta,35,29,31,44,38
```

Where to find the option:

- Command line version: menu option 7, "Import students from a file", then enter the
  file path when asked.
- Web version: the "Import" page in the navigation bar. A sample CSV template can be
  downloaded from that page with the "Download CSV template" link.

Working with Google Docs and Google Sheets:

- Google Docs and Google Sheets are online, so export the file first and upload the
  exported copy.
- From Google Sheets, use File, Download and pick CSV, Excel (.xlsx) or PDF.
- From Google Docs, use File, Download and pick PDF or Microsoft Word (.docx), and
  put the data in a table so it can be read.

## Marks entry, attendance and archive

- Marks entry (admins and faculty): pick a subject, fill in a mark for each student and
  save the whole column in one go. Empty boxes are left unchanged.
- Attendance (admins and faculty): pick a date, set each student to present / absent /
  late and save. The page also shows a running present rate per student, and each
  student's recent attendance appears on their report card.
- Archive (admins): deleting a student moves them to the Archive instead of removing
  the row, so a record can be restored or purged permanently.

## Exports

From the web app you can download:

- CSV of all records (`Export CSV` in the navigation bar)
- Excel `.xlsx` of all records (`/export/excel`)
- A single PDF of printable report cards, one page per student (`/export/pdf`)

## JSON API

A small read/write API is available for other programs. Send the token from
`SGP_API_TOKEN` (default `dev-api-token`) in the `X-API-Token` header.

| Method | Path | What it does |
|--------|------|--------------|
| GET | `/api/students` | List every student with marks and computed fields |
| POST | `/api/students` | Create a student from `{"name": "...", "marks": [...]}` |
| GET | `/api/students/<reg_no>` | Fetch one student with profile fields |
| DELETE | `/api/students/<reg_no>` | Permanently delete one student |
| GET | `/api/openapi.json` | OpenAPI description of the endpoints |

The web app also has an `API` page in the navigation bar that documents these. Change
the token in production.

## Audit log and users

- Every add, update, delete, import, login and admin action is written to an audit log,
  visible on the Audit page (admin only) and per student on the report card.
- The Users page (admin only) lets an admin create accounts, change roles, reset
  passwords, and enable or disable accounts.

## Database Schema

The database `students.db` keeps students and their marks in separate tables, so the
list of subjects is flexible, along with tables for subjects, users, the audit log,
attendance and the registration counter.

`students`:

| Column | Type | Notes |
|--------|------|-------|
| reg_no | TEXT | Primary key, generated automatically |
| name   | TEXT | Student name |
| email, phone, student_class, section, gender, dob, guardian, academic_year, term | TEXT | Optional profile fields |
| is_deleted | INTEGER | 1 when the record is in the Archive |
| created_at | TEXT | When the row was created |

`marks`:

| Column  | Type    | Notes |
|---------|---------|-------|
| reg_no  | TEXT    | Foreign key to `students` (deleted with the student) |
| subject | TEXT    | Subject name |
| mark    | INTEGER | Out of 50 |

`subjects`:

| Column   | Type    | Notes |
|----------|---------|-------|
| name     | TEXT    | Primary key |
| position | INTEGER | Display order |
| weight   | REAL    | Weight used in the percentage (default 1) |

`users`:

| Column | Type | Notes |
|--------|------|-------|
| username | TEXT | Primary key |
| password_hash | TEXT | PBKDF2 hash |
| role | TEXT | admin or faculty |
| is_active | INTEGER | 0 disables the account |
| created_at | TEXT | When the account was created |

`audit_log`, `attendance` and `settings` hold the action history, per-day attendance and
the last generated registration number respectively.

The old single-table layout (with a `maths`, `physics`, ... column each) is upgraded
automatically on first run: `database.py` detects it and moves the data into the two
tables above. Extra profile columns are added to an existing `students` table in place.

## Notes

- `students.db` and the exported CSV are created at runtime and are not tracked by git.
- Both the command line version and the web version use the same database file,
  so records added in one show up in the other.

## License

MIT. See the LICENSE file.
