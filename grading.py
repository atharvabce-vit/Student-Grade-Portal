from config import GRADE_SCALE, MAX_MARK, PASS_MARK


def calculate_total(marks):
    return sum(marks)


def calculate_percentage(marks, weights=None):
    if len(marks) == 0:
        return 0.0
    if weights:
        maximum = sum(MAX_MARK * weight for weight in weights)
        if maximum == 0:
            return 0.0
        earned = sum(mark * weight for mark, weight in zip(marks, weights, strict=False))
        return earned / maximum * 100
    maximum = len(marks) * MAX_MARK
    return calculate_total(marks) / maximum * 100


def get_result(marks, pass_mark=None):
    threshold = PASS_MARK if pass_mark is None else pass_mark
    for mark in marks:
        if mark < threshold:
            return "FAIL"
    return "PASS"


def get_grade(percentage, grade_scale=None):
    scale = grade_scale if grade_scale else GRADE_SCALE
    for minimum, grade in scale:
        if percentage >= minimum:
            return grade
    return "F"


def calculate(marks, weights=None, pass_mark=None, grade_scale=None):
    return (
        calculate_total(marks),
        calculate_percentage(marks, weights),
        get_result(marks, pass_mark),
    )
