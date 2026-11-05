from config import MAX_MARK, SUBJECTS
from database import (
    delete_student_record,
    existing_signatures,
    fetch_all_students,
    fetch_student,
    insert_student,
    search_students,
    subject_names,
    update_student_record,
)
from grading import calculate, get_grade
from importer import import_students
from reports import class_statistics, filter_students, sort_students


def get_marks(subject):
    while True:
        value = input(f"Enter marks for {subject} (out of {MAX_MARK}): ").strip()
        if value.isdigit():
            mark = int(value)
            if 0 <= mark <= MAX_MARK:
                return mark
            print(f"Marks must be between 0 and {MAX_MARK}.")
        else:
            print("Please enter a valid whole number.")


def display_students(students):
    if len(students) == 0:
        print("No records found.")
        return

    names = subject_names()
    header = f"{'Reg No':<10}{'Name':<20}"
    for subject in names:
        header += f"{subject[:8]:>9}"
    header += f"{'Total':>7}{'%':>7}{'Grade':>7}{'Result':>8}"

    print("-" * 104)
    print(header)
    print("-" * 104)

    for row in students:
        marks = row[2:2 + len(names)]
        total, percentage, result = calculate(marks)
        grade = get_grade(percentage)

        line = f"{row[0]:<10}{row[1]:<20}"
        for mark in marks:
            line += f"{mark:>9}"
        line += f"{total:>7}{percentage:>7.1f}{grade:>7}{result:>8}"
        print(line)

    print("-" * 104)


def add_student():
    print("\n--- ADD STUDENT ---")
    name = input("Enter student name: ").strip()

    if name == "":
        print("Student name cannot be empty.")
        return

    marks = []
    for subject in subject_names():
        marks.append(get_marks(subject))

    reg_no = insert_student(name, marks)
    print(f"Student added successfully. Registration number: {reg_no}")


def import_students_from_file():
    print("\n--- IMPORT STUDENTS FROM FILE ---")
    print("Supported files: .csv, .tsv, .xlsx, .pdf, .docx, .txt")
    print("First row must have a Name column and one column per subject: " + ", ".join(SUBJECTS))

    path = input("Enter the file path: ").strip().strip('"')
    if path == "":
        print("File path cannot be empty.")
        return

    try:
        records, errors = import_students(path)
    except ValueError as error:
        print(error)
        return

    if len(records) == 0:
        print("No valid student rows found in the file.")
    else:
        seen = existing_signatures()
        added = 0
        skipped = []

        for name, marks in records:
            signature = (name.strip().lower(), tuple(marks))
            if signature in seen:
                skipped.append(name)
                continue
            reg_no = insert_student(name, marks)
            seen.add(signature)
            added += 1
            print(f"Added {name} -> {reg_no}")

        print(f"\nImported {added} students.")
        if len(skipped) > 0:
            print(f"Skipped {len(skipped)} duplicate students: " + ", ".join(skipped))

    if len(errors) > 0:
        print("\nSkipped rows:")
        for error in errors:
            print("  " + error)


def view_all_students():
    print("\n--- ALL STUDENTS ---")
    print("Sort by:  1. Registration no   2. Name   3. Percentage   4. Total")
    sort_choice = input("Enter choice (default 1): ").strip()
    sort_by = {"2": "name", "3": "percentage", "4": "total"}.get(sort_choice, "reg_no")

    print("Filter:   1. All   2. Pass only   3. Fail only")
    filter_choice = input("Enter choice (default 1): ").strip()
    result_filter = {"2": "pass", "3": "fail"}.get(filter_choice, "all")

    students = filter_students(sort_students(fetch_all_students(), sort_by), result_filter)
    display_students(students)


def show_statistics():
    print("\n--- CLASS STATISTICS ---")
    summary = class_statistics(fetch_all_students())

    if summary["count"] == 0:
        print("No records found.")
        return

    print(f"Total students   : {summary['count']}")
    print(f"Class average    : {summary['average']:.2f}%")
    print(f"Passed           : {summary['passed']} ({summary['pass_percentage']:.2f}%)")
    print(f"Topper           : {summary['topper'][0]} ({summary['topper'][1]}) - {summary['topper'][2]:.2f}%")
    print(f"Lowest scorer    : {summary['lowest'][0]} ({summary['lowest'][1]}) - {summary['lowest'][2]:.2f}%")
    print("Subject averages :")
    names = subject_names()
    for i in range(len(names)):
        print(f"   {names[i]:<10} {summary['subject_averages'][i]:.2f} / {MAX_MARK}")


def search_student():
    print("\n--- SEARCH STUDENT ---")
    keyword = input("Enter registration number or name: ").strip()

    if keyword == "":
        print("Search text cannot be empty.")
        return

    display_students(search_students(keyword))


def update_student():
    print("\n--- UPDATE STUDENT ---")
    reg_no = input("Enter registration number to update: ").strip()

    row = fetch_student(reg_no)
    if row is None:
        print("Student not found.")
        return

    print("Current record:")
    display_students([row])

    print("1. Update name only")
    print("2. Update marks only")
    print("3. Update both")
    choice = input("Enter your choice: ").strip()

    if choice not in ("1", "2", "3"):
        print("Invalid choice.")
        return

    name = row[1]
    names = subject_names()
    marks = list(row[2:2 + len(names)])

    if choice in ("1", "3"):
        new_name = input("Enter new name: ").strip()
        if new_name != "":
            name = new_name

    if choice in ("2", "3"):
        for i in range(len(names)):
            marks[i] = get_marks(names[i])

    update_student_record(reg_no, name, marks)
    print("Record updated successfully.")


def delete_student():
    print("\n--- DELETE STUDENT ---")
    reg_no = input("Enter registration number to delete: ").strip()

    row = fetch_student(reg_no)
    if row is None:
        print("Student not found.")
        return

    display_students([row])
    confirm = input("Are you sure you want to delete this record? (y/n): ").strip().lower()

    if confirm == "y":
        delete_student_record(reg_no)
        print("Record deleted.")
    else:
        print("Delete cancelled.")
