from grading import calculate


def _marks_of(row):
    """Rows are (reg_no, name, *marks); the marks always trail the row."""
    return list(row[2:])


def sort_students(students, sort_by, weights=None):
    if sort_by == "name":
        return sorted(students, key=lambda row: row[1].lower())
    if sort_by == "percentage":
        return sorted(students, key=lambda row: calculate(_marks_of(row), weights)[1], reverse=True)
    if sort_by == "total":
        return sorted(students, key=lambda row: calculate(_marks_of(row), weights)[0], reverse=True)
    return sorted(students, key=lambda row: row[0])


def filter_students(students, result):
    if result == "pass":
        return [row for row in students if calculate(_marks_of(row))[2] == "PASS"]
    if result == "fail":
        return [row for row in students if calculate(_marks_of(row))[2] == "FAIL"]
    return students


def class_statistics(students, weights=None):
    summary = {
        "count": 0,
        "average": 0,
        "topper": None,
        "lowest": None,
        "passed": 0,
        "pass_percentage": 0,
        "subject_averages": [],
    }

    if len(students) == 0:
        return summary

    subject_count = len(_marks_of(students[0]))
    percentage_sum = 0
    passed = 0
    topper = None
    lowest = None
    subject_totals = [0] * subject_count

    for row in students:
        marks = _marks_of(row)
        percentage = calculate(marks, weights)[1]
        result = calculate(marks, weights)[2]

        percentage_sum += percentage
        if result == "PASS":
            passed += 1

        if topper is None or percentage > topper[2]:
            topper = (row[1], row[0], percentage)
        if lowest is None or percentage < lowest[2]:
            lowest = (row[1], row[0], percentage)

        for i in range(subject_count):
            if i < len(marks):
                subject_totals[i] += marks[i]

    summary["count"] = len(students)
    summary["average"] = percentage_sum / len(students)
    summary["topper"] = topper
    summary["lowest"] = lowest
    summary["passed"] = passed
    summary["pass_percentage"] = passed / len(students) * 100
    summary["subject_averages"] = [total / len(students) for total in subject_totals]
    return summary
