import csv
import os
import re

from config import MAX_MARK, SUBJECTS

NAME_HEADERS = ["name", "student name", "student", "full name", "student_name"]

SUBJECT_ALIASES = {
    "maths": ["maths", "math", "mathematics"],
    "physics": ["physics", "phy"],
    "chemistry": ["chemistry", "chem"],
    "english": ["english", "eng"],
    "computer": ["computer", "compsci", "cs", "computer science"],
}


def clean(value):
    if value is None:
        return ""
    return str(value).replace("\u00a0", " ").strip()


def matches(title, alias):
    if title == alias:
        return True
    return title.startswith(alias + " ") or title.startswith(alias + "(")


def detect_delimiter(line):
    counts = {",": line.count(","), ";": line.count(";"), "\t": line.count("\t")}
    best = max(counts, key=counts.get)
    if counts[best] == 0:
        return None
    return best


def split_line(line, delimiter):
    if delimiter is None:
        return [cell.strip() for cell in re.split(r"\s{2,}", line.strip())]
    return [cell.strip() for cell in line.split(delimiter)]


def find_columns(header):
    name_index = None
    subject_columns = {}

    for index in range(len(header)):
        title = clean(header[index]).lower()
        if title == "":
            continue

        if name_index is None and any(matches(title, alias) for alias in NAME_HEADERS):
            name_index = index
            continue

        for subject in SUBJECTS:
            if subject in subject_columns:
                continue
            aliases = SUBJECT_ALIASES.get(subject.lower(), [subject.lower()])
            if any(matches(title, alias) for alias in aliases):
                subject_columns[subject] = index
                break

    return name_index, subject_columns


def build_records(header, rows):
    name_index, subject_columns = find_columns(header)

    if name_index is None:
        return [], ["Could not find a Name column. The first row must contain the column headers."]

    missing = [subject for subject in SUBJECTS if subject not in subject_columns]
    if missing:
        return [], ["Missing a column for: " + ", ".join(missing)]

    records = []
    errors = []

    for position in range(len(rows)):
        row = rows[position]
        row_number = position + 2
        name = clean(row[name_index]) if name_index < len(row) else ""

        if name == "":
            continue

        marks = []
        problem = ""

        for subject in SUBJECTS:
            column = subject_columns[subject]
            value = clean(row[column]) if column < len(row) else ""

            if value == "":
                problem = f"{subject} marks are missing for {name}"
                break

            try:
                number = float(value)
            except ValueError:
                problem = f"{subject} marks '{value}' for {name} is not a number"
                break

            if number != int(number):
                problem = f"{subject} marks '{value}' for {name} must be a whole number"
                break

            number = int(number)
            if number < 0 or number > MAX_MARK:
                problem = f"{subject} marks {number} for {name} must be between 0 and {MAX_MARK}"
                break

            marks.append(number)

        if problem != "":
            errors.append(f"Row {row_number}: {problem}")
        else:
            records.append((name, marks))

    return records, errors


def lines_to_rows(lines):
    lines = [line for line in lines if clean(line) != ""]
    if len(lines) == 0:
        return [], []

    delimiter = detect_delimiter(lines[0])
    rows = [split_line(line, delimiter) for line in lines]
    return rows[0], rows[1:]


def read_delimited_rows(path, delimiter):
    with open(path, newline="", encoding="utf-8-sig", errors="replace") as handle:
        rows = [row for row in csv.reader(handle, delimiter=delimiter)]
    rows = [row for row in rows if any(clean(cell) != "" for cell in row)]

    if len(rows) == 0:
        return [], []
    return rows[0], rows[1:]


def read_text_rows(path):
    with open(path, encoding="utf-8-sig", errors="replace") as handle:
        lines = handle.read().split("\n")
    return lines_to_rows(lines)


def read_sheet_rows(path):
    try:
        from openpyxl import load_workbook
    except ImportError as error:
        raise ValueError("openpyxl is not installed. Run: pip install openpyxl") from error

    workbook = load_workbook(path, read_only=True, data_only=True)
    rows = [[clean(cell) for cell in row] for row in workbook.active.iter_rows(values_only=True)]
    workbook.close()

    rows = [row for row in rows if any(cell != "" for cell in row)]
    if len(rows) == 0:
        return [], []
    return rows[0], rows[1:]


def read_docx_rows(path):
    try:
        from docx import Document
    except ImportError as error:
        raise ValueError("python-docx is not installed. Run: pip install python-docx") from error

    document = Document(path)

    for table in document.tables:
        rows = [[clean(cell.text) for cell in row.cells] for row in table.rows]
        rows = [row for row in rows if any(cell != "" for cell in row)]
        if len(rows) > 0:
            return rows[0], rows[1:]

    lines = [paragraph.text for paragraph in document.paragraphs]
    return lines_to_rows(lines)


def read_pdf_rows(path):
    try:
        import pdfplumber
    except ImportError as error:
        raise ValueError("pdfplumber is not installed. Run: pip install pdfplumber") from error

    table_rows = []
    text_lines = []

    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            table = page.extract_table()
            if table:
                for row in table:
                    table_rows.append([clean(cell) for cell in row])

            text = page.extract_text() or ""
            for line in text.split("\n"):
                if clean(line) != "":
                    text_lines.append(line)

    table_rows = [row for row in table_rows if any(cell != "" for cell in row)]
    if len(table_rows) > 0:
        return table_rows[0], table_rows[1:]

    return lines_to_rows(text_lines)


def read_file(path):
    extension = os.path.splitext(path)[1].lower()

    if extension == ".csv":
        return read_delimited_rows(path, ",")
    if extension == ".tsv":
        return read_delimited_rows(path, "\t")
    if extension in (".txt", ".text"):
        return read_text_rows(path)
    if extension in (".xlsx", ".xlsm"):
        return read_sheet_rows(path)
    if extension == ".xls":
        raise ValueError("Old .xls files are not supported. Save the file as .xlsx and try again.")
    if extension == ".docx":
        return read_docx_rows(path)
    if extension == ".pdf":
        return read_pdf_rows(path)

    raise ValueError(
        f"Unsupported file type '{extension}'. Use .csv, .tsv, .xlsx, .pdf, .docx or .txt."
    )


def import_students(path):
    if not os.path.isfile(path):
        raise ValueError("File not found: " + path)
    if os.path.getsize(path) == 0:
        raise ValueError("The file is empty.")

    header, rows = read_file(path)
    return build_records(header, rows)
