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

- Add a student (name and marks per subject out of 50). The registration number is
  generated automatically, so it is never typed by the user.
- View all students with pagination (10 per page), or search by registration number / name
- Update a student's marks or details
- Delete a student record (admin only)
- Automatic total, percentage, letter grade and PASS / FAIL per student
- Per-student report card page with a clean printable layout (Print / Save as PDF)
- Class statistics: average, topper, lowest scorer, pass percentage, subject averages
- Subject averages shown as bar charts
- Sort by registration number, name, percentage or total, and filter by pass / fail
- Export all records to CSV (includes total, percentage, grade and result)
- Import students from a document (CSV, TSV, Excel, PDF, Word or plain text). The
  names and subject marks are read out of the file automatically, each student gets a
  generated registration number, and duplicate rows are skipped and reported.
- Login with two roles: admin and faculty. Passwords are stored as SHA-256 hashes.

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
- Flask for the web version
- openpyxl, pdfplumber and python-docx for the file import
- waitress for running the web app in production

## Project Structure

```
Student-Grade-Portal-Project/
├── main.py          # Command line entry point
├── app.py           # Web app entry point (Flask)
├── config.py        # Settings: subjects, marks, grade scale, users
├── database.py      # All SQLite code (students + marks tables, migration)
├── grading.py       # Total, percentage, result and letter grade
├── reports.py       # Class statistics, sorting, filtering
├── auth.py          # Login (hashed passwords) and permission checks
├── students.py      # Command line menu actions
├── importer.py      # Reads CSV, Excel, PDF, Word and text files
├── export.py        # CSV export
├── templates/       # HTML pages for the web app
├── static/          # CSS for the web app
├── tests/           # Unit tests (unittest)
├── docs/screenshots # Screenshots used in this README
├── Dockerfile       # Container image for deployment
├── .dockerignore
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

The command line version and CSV / TSV / text import only need the standard
library. Flask is needed for the web version, and openpyxl, pdfplumber and
python-docx are only needed when importing Excel, PDF or Word files.

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

## Login

Two demo accounts are defined in `config.py`:

| Username | Password   | Role    | Can do |
|----------|------------|---------|--------|
| admin    | admin123   | admin   | everything, including delete |
| faculty  | faculty123 | faculty | add, view, search, update, stats, export, report (no delete) |

Passwords are not stored in plain text: `config.py` keeps a SHA-256 hash of each
password (with a static salt) and `auth.py` hashes whatever is typed at login and
compares the hashes. To change a password, replace the hash in `config.py`.

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

Percentage is calculated as `total / (number of subjects * 50) * 100`.

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

## Database Schema

The database `students.db` has two tables, so the list of subjects is flexible.

`students`:

| Column | Type | Notes |
|--------|------|-------|
| reg_no | TEXT | Primary key, generated automatically |
| name   | TEXT | Student name |

`marks`:

| Column  | Type    | Notes |
|---------|---------|-------|
| reg_no  | TEXT    | Foreign key to `students` (deleted with the student) |
| subject | TEXT    | Subject name |
| mark    | INTEGER | Out of 50 |

The old single-table layout (with a `maths`, `physics`, ... column each) is upgraded
automatically on first run: `database.py` detects it and moves the data into the two
tables above.

## Notes

- `students.db` and the exported CSV are created at runtime and are not tracked by git.
- Both the command line version and the web version use the same database file,
  so records added in one show up in the other.

## License

MIT. See the LICENSE file.
