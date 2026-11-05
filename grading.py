from config import GRADE_SCALE, MAX_MARK, PASS_MARK, SUBJECTS


def calculate_total(marks):
    return sum(marks)


def calculate_percentage(marks):
    maximum_marks = len(SUBJECTS) * MAX_MARK
    return calculate_total(marks) / maximum_marks * 100


def get_result(marks):
    for mark in marks:
        if mark < PASS_MARK:
            return "FAIL"
    return "PASS"


def get_grade(percentage):
    for minimum, grade in GRADE_SCALE:
        if percentage >= minimum:
            return grade
    return "F"


def calculate(marks):
    return calculate_total(marks), calculate_percentage(marks), get_result(marks)
