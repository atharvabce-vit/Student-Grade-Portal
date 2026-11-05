import csv
import io

from config import CSV_FILE
from database import fetch_all_students, subject_names, subject_weights
from grading import calculate, get_grade


def build_table():
    """Return (header, rows) shared by the CSV and Excel exports."""
    students = fetch_all_students()
    names = subject_names()
    weights = subject_weights()

    header = ["Reg No", "Name"] + names + ["Total", "Percentage", "Grade", "Result"]
    rows = []
    for row in students:
        marks = list(row[2:])
        total, percentage, result = calculate(marks, weights)
        rows.append(
            [row[0], row[1]] + marks + [total, round(percentage, 2), get_grade(percentage), result]
        )
    return header, rows


def export_to_csv(path=None):
    header, rows = build_table()
    target = path or CSV_FILE

    with open(target, "w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(header)
        writer.writerows(rows)

    return target, len(rows)


def build_csv_bytes():
    header, rows = build_table()
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(header)
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8")


def build_excel_bytes():
    from openpyxl import Workbook

    header, rows = build_table()
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Students"
    sheet.append(header)
    for row in rows:
        sheet.append(row)

    for column in range(1, len(header) + 1):
        sheet.column_dimensions[chr(64 + column)].width = 14

    buffer = io.BytesIO()
    workbook.save(buffer)
    workbook.close()
    return buffer.getvalue()
