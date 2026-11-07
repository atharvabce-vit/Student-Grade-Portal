"""Flag students who need extra support.

A student is "at risk" when any of three signals crosses a threshold: a low
overall percentage, poor attendance, or failed subjects. The functions here
are pure so they are easy to unit test without a database.
"""

from config import PASS_MARK, RISK_ATTENDANCE, RISK_PERCENTAGE


def assess(percentage, attendance_rate=None, failed_subjects=0,
           percentage_threshold=RISK_PERCENTAGE, attendance_threshold=RISK_ATTENDANCE):
    """Return {"at_risk": bool, "reasons": [str, ...]} for a single student."""
    reasons = []
    if percentage < percentage_threshold:
        reasons.append(f"Overall percentage {percentage:.2f}% is below {percentage_threshold}%")
    if attendance_rate is not None and attendance_rate < attendance_threshold:
        reasons.append(f"Attendance {attendance_rate:.1f}% is below {attendance_threshold}%")
    if failed_subjects:
        reasons.append(f"{failed_subjects} subject(s) below the pass mark")
    return {"at_risk": bool(reasons), "reasons": reasons}


def identify(students, attendance_rates=None, pass_mark=None, **thresholds):
    """Return the subset of ``students`` that is at risk.

    ``students`` are the row dicts produced by the app's ``build_rows`` helper
    (they carry ``reg_no``, ``marks`` and ``percentage``), and
    ``attendance_rates`` maps ``reg_no`` to an attendance percentage.
    """
    attendance_rates = attendance_rates or {}
    threshold = PASS_MARK if pass_mark is None else pass_mark

    flagged = []
    for student in students:
        failed = sum(1 for mark in student.get("marks", []) if mark < threshold)
        rate = attendance_rates.get(student["reg_no"])
        verdict = assess(student["percentage"], rate, failed, **thresholds)
        if verdict["at_risk"]:
            flagged.append({
                **student,
                "reasons": verdict["reasons"],
                "failed_subjects": failed,
                "attendance_rate": rate,
            })
    return flagged
