import csv

from config import CSV_FILE, SUBJECTS
from database import fetch_all_students
from grading import calculate


def export_to_csv():
    students = fetch_all_students()

    if len(students) == 0:
        print("No records to export.")
        return

    with open(CSV_FILE, "w", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(["Reg No", "Name"] + SUBJECTS + ["Total", "Percentage", "Result"])

        for row in students:
            marks = row[2:2 + len(SUBJECTS)]
            total, percentage, result = calculate(marks)
            writer.writerow(
                [row[0], row[1]] + list(marks) + [total, round(percentage, 2), result]
            )

    print(f"Records exported to {CSV_FILE}")
