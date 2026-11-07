import datetime
import hmac
import logging
import os
import secrets
import tempfile
from datetime import timedelta

from flask import (
    Flask,
    Response,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    session,
    url_for,
)
from flask_wtf import CSRFProtect

import totp
from analytics import cohort_average, grade_distribution, term_trend
from auth import can, lockout_remaining, login
from config import (
    API_RATE_LIMIT,
    API_TOKEN,
    ATTENDANCE_STATUSES,
    CSV_FILE,
    DEBUG,
    ENV,
    EXAMS,
    GRADE_SCALE,
    LOGIN_RATE_LIMIT,
    MAX_MARK,
    PAGE_SIZE,
    PASS_MARK,
    RISK_ATTENDANCE,
    RISK_PERCENTAGE,
    SECRET_KEY,
    SESSION_COOKIE_SECURE,
    SESSION_LIFETIME_MINUTES,
    TERMS,
    validate_config,
)
from database import (
    add_subject,
    attendance_for_student,
    attendance_summary,
    count_audit_log,
    count_students,
    create_api_key,
    create_table,
    delete_api_key,
    delete_student_record,
    existing_signatures,
    fetch_all_students,
    fetch_attendance,
    fetch_audit_log,
    fetch_audit_log_detailed,
    fetch_deleted_students,
    fetch_details_map,
    fetch_student,
    fetch_student_details,
    fetch_students_page,
    find_api_key,
    insert_student,
    list_api_keys,
    mark_attendance,
    marks_for_subject,
    record_audit,
    remove_grade_rule,
    remove_subject,
    replace_marks,
    restore_student,
    search_students,
    set_grade_rule,
    set_subject_mark,
    set_subject_weight,
    set_term_mark,
    soft_delete_student,
    subject_names,
    subject_weights,
    term_marks_for_student,
    term_marks_grid,
    term_totals_by_term,
    touch_api_key,
    update_student_details,
    update_student_record,
)
from export import build_excel_bytes, export_to_csv
from grading import calculate, get_grade
from importer import import_students
from logging_setup import configure_logging
from mailer import MailNotConfigured, send_alert, send_report_card
from pdf_reports import build_report_cards_bytes, build_transcript_pdf
from reports import class_statistics, filter_students, sort_students
from risk import identify as identify_at_risk
from rules import dump_scale, load_rules, parse_scale
from rules import for_class as rules_for_class
from security import RateLimiter, apply_security_headers, client_ip
from transcripts import build_transcript, cumulative
from users import (
    create_user,
    delete_user,
    find_user,
    hash_token,
    list_users,
    seed_default_users,
    session_version,
    set_active,
    set_linked_reg_no,
    set_password,
    set_role,
    set_totp,
    verify_password,
)
from validators import validate_details

configure_logging()
logger = logging.getLogger("sgp.app")

app = Flask(__name__)
app.secret_key = SECRET_KEY
app.config.update(
    MAX_CONTENT_LENGTH=10 * 1024 * 1024,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=SESSION_COOKIE_SECURE,
    PERMANENT_SESSION_LIFETIME=timedelta(minutes=SESSION_LIFETIME_MINUTES),
)

csrf = CSRFProtect(app)

validate_config()
apply_security_headers(app)

login_limiter = RateLimiter(LOGIN_RATE_LIMIT)
api_limiter = RateLimiter(API_RATE_LIMIT)

app.jinja_env.globals["can"] = can

create_table()
seed_default_users()


@app.before_request
def _validate_session():
    """Log the user out if their account changed or the session expired."""
    username = session.get("username")
    if username and session.get("sv") != session_version(username):
        session.clear()
    return None


STUDENT_ALLOWED_ENDPOINTS = {
    "static", "login_page", "logout", "me_page",
    "me_transcript_page", "me_transcript_pdf", "change_password_page",
}


@app.before_request
def _restrict_student_scope():
    """Keep student accounts inside their own self-service pages."""
    if session.get("role") != "student":
        return None
    if request.endpoint in STUDENT_ALLOWED_ENDPOINTS:
        return None
    if request.endpoint == "index":
        return None
    return redirect(url_for("me_page"))


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def current_role():
    return session.get("role")


def current_username():
    return session.get("username", "")


def current_reg_no():
    return session.get("reg_no", "")


def audit(action, target="", details="", username=None):
    """Record an audit entry with the client's request metadata."""
    record_audit(
        username if username is not None else current_username(),
        action,
        target,
        details,
        ip=client_ip(request),
        user_agent=request.headers.get("User-Agent", ""),
    )


def subject_context():
    return {
        "subjects": subject_names(),
        "weights": subject_weights(),
        "max_mark": MAX_MARK,
        "pass_mark": PASS_MARK,
        "statuses": ATTENDANCE_STATUSES,
        "term_options": TERMS,
        "exam_options": EXAMS,
    }


def build_rows(students, rules=None):
    subjects = subject_names()
    weights = subject_weights()
    details = fetch_details_map()
    if rules is None:
        rules = load_rules()
    rows = []
    for row in students:
        marks = list(row[2:2 + len(subjects)])
        info = details.get(row[0], {})
        rule = rules_for_class(info.get("student_class", ""), rules)
        total, percentage, result = calculate(marks, weights, rule["pass_mark"])
        rows.append({
            "reg_no": row[0],
            "name": row[1],
            "marks": marks,
            "total": total,
            "percentage": percentage,
            "grade": get_grade(percentage, rule["grade_scale"]),
            "result": result,
            "student_class": info.get("student_class", ""),
            "section": info.get("section", ""),
            "term": info.get("term", ""),
        })
    return rows


def attendance_rates():
    """Return {reg_no: attendance percentage} across all recorded days."""
    rates = {}
    for reg_no, _name, present, total in attendance_summary():
        rates[reg_no] = round(present / total * 100, 1) if total else None
    return rates


def read_marks(form):
    marks = []
    for subject in subject_names():
        value = form.get(subject, "").strip()
        if not value.isdigit():
            return None, f"Enter valid marks for {subject}."
        mark = int(value)
        if mark < 0 or mark > MAX_MARK:
            return None, f"{subject} marks must be between 0 and {MAX_MARK}."
        marks.append(mark)
    return marks, ""


def read_details(form):
    return {
        "email": form.get("email", "").strip(),
        "phone": form.get("phone", "").strip(),
        "student_class": form.get("student_class", "").strip(),
        "section": form.get("section", "").strip(),
        "gender": form.get("gender", "").strip(),
        "dob": form.get("dob", "").strip(),
        "guardian": form.get("guardian", "").strip(),
        "academic_year": form.get("academic_year", "").strip(),
        "term": form.get("term", "").strip(),
    }


def add_imported_records(records):
    seen = existing_signatures()
    added = 0
    duplicates = []

    for name, marks in records:
        signature = (name.strip().lower(), tuple(marks))
        if signature in seen:
            duplicates.append(name)
            continue
        insert_student(name, marks)
        seen.add(signature)
        added += 1

    return added, duplicates


def _guard(action=None):
    if current_role() is None:
        return redirect(url_for("login_page"))
    if action and not can(current_role(), action):
        flash("Your role does not have permission to do that.")
        return redirect(url_for("index"))
    return None


def pagination(total, size=PAGE_SIZE):
    """Return (page, page_count, offset) clamped to the available range."""
    page_count = max(1, (total + size - 1) // size)
    raw = request.args.get("page", "1")
    page = int(raw) if raw.isdigit() and int(raw) > 0 else 1
    if page > page_count:
        page = page_count
    return page, page_count, (page - 1) * size


def require_api_token(required_scope=None):
    """Return None when the request carries a valid token, else a response.

    Accepts either the configured static token or a database-issued API key.
    """
    token = request.headers.get("X-API-Token", "")
    if not token:
        return jsonify({"error": "unauthorized", "detail": "Send a valid X-API-Token header."}), 401

    if hmac.compare_digest(token, API_TOKEN):
        return None

    key = find_api_key(hash_token(token))
    if key is None or not key["is_active"]:
        return jsonify({"error": "unauthorized", "detail": "Send a valid X-API-Token header."}), 401

    if key["expires_at"]:
        try:
            expiry = datetime.datetime.fromisoformat(key["expires_at"])
        except ValueError:
            expiry = None
        if expiry and expiry < datetime.datetime.now():
            return jsonify({"error": "unauthorized", "detail": "API key has expired."}), 401

    if required_scope and required_scope not in key["scopes"].split(","):
        return jsonify({"error": "forbidden", "detail": "API key lacks the required scope."}), 403

    touch_api_key(key["id"])
    return None


def api_page():
    raw = request.args.get("page", "1")
    return int(raw) if raw.isdigit() and int(raw) > 0 else 1


def api_page_size():
    """Page size for the JSON API, capped so a client cannot request everything."""
    raw = request.args.get("page_size", str(PAGE_SIZE))
    size = int(raw) if raw.isdigit() and int(raw) > 0 else PAGE_SIZE
    return min(size, 100)


# --------------------------------------------------------------------------- #
# auth
# --------------------------------------------------------------------------- #
@app.route("/login", methods=["GET", "POST"])
def login_page():
    if request.method == "POST":
        if not login_limiter.allow(client_ip(request)):
            flash("Too many login attempts from your address. Please wait a moment.")
            return render_template("login.html", role=current_role()), 429

        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        remaining = lockout_remaining(username)
        if remaining > 0:
            flash(f"Too many failed attempts. Try again in {remaining} seconds.")
        else:
            role = login(username, password)

            if role is None:
                flash("Invalid username or password.")
                audit("login_failed", username=username)
            else:
                user = find_user(username) or {}
                if user.get("totp_enabled"):
                    session.clear()
                    session["pending_2fa"] = username
                    session.permanent = True
                    return redirect(url_for("two_factor_verify_page"))
                _start_session(username, role, user.get("linked_reg_no", ""))
                audit("login", username=username)
                return redirect(url_for("dashboard_page"))

    return render_template("login.html", role=current_role())


def _start_session(username, role, reg_no):
    """Establish a fully authenticated session for a user."""
    session.clear()
    session["username"] = username
    session["role"] = role
    session["reg_no"] = reg_no
    session["sv"] = session_version(username)
    session.permanent = True


@app.route("/2fa/verify", methods=["GET", "POST"])
def two_factor_verify_page():
    username = session.get("pending_2fa")
    if not username:
        return redirect(url_for("login_page"))

    if request.method == "POST":
        code = request.form.get("code", "").strip()
        user = find_user(username) or {}
        if totp.verify(user.get("totp_secret", ""), code):
            _start_session(username, user.get("role", ""), user.get("linked_reg_no", ""))
            audit("login_2fa", username=username)
            return redirect(url_for("dashboard_page"))
        flash("That code is not valid. Try again.")
        audit("login_2fa_failed", username=username)

    return render_template("two_factor_verify.html", role=None)


@app.route("/2fa", methods=["GET", "POST"])
def two_factor_page():
    if current_role() is None:
        return redirect(url_for("login_page"))

    username = current_username()
    user = find_user(username) or {}
    secret = user.get("totp_secret", "")

    if request.method == "POST":
        if request.form.get("action") == "disable":
            set_totp(username, "", False)
            audit("disable_2fa", username)
            flash("Two-factor login disabled.")
            return redirect(url_for("two_factor_page"))

        if not secret:
            secret = totp.generate_secret()
            set_totp(username, secret, False)
        if totp.verify(secret, request.form.get("code", "").strip()):
            set_totp(username, secret, True)
            audit("enable_2fa", username)
            flash("Two-factor login enabled.")
        else:
            flash("That code is not valid. Check your authenticator app and try again.")
        return redirect(url_for("two_factor_page"))

    if not secret:
        secret = totp.generate_secret()
        set_totp(username, secret, False)

    return render_template(
        "two_factor.html",
        secret=secret,
        uri=totp.provisioning_uri(secret, username),
        enabled=user.get("totp_enabled", False),
        role=current_role(),
    )


@app.route("/logout")
def logout():
    username = current_username()
    session.clear()
    if username:
        audit("logout", username=username)
    return redirect(url_for("login_page"))


@app.route("/password", methods=["GET", "POST"])
def change_password_page():
    if current_role() is None:
        return redirect(url_for("login_page"))

    if request.method == "POST":
        current = request.form.get("current_password", "")
        new = request.form.get("new_password", "")
        confirm = request.form.get("confirm_password", "")

        user = find_user(current_username())
        if user is None or not verify_password(user["password_hash"], current):
            flash("Your current password is incorrect.")
        elif len(new) < 8:
            flash("The new password must be at least 8 characters.")
        elif new != confirm:
            flash("The two new passwords do not match.")
        elif verify_password(user["password_hash"], new):
            flash("The new password must be different from the current one.")
        else:
            set_password(current_username(), new)
            audit("change_password", current_username())
            session["sv"] = session_version(current_username())
            flash("Password updated.")
            return redirect(url_for("index") if current_role() != "student" else url_for("me_page"))

    return render_template("change_password.html", role=current_role())


# --------------------------------------------------------------------------- #
# students
# --------------------------------------------------------------------------- #
@app.route("/")
def index():
    if current_role() is None:
        return redirect(url_for("login_page"))
    if current_role() == "student":
        return redirect(url_for("me_page"))

    sort_by = request.args.get("sort", "reg_no")
    result_filter = request.args.get("filter", "all")
    keyword = request.args.get("q", "").strip()
    class_filter = request.args.get("class", "").strip()
    section_filter = request.args.get("section", "").strip()
    term_filter = request.args.get("term", "").strip()

    details = fetch_details_map()
    students = search_students(keyword) if keyword != "" else fetch_all_students()

    if class_filter:
        students = [r for r in students if details.get(r[0], {}).get("student_class", "") == class_filter]
    if section_filter:
        students = [r for r in students if details.get(r[0], {}).get("section", "") == section_filter]
    if term_filter:
        students = [r for r in students if details.get(r[0], {}).get("term", "") == term_filter]

    weights = subject_weights()
    students = filter_students(sort_students(students, sort_by, weights), result_filter)

    total = len(students)
    page_count = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)

    page = request.args.get("page", "1")
    page = int(page) if page.isdigit() and int(page) > 0 else 1
    if page > page_count:
        page = page_count

    start = (page - 1) * PAGE_SIZE
    page_students = students[start:start + PAGE_SIZE]

    classes = sorted({d.get("student_class", "") for d in details.values() if d.get("student_class")})
    sections = sorted({d.get("section", "") for d in details.values() if d.get("section")})
    terms = sorted({d.get("term", "") for d in details.values() if d.get("term")})

    return render_template(
        "index.html",
        students=build_rows(page_students),
        sort_by=sort_by,
        result_filter=result_filter,
        keyword=keyword,
        class_filter=class_filter,
        section_filter=section_filter,
        term_filter=term_filter,
        classes=classes,
        sections=sections,
        terms=terms,
        total=total,
        page=page,
        page_count=page_count,
        can_delete=can(current_role(), "delete"),
        role=current_role(),
        **subject_context(),
    )


@app.route("/add", methods=["GET", "POST"])
def add_student_page():
    if current_role() is None:
        return redirect(url_for("login_page"))

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        marks, error = read_marks(request.form)
        details = read_details(request.form)
        detail_errors = validate_details(details)

        if name == "":
            flash("Student name is required.")
        elif error != "":
            flash(error)
        elif detail_errors:
            for message in detail_errors:
                flash(message)
        else:
            reg_no = insert_student(name, marks, details)
            audit("add_student", reg_no, name)
            flash(f"Student {name} added with registration number {reg_no}.")
            return redirect(url_for("index"))

    return render_template("form.html", student=None, details={}, role=current_role(), **subject_context())


@app.route("/edit/<reg_no>", methods=["GET", "POST"])
def edit_student_page(reg_no):
    if current_role() is None:
        return redirect(url_for("login_page"))

    row = fetch_student(reg_no)
    if row is None:
        flash("Student not found.")
        return redirect(url_for("index"))

    subjects = subject_names()
    student = {"reg_no": row[0], "name": row[1], "marks": list(row[2:2 + len(subjects)])}

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        marks, error = read_marks(request.form)
        details = read_details(request.form)
        detail_errors = validate_details(details)

        if name == "":
            flash("Student name is required.")
        elif error != "":
            flash(error)
        elif detail_errors:
            for message in detail_errors:
                flash(message)
        else:
            update_student_record(reg_no, name, marks)
            update_student_details(reg_no, details)
            audit("update_student", reg_no, name)
            flash("Record updated successfully.")
            return redirect(url_for("index"))

    return render_template(
        "form.html",
        student=student,
        details=fetch_student_details(reg_no) or {},
        role=current_role(),
        **subject_context(),
    )


@app.route("/delete/<reg_no>", methods=["POST"])
def delete_student_page(reg_no):
    guard = _guard("delete")
    if guard:
        return guard

    soft_delete_student(reg_no)
    audit("delete_student", reg_no)
    flash("Record moved to the archive. Restore it from the Archive page.")
    return redirect(url_for("index"))


@app.route("/archive")
def archive_page():
    guard = _guard("archive")
    if guard:
        return guard

    deleted = fetch_deleted_students()
    page, page_count, offset = pagination(len(deleted))
    return render_template(
        "archive.html",
        students=build_rows(deleted[offset:offset + PAGE_SIZE]),
        page=page,
        page_count=page_count,
        role=current_role(),
        **subject_context(),
    )


@app.route("/restore/<reg_no>", methods=["POST"])
def restore_student_page(reg_no):
    guard = _guard("archive")
    if guard:
        return guard

    restore_student(reg_no)
    audit("restore_student", reg_no)
    flash("Record restored.")
    return redirect(url_for("archive_page"))


@app.route("/purge/<reg_no>", methods=["POST"])
def purge_student_page(reg_no):
    guard = _guard("delete")
    if guard:
        return guard

    delete_student_record(reg_no)
    audit("purge_student", reg_no)
    flash("Record permanently deleted.")
    return redirect(url_for("archive_page"))


# --------------------------------------------------------------------------- #
# dashboard
# --------------------------------------------------------------------------- #
def cohort_trend_points():
    """Average percentage per term across the whole cohort."""
    points = []
    for term, (earned, recorded) in sorted(term_totals_by_term().items()):
        maximum = recorded * MAX_MARK
        points.append({
            "term": term,
            "percentage": round(earned / maximum * 100, 2) if maximum else 0.0,
        })
    return points


@app.route("/dashboard")
def dashboard_page():
    if current_role() is None:
        return redirect(url_for("login_page"))
    if current_role() == "student":
        return redirect(url_for("me_page"))

    rules = load_rules()
    students = fetch_all_students()
    rows = build_rows(students, rules)
    summary = class_statistics(students, subject_weights())
    flagged = identify_at_risk(rows, attendance_rates(), PASS_MARK)

    distribution = grade_distribution(rows)
    max_count = max([count for _grade, count in distribution] + [1])

    return render_template(
        "dashboard.html",
        total_students=len(rows),
        average=cohort_average(rows),
        pass_rate=round(summary["pass_percentage"], 1),
        at_risk_count=len(flagged),
        at_risk=flagged[:5],
        distribution=distribution,
        max_count=max_count,
        trend=term_trend(cohort_trend_points()),
        role=current_role(),
        **subject_context(),
    )


# --------------------------------------------------------------------------- #
# reporting and stats
# --------------------------------------------------------------------------- #
@app.route("/stats")
def stats_page():
    if current_role() is None:
        return redirect(url_for("login_page"))

    students = fetch_all_students()
    weights = subject_weights()
    summary = class_statistics(students, weights)

    grade_counts = {}
    for row in students:
        marks = list(row[2:])
        percentage = calculate(marks, weights)[1]
        grade = get_grade(percentage)
        grade_counts[grade] = grade_counts.get(grade, 0) + 1

    order = ["A+", "A", "B+", "B", "C", "D", "F"]
    grade_distribution = [(grade, grade_counts.get(grade, 0)) for grade in order]
    max_count = max([count for _grade, count in grade_distribution] + [1])

    return render_template(
        "stats.html",
        stats=summary,
        grade_distribution=grade_distribution,
        max_count=max_count,
        role=current_role(),
        **subject_context(),
    )


@app.route("/student/<reg_no>")
def report_page(reg_no):
    if current_role() is None:
        return redirect(url_for("login_page"))

    row = fetch_student(reg_no)
    if row is None:
        flash("Student not found.")
        return redirect(url_for("index"))

    attendance = attendance_for_student(reg_no)
    present = sum(1 for _day, status in attendance if status == "present")
    attendance_rate = round(present / len(attendance) * 100, 1) if attendance else None

    return render_template(
        "report.html",
        student=build_rows([row])[0],
        details=fetch_student_details(reg_no) or {},
        history=fetch_audit_log(50, target=reg_no),
        attendance=attendance,
        attendance_rate=attendance_rate,
        trend=term_trend(_transcript_parts(reg_no)[0]),
        role=current_role(),
        **subject_context(),
    )


# --------------------------------------------------------------------------- #
# at-risk students and guardian alerts
# --------------------------------------------------------------------------- #
@app.route("/at-risk")
def at_risk_page():
    guard = _guard("risk")
    if guard:
        return guard

    rules = load_rules()
    rows = build_rows(fetch_all_students(), rules)
    flagged = identify_at_risk(rows, attendance_rates(), PASS_MARK)

    return render_template(
        "at_risk.html",
        students=flagged,
        risk_percentage=RISK_PERCENTAGE,
        risk_attendance=RISK_ATTENDANCE,
        role=current_role(),
        **subject_context(),
    )


@app.route("/at-risk/notify/<reg_no>", methods=["POST"])
def notify_guardian_page(reg_no):
    guard = _guard("email")
    if guard:
        return guard

    row = fetch_student(reg_no)
    if row is None:
        flash("Student not found.")
        return redirect(url_for("at_risk_page"))

    details = fetch_student_details(reg_no) or {}
    recipient = details.get("email", "")
    if not recipient:
        flash("This student has no guardian email address on file.")
        return redirect(url_for("at_risk_page"))

    student = build_rows([row])[0]
    rate = attendance_rates().get(reg_no)
    html = (
        f"<h2>Academic alert</h2><p><b>{student['name']}</b> ({student['reg_no']})</p>"
        f"<p>Overall percentage: {student['percentage']:.2f}% &nbsp; Grade: {student['grade']}"
        f" &nbsp; Result: {student['result']}</p>"
        f"<p>Attendance: {rate if rate is not None else 'not recorded'}%</p>"
        "<p>Please contact the school office to discuss extra support.</p>"
    )
    try:
        send_alert(recipient, student["name"], html)
    except MailNotConfigured as error:
        flash(str(error))
        return redirect(url_for("at_risk_page"))
    except Exception as error:  # noqa: BLE001 - surface SMTP failures to the user
        logger.exception("Failed to send guardian alert for %s", reg_no)
        flash(f"Could not send the alert: {error}")
        return redirect(url_for("at_risk_page"))

    audit("guardian_alert", reg_no, recipient)
    flash(f"Guardian alert sent to {recipient}.")
    return redirect(url_for("at_risk_page"))


# --------------------------------------------------------------------------- #
# student self-service
# --------------------------------------------------------------------------- #
def _student_self_context():
    reg_no = current_reg_no()
    if reg_no == "":
        return None, None
    row = fetch_student(reg_no)
    if row is None:
        return None, None

    attendance = attendance_for_student(reg_no)
    present = sum(1 for _day, status in attendance if status == "present")
    attendance_rate = round(present / len(attendance) * 100, 1) if attendance else None
    return row, {
        "student": build_rows([row])[0],
        "details": fetch_student_details(reg_no) or {},
        "attendance": attendance,
        "attendance_rate": attendance_rate,
    }


@app.route("/me")
def me_page():
    if current_role() is None:
        return redirect(url_for("login_page"))

    row, context = _student_self_context()
    if row is None:
        flash("Your account is not linked to a student record yet. Please contact the office.")
        return render_template("me.html", student=None, details={}, attendance=[], attendance_rate=None,
                               role=current_role(), **subject_context())

    return render_template("me.html", role=current_role(), **context, **subject_context())


@app.route("/me/transcript")
def me_transcript_page():
    if current_role() is None:
        return redirect(url_for("login_page"))

    row, context = _student_self_context()
    if row is None:
        flash("Your account is not linked to a student record yet.")
        return redirect(url_for("me_page"))

    terms, overall = _transcript_parts(row[0])
    return render_template(
        "transcript.html",
        student={"reg_no": row[0], "name": row[1]},
        details=context["details"],
        terms=terms,
        overall=overall,
        trend=term_trend(terms),
        exams=EXAMS,
        self_view=True,
        role=current_role(),
        **subject_context(),
    )


@app.route("/me/transcript.pdf")
def me_transcript_pdf_page():
    if current_role() is None:
        return redirect(url_for("login_page"))

    row, context = _student_self_context()
    if row is None:
        flash("Your account is not linked to a student record yet.")
        return redirect(url_for("me_page"))

    terms, overall = _transcript_parts(row[0])
    payload = build_transcript_pdf(
        {"reg_no": row[0], "name": row[1]},
        context["details"],
        terms,
        overall,
        EXAMS,
        MAX_MARK,
    )
    return Response(
        payload,
        mimetype="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=transcript-{row[0]}.pdf"},
    )


# --------------------------------------------------------------------------- #
# marks entry grid
# --------------------------------------------------------------------------- #
@app.route("/marks", methods=["GET", "POST"])
def marks_page():
    guard = _guard("marks")
    if guard:
        return guard

    subjects = subject_names()
    subject = request.form.get("subject") or request.args.get("subject") or (subjects[0] if subjects else "")
    if subject not in subjects:
        subject = subjects[0] if subjects else ""

    if request.method == "POST":
        saved = 0
        for student in fetch_all_students():
            reg_no = student[0]
            value = request.form.get("mark_" + reg_no, "").strip()
            if value == "":
                continue
            if not value.isdigit() or not (0 <= int(value) <= MAX_MARK):
                flash(f"Invalid mark for {reg_no}; it was skipped.")
                continue
            set_subject_mark(reg_no, subject, int(value))
            saved += 1
        audit("marks_entry", subject, f"{saved} saved")
        flash(f"Saved {saved} mark(s) for {subject}.")
        return redirect(url_for("marks_page", subject=subject))

    current = marks_for_subject(subject)
    students = [{"reg_no": row[0], "name": row[1], "mark": current.get(row[0], "")} for row in fetch_all_students()]

    return render_template(
        "marks.html",
        subject=subject,
        students=students,
        role=current_role(),
        **subject_context(),
    )


# --------------------------------------------------------------------------- #
# term-wise marks and transcripts
# --------------------------------------------------------------------------- #
@app.route("/term-marks", methods=["GET", "POST"])
def term_marks_page():
    guard = _guard("marks")
    if guard:
        return guard

    subjects = subject_names()
    term = request.form.get("term") or request.args.get("term") or (TERMS[0] if TERMS else "")
    exam = request.form.get("exam") or request.args.get("exam") or (EXAMS[0] if EXAMS else "")
    if term not in TERMS:
        term = TERMS[0] if TERMS else ""
    if exam not in EXAMS:
        exam = EXAMS[0] if EXAMS else ""

    if request.method == "POST":
        saved = 0
        for student in fetch_all_students():
            reg_no = student[0]
            for index, subject in enumerate(subjects):
                value = request.form.get(f"mark_{reg_no}_{index}", "").strip()
                if value == "":
                    continue
                if not value.isdigit() or not (0 <= int(value) <= MAX_MARK):
                    flash(f"Invalid mark for {reg_no} / {subject}; it was skipped.")
                    continue
                set_term_mark(reg_no, subject, term, exam, int(value))
                saved += 1
        audit("term_marks_entry", f"{term} / {exam}", f"{saved} saved")
        flash(f"Saved {saved} term mark(s) for {term} - {exam}.")
        return redirect(url_for("term_marks_page", term=term, exam=exam))

    grid = term_marks_grid(term, exam)
    students = []
    for row in fetch_all_students():
        stored = grid.get(row[0], {})
        students.append({
            "reg_no": row[0],
            "name": row[1],
            "marks": [stored.get(subject, "") for subject in subjects],
        })

    return render_template(
        "term_marks.html",
        term=term,
        exam=exam,
        students=students,
        role=current_role(),
        **subject_context(),
    )


def _transcript_parts(reg_no):
    terms = build_transcript(term_marks_for_student(reg_no), subject_names(), EXAMS)
    return terms, cumulative(terms)


@app.route("/student/<reg_no>/transcript")
def transcript_page(reg_no):
    guard = _guard("transcripts")
    if guard:
        return guard

    row = fetch_student(reg_no)
    if row is None:
        flash("Student not found.")
        return redirect(url_for("index"))

    terms, overall = _transcript_parts(reg_no)
    return render_template(
        "transcript.html",
        student={"reg_no": row[0], "name": row[1]},
        details=fetch_student_details(reg_no) or {},
        terms=terms,
        overall=overall,
        trend=term_trend(terms),
        exams=EXAMS,
        role=current_role(),
        **subject_context(),
    )


@app.route("/student/<reg_no>/transcript.pdf")
def transcript_pdf_page(reg_no):
    guard = _guard("transcripts")
    if guard:
        return guard

    row = fetch_student(reg_no)
    if row is None:
        flash("Student not found.")
        return redirect(url_for("index"))

    terms, overall = _transcript_parts(reg_no)
    payload = build_transcript_pdf(
        {"reg_no": row[0], "name": row[1]},
        fetch_student_details(reg_no) or {},
        terms,
        overall,
        EXAMS,
        MAX_MARK,
    )
    return Response(
        payload,
        mimetype="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=transcript-{reg_no}.pdf"},
    )


# --------------------------------------------------------------------------- #
# attendance
# --------------------------------------------------------------------------- #
@app.route("/attendance", methods=["GET", "POST"])
def attendance_page():
    guard = _guard("attendance")
    if guard:
        return guard

    day = request.form.get("day") or request.args.get("day") or datetime.date.today().isoformat()

    if request.method == "POST":
        default_status = request.form.get("default_status", "").strip()
        saved = 0
        for student in fetch_all_students():
            reg_no = student[0]
            status = request.form.get("status_" + reg_no, "").strip() or default_status
            if status in ATTENDANCE_STATUSES:
                mark_attendance(reg_no, day, status)
                saved += 1
        audit("attendance", day, f"{saved} marked")
        flash(f"Attendance saved for {day}.")
        return redirect(url_for("attendance_page", day=day))

    existing = {reg_no: status for reg_no, _name, status in fetch_attendance(day)}
    students = [
        {"reg_no": row[0], "name": row[1], "status": existing.get(row[0], "")}
        for row in fetch_all_students()
    ]

    return render_template(
        "attendance.html",
        day=day,
        students=students,
        summary=attendance_summary(),
        role=current_role(),
        **subject_context(),
    )


# --------------------------------------------------------------------------- #
# subjects admin
# --------------------------------------------------------------------------- #
@app.route("/subjects")
def subjects_page():
    guard = _guard("subjects")
    if guard:
        return guard

    from database import get_subjects

    return render_template(
        "subjects.html",
        subjects=get_subjects(),
        role=current_role(),
    )


@app.route("/subjects/add", methods=["POST"])
def add_subject_page():
    guard = _guard("subjects")
    if guard:
        return guard

    name = request.form.get("name", "").strip()
    if name == "":
        flash("Subject name is required.")
    elif add_subject(name):
        audit("add_subject", name)
        flash(f"Subject {name} added.")
    else:
        flash(f"Subject {name} already exists.")
    return redirect(url_for("subjects_page"))


@app.route("/subjects/remove", methods=["POST"])
def remove_subject_page():
    guard = _guard("subjects")
    if guard:
        return guard

    name = request.form.get("name", "").strip()
    remove_subject(name)
    audit("remove_subject", name)
    flash(f"Subject {name} removed.")
    return redirect(url_for("subjects_page"))


@app.route("/subjects/weight", methods=["POST"])
def subject_weight_page():
    guard = _guard("subjects")
    if guard:
        return guard

    name = request.form.get("name", "").strip()
    value = request.form.get("weight", "").strip()
    try:
        weight = float(value)
    except ValueError:
        weight = 0.0
    if weight <= 0:
        flash("Weight must be a positive number.")
    else:
        set_subject_weight(name, weight)
        audit("set_subject_weight", name, str(weight))
        flash(f"Weight for {name} set to {weight}.")
    return redirect(url_for("subjects_page"))


# --------------------------------------------------------------------------- #
# grade rules admin
# --------------------------------------------------------------------------- #
@app.route("/grade-rules")
def grade_rules_page():
    guard = _guard("graderules")
    if guard:
        return guard

    rules = load_rules()
    display = sorted(
        (
            student_class,
            rule["pass_mark"],
            "\n".join(f"{minimum} {grade}" for minimum, grade in rule["grade_scale"]),
        )
        for student_class, rule in rules.items()
    )
    classes = sorted({
        info.get("student_class", "")
        for info in fetch_details_map().values()
        if info.get("student_class")
    })

    return render_template(
        "grade_rules.html",
        rules=display,
        classes=classes,
        default_scale="\n".join(f"{minimum} {grade}" for minimum, grade in GRADE_SCALE),
        role=current_role(),
        **subject_context(),
    )


@app.route("/grade-rules/set", methods=["POST"])
def set_grade_rule_page():
    guard = _guard("graderules")
    if guard:
        return guard

    student_class = request.form.get("student_class", "").strip()
    value = request.form.get("pass_mark", "").strip()
    scale = parse_scale(request.form.get("grade_scale", ""))

    if student_class == "":
        flash("Enter a class name.")
    elif not value.isdigit() or not (0 <= int(value) <= MAX_MARK):
        flash(f"The pass mark must be a whole number between 0 and {MAX_MARK}.")
    elif not scale:
        flash("Enter at least one line for the grade scale, for example '90 A+'.")
    else:
        set_grade_rule(student_class, int(value), dump_scale(scale))
        audit("set_grade_rule", student_class, value)
        flash(f"Grade rules saved for {student_class}.")
    return redirect(url_for("grade_rules_page"))


@app.route("/grade-rules/remove", methods=["POST"])
def remove_grade_rule_page():
    guard = _guard("graderules")
    if guard:
        return guard

    student_class = request.form.get("student_class", "").strip()
    remove_grade_rule(student_class)
    audit("remove_grade_rule", student_class)
    flash(f"Grade rules for {student_class} removed; the default scale applies again.")
    return redirect(url_for("grade_rules_page"))


# --------------------------------------------------------------------------- #
# import and export
# --------------------------------------------------------------------------- #
@app.route("/import", methods=["GET", "POST"])
def import_page():
    if current_role() is None:
        return redirect(url_for("login_page"))

    if not can(current_role(), "import"):
        flash("Your role does not have permission to import records.")
        return redirect(url_for("index"))

    if request.method == "POST":
        upload = request.files.get("file")

        if upload is None or upload.filename == "":
            flash("Please choose a file to upload.")
            return redirect(url_for("import_page"))

        suffix = os.path.splitext(upload.filename)[1].lower()
        handle, path = tempfile.mkstemp(suffix=suffix)
        os.close(handle)

        try:
            upload.save(path)
            records, errors = import_students(path)
        except ValueError as error:
            flash(str(error))
            return redirect(url_for("import_page"))
        finally:
            if os.path.exists(path):
                os.remove(path)

        if len(records) == 0:
            flash("No valid student rows were found in the file.")
        else:
            added, duplicates = add_imported_records(records)
            record_audit(
                current_username(), "import", upload.filename,
                f"{added} added, {len(duplicates)} duplicates",
            )
            flash(f"Imported {added} of {len(records)} students from {upload.filename}.")
            if duplicates:
                flash("Skipped " + str(len(duplicates)) + " duplicate students: " + ", ".join(duplicates[:5]))

        for error in errors[:10]:
            flash(error)

        return redirect(url_for("index"))

    return render_template("import.html", role=current_role(), **subject_context())


@app.route("/template")
def template_page():
    if current_role() is None:
        return redirect(url_for("login_page"))

    subjects = subject_names()
    rows = ["Name," + ",".join(subjects)]
    rows.append("Sample Student," + ",".join(["40"] * len(subjects)))
    content = "\n".join(rows) + "\n"

    return Response(
        content,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=student_import_template.csv"},
    )


@app.route("/export")
def export_page():
    if current_role() is None:
        return redirect(url_for("login_page"))

    export_to_csv()
    return send_file(os.path.abspath(CSV_FILE), as_attachment=True)


@app.route("/export/excel")
def export_excel_page():
    if current_role() is None:
        return redirect(url_for("login_page"))

    return Response(
        build_excel_bytes(),
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=student_records.xlsx"},
    )


@app.route("/export/pdf")
def export_pdf_page():
    if current_role() is None:
        return redirect(url_for("login_page"))

    subjects = subject_names()
    payload = build_report_cards_bytes(
        fetch_all_students(),
        fetch_details_map(),
        subjects,
        MAX_MARK,
        PASS_MARK,
        get_grade,
        lambda marks: "PASS" if all(mark >= PASS_MARK for mark in marks) else "FAIL",
    )
    return Response(
        payload,
        mimetype="application/pdf",
        headers={"Content-Disposition": "attachment; filename=report_cards.pdf"},
    )


# --------------------------------------------------------------------------- #
# audit and users
# --------------------------------------------------------------------------- #
@app.route("/audit")
def audit_page():
    guard = _guard("audit")
    if guard:
        return guard

    total = count_audit_log()
    page, page_count, offset = pagination(total)
    return render_template(
        "audit.html",
        entries=fetch_audit_log_detailed(PAGE_SIZE, offset),
        page=page,
        page_count=page_count,
        total=total,
        role=current_role(),
    )


@app.route("/users")
def users_page():
    guard = _guard("users")
    if guard:
        return guard

    return render_template("users.html", users=list_users(), role=current_role())


@app.route("/users/add", methods=["POST"])
def add_user_page():
    guard = _guard("users")
    if guard:
        return guard

    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")
    role = request.form.get("role", "faculty").strip()
    linked_reg_no = request.form.get("linked_reg_no", "").strip()

    if username == "" or password == "":
        flash("Username and password are required.")
    elif role not in ("admin", "faculty", "student"):
        flash("Unknown role.")
    elif role == "student" and (linked_reg_no == "" or fetch_student(linked_reg_no) is None):
        flash("Pick an existing registration number to link the student account to.")
    else:
        try:
            create_user(username, password, role, linked_reg_no if role == "student" else "")
            audit("create_user", username, role)
            flash(f"User {username} created.")
        except Exception:
            flash(f"User {username} already exists.")

    return redirect(url_for("users_page"))


@app.route("/users/<username>/role", methods=["POST"])
def change_user_role(username):
    guard = _guard("users")
    if guard:
        return guard

    role = request.form.get("role", "").strip()
    if role in ("admin", "faculty", "student"):
        set_role(username, role)
        if role == "student":
            linked_reg_no = request.form.get("linked_reg_no", "").strip()
            if linked_reg_no:
                set_linked_reg_no(username, linked_reg_no)
        audit("set_role", username, role)
        flash(f"{username} is now {role}.")
    return redirect(url_for("users_page"))


@app.route("/users/<username>/password", methods=["POST"])
def change_user_password(username):
    guard = _guard("users")
    if guard:
        return guard

    password = request.form.get("password", "")
    if password == "":
        flash("Password cannot be empty.")
    else:
        set_password(username, password)
        audit("set_password", username)
        flash(f"Password updated for {username}.")
    return redirect(url_for("users_page"))


@app.route("/users/<username>/toggle", methods=["POST"])
def toggle_user(username):
    guard = _guard("users")
    if guard:
        return guard

    active = request.form.get("active") == "1"
    set_active(username, active)
    audit("set_active", username, str(active))
    flash(f"{username} {'enabled' if active else 'disabled'}.")
    return redirect(url_for("users_page"))


@app.route("/users/<username>/delete", methods=["POST"])
def remove_user(username):
    guard = _guard("users")
    if guard:
        return guard

    if username == current_username():
        flash("You cannot delete the account you are signed in with.")
    else:
        delete_user(username)
        audit("delete_user", username)
        flash(f"User {username} deleted.")
    return redirect(url_for("users_page"))


# --------------------------------------------------------------------------- #
# api keys
# --------------------------------------------------------------------------- #
@app.route("/api-keys")
def api_keys_page():
    guard = _guard("apikeys")
    if guard:
        return guard

    return render_template("api_keys.html", keys=list_api_keys(), role=current_role())


@app.route("/api-keys/create", methods=["POST"])
def create_api_key_page():
    guard = _guard("apikeys")
    if guard:
        return guard

    name = request.form.get("name", "").strip()
    scopes = ",".join(s for s in request.form.getlist("scopes") if s in ("read", "write")) or "read"
    expires_at = request.form.get("expires_at", "").strip() or None

    if name == "":
        flash("A key name is required.")
        return redirect(url_for("api_keys_page"))

    raw = "sgp_" + secrets.token_urlsafe(24)
    create_api_key(name, hash_token(raw), scopes, expires_at)
    audit("create_api_key", name, scopes)
    flash(f"Key created ({scopes}). Copy it now, it is not shown again: {raw}")
    return redirect(url_for("api_keys_page"))


@app.route("/api-keys/<int:key_id>/delete", methods=["POST"])
def delete_api_key_page(key_id):
    guard = _guard("apikeys")
    if guard:
        return guard

    delete_api_key(key_id)
    audit("delete_api_key", str(key_id))
    flash("API key revoked.")
    return redirect(url_for("api_keys_page"))


# --------------------------------------------------------------------------- #
# email report card
# --------------------------------------------------------------------------- #
@app.route("/student/<reg_no>/email", methods=["POST"])
def email_report_card_page(reg_no):
    guard = _guard("email")
    if guard:
        return guard

    row = fetch_student(reg_no)
    if row is None:
        flash("Student not found.")
        return redirect(url_for("index"))

    details = fetch_student_details(reg_no) or {}
    recipient = details.get("email", "")
    if not recipient:
        flash("This student has no email address on file.")
        return redirect(url_for("report_page", reg_no=reg_no))

    student = build_rows([row])[0]
    html = (
        f"<h2>Report Card</h2><p><b>{student['name']}</b> ({student['reg_no']})</p>"
        f"<p>Total: {student['total']} &nbsp; Percentage: {student['percentage']:.2f}% &nbsp; "
        f"Grade: {student['grade']} &nbsp; Result: {student['result']}</p>"
    )
    try:
        send_report_card(recipient, row[1], f"Report card for {row[1]}", html)
    except MailNotConfigured as error:
        flash(str(error))
        return redirect(url_for("report_page", reg_no=reg_no))
    except Exception as error:  # noqa: BLE001 - surface SMTP failures to the user
        logger.exception("Failed to email report card for %s", reg_no)
        flash(f"Could not send the email: {error}")
        return redirect(url_for("report_page", reg_no=reg_no))

    audit("email_report_card", reg_no, recipient)
    flash(f"Report card emailed to {recipient}.")
    return redirect(url_for("report_page", reg_no=reg_no))


# --------------------------------------------------------------------------- #
# JSON API
# --------------------------------------------------------------------------- #
@app.route("/api/openapi.json")
def api_spec():
    spec = {
        "openapi": "3.0.0",
        "info": {"title": "Student Grade Portal API", "version": "1.0.0"},
        "servers": [{"url": "/"}],
        "components": {
            "securitySchemes": {
                "ApiToken": {"type": "apiKey", "in": "header", "name": "X-API-Token"}
            }
        },
        "paths": {
            "/api/students": {
                "get": {
                    "summary": "List students (paginated)",
                    "parameters": [
                        {"name": "page", "in": "query", "schema": {"type": "integer"}},
                        {"name": "page_size", "in": "query", "schema": {"type": "integer"}},
                    ],
                    "responses": {"200": {"description": "OK"}},
                },
                "post": {
                    "summary": "Create a student",
                    "requestBody": {
                        "required": True,
                        "content": {"application/json": {"schema": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string"},
                                "marks": {"type": "array", "items": {"type": "integer"}},
                            },
                            "required": ["name", "marks"],
                        }}},
                    },
                    "responses": {"201": {"description": "Created"}},
                },
            },
            "/api/students/{reg_no}": {
                "get": {"summary": "Fetch one student", "responses": {"200": {"description": "OK"}}},
                "patch": {"summary": "Partially update a student", "responses": {"200": {"description": "OK"}}},
                "delete": {"summary": "Delete one student", "responses": {"200": {"description": "OK"}}},
            },
            "/api/students/{reg_no}/marks": {
                "get": {"summary": "Fetch subject marks", "responses": {"200": {"description": "OK"}}},
                "put": {"summary": "Replace subject marks", "responses": {"200": {"description": "OK"}}},
            },
            "/healthz": {
                "get": {"summary": "Liveness and database check", "responses": {"200": {"description": "OK"}}},
            },
        },
    }
    return jsonify(spec)


@app.route("/api")
def api_docs_page():
    return render_template("api.html", role=current_role())


@app.route("/api/students", methods=["GET", "POST"])
@csrf.exempt
def api_students():
    if not api_limiter.allow(client_ip(request)):
        return jsonify({"error": "rate_limited", "detail": "Too many requests."}), 429

    error = require_api_token("read" if request.method == "GET" else "write")
    if error:
        return error

    if request.method == "GET":
        size = api_page_size()
        page = api_page()
        rows = fetch_students_page(size, (page - 1) * size)
        return jsonify({
            "students": build_rows(rows),
            "page": page,
            "page_size": size,
            "total": count_students(),
        })

    payload = request.get_json(silent=True) or {}
    name = str(payload.get("name", "")).strip()
    marks = payload.get("marks", [])

    subjects = subject_names()
    if name == "" or not isinstance(marks, list) or len(marks) != len(subjects):
        return jsonify({
            "error": "invalid_payload",
            "detail": f"Provide a name and {len(subjects)} marks (one per subject).",
        }), 400
    if any(not isinstance(mark, int) or mark < 0 or mark > MAX_MARK for mark in marks):
        return jsonify({"error": "invalid_marks", "detail": f"Marks must be 0-{MAX_MARK}."}), 400

    reg_no = insert_student(name, marks)
    audit("api_add_student", reg_no, name, username="api")
    return jsonify({"reg_no": reg_no, "name": name, "marks": marks}), 201


@app.route("/api/students/<reg_no>", methods=["GET", "PATCH", "DELETE"])
@csrf.exempt
def api_student(reg_no):
    if not api_limiter.allow(client_ip(request)):
        return jsonify({"error": "rate_limited", "detail": "Too many requests."}), 429

    error = require_api_token("read" if request.method == "GET" else "write")
    if error:
        return error

    row = fetch_student(reg_no)
    if row is None:
        return jsonify({"error": "not_found"}), 404

    if request.method == "DELETE":
        delete_student_record(reg_no)
        audit("api_delete_student", reg_no, username="api")
        return jsonify({"deleted": reg_no})

    if request.method == "PATCH":
        payload = request.get_json(silent=True) or {}
        subjects = subject_names()
        marks = payload.get("marks")

        if "name" in payload and str(payload["name"]).strip() == "":
            return jsonify({"error": "invalid_payload", "detail": "Name cannot be empty."}), 400
        if marks is not None and (
            not isinstance(marks, list)
            or len(marks) != len(subjects)
            or any(not isinstance(m, int) or m < 0 or m > MAX_MARK for m in marks)
        ):
            return jsonify({
                "error": "invalid_marks",
                "detail": f"Provide {len(subjects)} marks between 0 and {MAX_MARK}.",
            }), 400

        details = payload.get("details", {})
        if details:
            if not isinstance(details, dict):
                return jsonify({"error": "invalid_payload", "detail": "details must be an object."}), 400
            detail_errors = validate_details(details)
            if detail_errors:
                return jsonify({"error": "invalid_payload", "detail": detail_errors}), 400

        current_marks = list(row[2:2 + len(subjects)])
        if "name" in payload or marks is not None:
            name = str(payload["name"]).strip() if "name" in payload else row[1]
            update_student_record(reg_no, name, marks if marks is not None else current_marks)
        if details:
            update_student_details(reg_no, details)

        audit("api_patch_student", reg_no, username="api")
        return jsonify({
            "student": build_rows([fetch_student(reg_no)])[0],
            "details": fetch_student_details(reg_no),
        })

    return jsonify({"student": build_rows([row])[0], "details": fetch_student_details(reg_no)})


@app.route("/api/students/<reg_no>/marks", methods=["GET", "PUT"])
@csrf.exempt
def api_student_marks(reg_no):
    if not api_limiter.allow(client_ip(request)):
        return jsonify({"error": "rate_limited", "detail": "Too many requests."}), 429

    error = require_api_token("read" if request.method == "GET" else "write")
    if error:
        return error

    row = fetch_student(reg_no)
    if row is None:
        return jsonify({"error": "not_found"}), 404

    subjects = subject_names()
    if request.method == "GET":
        marks = list(row[2:2 + len(subjects)])
        return jsonify({"reg_no": reg_no, "marks": dict(zip(subjects, marks, strict=False))})

    payload = request.get_json(silent=True) or {}
    marks = payload.get("marks")
    if (
        not isinstance(marks, list)
        or len(marks) != len(subjects)
        or any(not isinstance(m, int) or m < 0 or m > MAX_MARK for m in marks)
    ):
        return jsonify({
            "error": "invalid_marks",
            "detail": f"Provide {len(subjects)} marks between 0 and {MAX_MARK}.",
        }), 400

    replace_marks(reg_no, marks)
    audit("api_set_marks", reg_no, username="api")
    return jsonify({"reg_no": reg_no, "marks": dict(zip(subjects, marks, strict=False))})


# --------------------------------------------------------------------------- #
# misc
# --------------------------------------------------------------------------- #
@app.route("/health")
def health():
    return {"status": "ok", "env": ENV}


@app.route("/healthz")
def healthz():
    """Liveness probe that also confirms the database is reachable."""
    try:
        count_students()
        database_ok = True
    except Exception:  # noqa: BLE001 - any failure means the service is unhealthy
        logger.exception("Health check could not reach the database")
        database_ok = False
    return jsonify({
        "status": "ok" if database_ok else "error",
        "database": database_ok,
        "env": ENV,
    }), (200 if database_ok else 503)


@app.errorhandler(404)
def not_found(error):
    return render_template("404.html", role=current_role()), 404


@app.errorhandler(500)
def server_error(error):
    logger.exception("Unhandled server error: %s", error)
    return render_template("500.html", role=current_role()), 500


@app.errorhandler(413)
def upload_too_large(error):
    flash("That file is too large. The maximum upload size is 10 MB.")
    return redirect(url_for("import_page"))


if __name__ == "__main__":
    app.run(debug=DEBUG)
