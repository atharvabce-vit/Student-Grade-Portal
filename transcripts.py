"""Turn term-wise marks into a structured transcript."""

from config import MAX_MARK
from grading import get_grade


def build_transcript(term_marks, subjects, exams):
    """Convert {term: {subject: {exam: mark}}} into an ordered term list.

    Each term carries a row per subject (one cell per exam), plus the marks
    earned, how many were recorded, the percentage and the grade. Terms are
    returned in alphabetical order so the layout is stable.
    """
    terms = []
    for term in sorted(term_marks):
        rows = []
        earned = 0
        recorded = 0
        for subject in subjects:
            by_exam = term_marks[term].get(subject, {})
            marks = {exam: by_exam.get(exam) for exam in exams}
            rows.append({"subject": subject, "marks": marks})
            for value in marks.values():
                if value is not None:
                    earned += value
                    recorded += 1

        maximum = recorded * MAX_MARK
        percentage = round(earned / maximum * 100, 2) if maximum else 0.0
        terms.append({
            "term": term,
            "rows": rows,
            "earned": earned,
            "recorded": recorded,
            "maximum": maximum,
            "percentage": percentage,
            "grade": get_grade(percentage) if maximum else "-",
        })
    return terms


def cumulative(terms):
    """Overall earned / maximum / percentage across every term."""
    earned = sum(term["earned"] for term in terms)
    maximum = sum(term["maximum"] for term in terms)
    percentage = round(earned / maximum * 100, 2) if maximum else 0.0
    return {
        "earned": earned,
        "maximum": maximum,
        "percentage": percentage,
        "grade": get_grade(percentage) if maximum else "-",
    }
