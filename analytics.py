"""Performance trend analytics.

Turns term-wise figures into a small trend view (percentage per term plus the
change from the previous term) and a grade distribution. Pure functions, so
they are easy to unit test.
"""

GRADE_ORDER = ["A+", "A", "B+", "B", "C", "D", "F"]


def direction(change):
    """Classify a percentage change as up, down or flat."""
    if change is None:
        return "flat"
    if change > 0.5:
        return "up"
    if change < -0.5:
        return "down"
    return "flat"


def term_trend(points):
    """Annotate ``[{term, percentage}]`` points with change and direction."""
    trend = []
    previous = None
    for point in points:
        percentage = point["percentage"]
        change = None if previous is None else round(percentage - previous, 2)
        trend.append({
            "term": point["term"],
            "percentage": percentage,
            "change": change,
            "direction": direction(change),
        })
        previous = percentage
    return trend


def cohort_average(students):
    """Average percentage across build_rows-style student dicts."""
    if not students:
        return 0.0
    return round(sum(student["percentage"] for student in students) / len(students), 2)


def grade_distribution(students):
    """Return ordered [(grade, count)] pairs, appending any custom grades."""
    counts = {}
    for student in students:
        grade = student["grade"]
        counts[grade] = counts.get(grade, 0) + 1

    ordered = list(GRADE_ORDER)
    for grade in counts:
        if grade not in ordered:
            ordered.append(grade)
    return [(grade, counts.get(grade, 0)) for grade in ordered]
