import datetime
import logging
import os
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

from auth import can, lockout_remaining, login
from config import (
    API_TOKEN,
    ATTENDANCE_STATUSES,
    CSV_FILE,
    DEBUG,
    ENV,
    MAX_MARK,
    PAGE_SIZE,
    PASS_MARK,
    SECRET_KEY,
    SESSION_COOKIE_SECURE,
    SESSION_LIFETIME_MINUTES,
)
from database import (
    add_subject,
    attendance_for_student,
    attendance_summary,
    create_table,
    delete_student_record,
    existing_signatures,
    fetch_all_students,
    fetch_attendance,
    fetch_audit_log,
    fetch_deleted_students,
    fetch_details_map,
    fetch_student,
    fetch_student_details,
    insert_student,
    mark_attendance,
    marks_for_subject,
    record_audit,
    remove_subject,
    restore_student,
    search_students,
    set_subject_mark,
    set_subject_weight,
    soft_delete_student,
    subject_names,
    subject_weights,
    update_student_details,
    update_student_record,
)
from export import build_csv_bytes, build_excel_bytes, export_to_csv
from grading import calculate, get_grade
from importer import import_students
from logging_setup import configure_logging
from pdf_reports import build_report_cards_bytes
from reports import class_statistics, filter_students, sort_students
from users import (
    create_user,
    delete_user,
    list_users,
    seed_default_users,
    set_active,
    set_password,
    set_role,
)

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

app.jinja_env.globals["can"] = can

create_table()
seed_default_users()


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def current_role():
    return session.get("role")


def current_username():
    return session.get("username", "")


def subject_context():
    return {
        "subjects": subject_names(),
        "weights": subject_weights(),
        "max_mark": MAX_MARK,
        "pass_mark": PASS_MARK,
        "statuses": ATTENDANCE_STATUSES,
    }


def build_rows(students):
    subjects = subject_names()
    weights = subject_weights()
    details = fetch_details_map()
    rows = []
    for row in students:
        marks = list(row[2:2 + len(subjects)])
        total, percentage, result = calculate(marks, weights)
        info = details.get(row[0], {})
        rows.append({
            "reg_no": row[0],
            "name": row[1],
            "marks": marks,
            "total": total,
            "percentage": percentage,
            "grade": get_grade(percentage),
            "result": result,
            "student_class": info.get("student_class", ""),
            "section": info.get("section", ""),
            "term": info.get("term", ""),
        })
    return rows


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


def require_api_token():
    """Return None when the request carries the right token, else a response."""
    token = request.headers.get("X-API-Token", "")
    if token and token == API_TOKEN:
        return None
    return jsonify({"error": "unauthorized", "detail": "Send a valid X-API-Token header."}), 401


# --------------------------------------------------------------------------- #
# auth
# --------------------------------------------------------------------------- #
@app.route("/login", methods=["GET", "POST"])
def login_page():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        remaining = lockout_remaining(username)
        if remaining > 0:
            flash(f"Too many failed attempts. Try again in {remaining} seconds.")
        else:
            role = login(username, password)

            if role is None:
                flash("Invalid username or password.")
                record_audit(username, "login_failed")
            else:
                session.clear()
                session["username"] = username
                session["role"] = role
                session.permanent = True
                record_audit(username, "login")
                return redirect(url_for("index"))

    return render_template("login.html", role=current_role())


@app.route("/logout")
def logout():
    username = current_username()
    session.clear()
    if username:
        record_audit(username, "logout")
    return redirect(url_for("login_page"))


# --------------------------------------------------------------------------- #
# students
# --------------------------------------------------------------------------- #
@app.route("/")
def index():
    if current_role() is None:
        return redirect(url_for("login_page"))

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

        if name == "":
            flash("Student name is required.")
        elif error != "":
            flash(error)
        else:
            reg_no = insert_student(name, marks, read_details(request.form))
            record_audit(current_username(), "add_student", reg_no, name)
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

        if name == "":
            flash("Student name is required.")
        elif error != "":
            flash(error)
        else:
            update_student_record(reg_no, name, marks)
            update_student_details(reg_no, read_details(request.form))
            record_audit(current_username(), "update_student", reg_no, name)
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
    record_audit(current_username(), "delete_student", reg_no)
    flash("Record moved to the archive. Restore it from the Archive page.")
    return redirect(url_for("index"))


@app.route("/archive")
def archive_page():
    guard = _guard("archive")
    if guard:
        return guard

    return render_template(
        "archive.html",
        students=build_rows(fetch_deleted_students()),
        role=current_role(),
        **subject_context(),
    )


@app.route("/restore/<reg_no>", methods=["POST"])
def restore_student_page(reg_no):
    guard = _guard("archive")
    if guard:
        return guard

    restore_student(reg_no)
    record_audit(current_username(), "restore_student", reg_no)
    flash("Record restored.")
    return redirect(url_for("archive_page"))


@app.route("/purge/<reg_no>", methods=["POST"])
def purge_student_page(reg_no):
    guard = _guard("delete")
    if guard:
        return guard

    delete_student_record(reg_no)
    record_audit(current_username(), "purge_student", reg_no)
    flash("Record permanently deleted.")
    return redirect(url_for("archive_page"))


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

    return render_template(
        "report.html",
        student=build_rows([row])[0],
        details=fetch_student_details(reg_no) or {},
        history=fetch_audit_log(50, target=reg_no),
        attendance=attendance_for_student(reg_no),
        role=current_role(),
        **subject_context(),
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
        record_audit(current_username(), "marks_entry", subject, f"{saved} saved")
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
# attendance
# --------------------------------------------------------------------------- #
@app.route("/attendance", methods=["GET", "POST"])
def attendance_page():
    guard = _guard("attendance")
    if guard:
        return guard

    day = request.form.get("day") or request.args.get("day") or datetime.date.today().isoformat()

    if request.method == "POST":
        saved = 0
        for student in fetch_all_students():
            reg_no = student[0]
            status = request.form.get("status_" + reg_no, "")
            if status in ATTENDANCE_STATUSES:
                mark_attendance(reg_no, day, status)
                saved += 1
        record_audit(current_username(), "attendance", day, f"{saved} marked")
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
        record_audit(current_username(), "add_subject", name)
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
    record_audit(current_username(), "remove_subject", name)
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
        record_audit(current_username(), "set_subject_weight", name, str(weight))
        flash(f"Weight for {name} set to {weight}.")
    return redirect(url_for("subjects_page"))


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

    return render_template("audit.html", entries=fetch_audit_log(200), role=current_role())


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

    if username == "" or password == "":
        flash("Username and password are required.")
    elif role not in ("admin", "faculty"):
        flash("Unknown role.")
    else:
        try:
            create_user(username, password, role)
            record_audit(current_username(), "create_user", username, role)
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
    if role in ("admin", "faculty"):
        set_role(username, role)
        record_audit(current_username(), "set_role", username, role)
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
        record_audit(current_username(), "set_password", username)
        flash(f"Password updated for {username}.")
    return redirect(url_for("users_page"))


@app.route("/users/<username>/toggle", methods=["POST"])
def toggle_user(username):
    guard = _guard("users")
    if guard:
        return guard

    active = request.form.get("active") == "1"
    set_active(username, active)
    record_audit(current_username(), "set_active", username, str(active))
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
        record_audit(current_username(), "delete_user", username)
        flash(f"User {username} deleted.")
    return redirect(url_for("users_page"))


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
                "get": {"summary": "List students", "responses": {"200": {"description": "OK"}}},
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
                "delete": {"summary": "Delete one student", "responses": {"200": {"description": "OK"}}},
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
    error = require_api_token()
    if error:
        return error

    if request.method == "GET":
        return jsonify({"students": build_rows(fetch_all_students())})

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
    record_audit("api", "api_add_student", reg_no, name)
    return jsonify({"reg_no": reg_no, "name": name, "marks": marks}), 201


@app.route("/api/students/<reg_no>", methods=["GET", "DELETE"])
@csrf.exempt
def api_student(reg_no):
    error = require_api_token()
    if error:
        return error

    row = fetch_student(reg_no)
    if row is None:
        return jsonify({"error": "not_found"}), 404

    if request.method == "DELETE":
        delete_student_record(reg_no)
        record_audit("api", "api_delete_student", reg_no)
        return jsonify({"deleted": reg_no})

    return jsonify({"student": build_rows([row])[0], "details": fetch_student_details(reg_no)})


# --------------------------------------------------------------------------- #
# misc
# --------------------------------------------------------------------------- #
@app.route("/health")
def health():
    return {"status": "ok", "env": ENV}


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
