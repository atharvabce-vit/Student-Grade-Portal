import os
import tempfile

from flask import (
    Flask,
    Response,
    flash,
    redirect,
    render_template,
    request,
    send_file,
    session,
    url_for,
)

from auth import can, login
from config import CSV_FILE, MAX_MARK, SUBJECTS
from database import (
    create_table,
    delete_student_record,
    fetch_all_students,
    fetch_student,
    insert_student,
    search_students,
    update_student_record,
)
from export import export_to_csv
from grading import calculate, get_grade
from importer import import_students
from reports import class_statistics, filter_students, sort_students

app = Flask(__name__)
app.secret_key = "student-grade-portal-secret-key"
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024

create_table()


def current_role():
    return session.get("role")


def build_rows(students):
    rows = []
    for row in students:
        marks = list(row[2:2 + len(SUBJECTS)])
        total, percentage, result = calculate(marks)
        rows.append({
            "reg_no": row[0],
            "name": row[1],
            "marks": marks,
            "total": total,
            "percentage": percentage,
            "grade": get_grade(percentage),
            "result": result,
        })
    return rows


def read_marks(form):
    marks = []
    for subject in SUBJECTS:
        value = form.get(subject, "").strip()
        if not value.isdigit():
            return None, f"Enter valid marks for {subject}."
        mark = int(value)
        if mark < 0 or mark > MAX_MARK:
            return None, f"{subject} marks must be between 0 and {MAX_MARK}."
        marks.append(mark)
    return marks, ""


@app.route("/login", methods=["GET", "POST"])
def login_page():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        role = login(username, password)

        if role is None:
            flash("Invalid username or password.")
        else:
            session["username"] = username
            session["role"] = role
            return redirect(url_for("index"))

    return render_template("login.html", role=current_role())


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login_page"))


@app.route("/")
def index():
    if current_role() is None:
        return redirect(url_for("login_page"))

    sort_by = request.args.get("sort", "reg_no")
    result_filter = request.args.get("filter", "all")
    keyword = request.args.get("q", "").strip()

    students = search_students(keyword) if keyword != "" else fetch_all_students()
    students = filter_students(sort_students(students, sort_by), result_filter)

    return render_template(
        "index.html",
        students=build_rows(students),
        subjects=SUBJECTS,
        sort_by=sort_by,
        result_filter=result_filter,
        keyword=keyword,
        can_delete=can(current_role(), "delete"),
        role=current_role(),
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
            reg_no = insert_student(name, marks)
            flash(f"Student {name} added with registration number {reg_no}.")
            return redirect(url_for("index"))

    return render_template(
        "form.html",
        student=None,
        subjects=SUBJECTS,
        max_mark=MAX_MARK,
        role=current_role(),
    )


@app.route("/edit/<reg_no>", methods=["GET", "POST"])
def edit_student_page(reg_no):
    if current_role() is None:
        return redirect(url_for("login_page"))

    row = fetch_student(reg_no)
    if row is None:
        flash("Student not found.")
        return redirect(url_for("index"))

    student = {
        "reg_no": row[0],
        "name": row[1],
        "marks": list(row[2:2 + len(SUBJECTS)]),
    }

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        marks, error = read_marks(request.form)

        if name == "":
            flash("Student name is required.")
        elif error != "":
            flash(error)
        else:
            update_student_record(reg_no, name, marks)
            flash("Record updated successfully.")
            return redirect(url_for("index"))

    return render_template(
        "form.html",
        student=student,
        subjects=SUBJECTS,
        max_mark=MAX_MARK,
        role=current_role(),
    )


@app.route("/delete/<reg_no>", methods=["POST"])
def delete_student_page(reg_no):
    if current_role() is None:
        return redirect(url_for("login_page"))

    if not can(current_role(), "delete"):
        flash("Your role does not have permission to delete records.")
        return redirect(url_for("index"))

    delete_student_record(reg_no)
    flash("Record deleted.")
    return redirect(url_for("index"))


@app.route("/stats")
def stats_page():
    if current_role() is None:
        return redirect(url_for("login_page"))

    summary = class_statistics(fetch_all_students())
    return render_template(
        "stats.html",
        stats=summary,
        subjects=SUBJECTS,
        max_mark=MAX_MARK,
        role=current_role(),
    )


@app.route("/import", methods=["GET", "POST"])
def import_page():
    if current_role() is None:
        return redirect(url_for("login_page"))

    if not can(current_role(), "add"):
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
            for name, marks in records:
                insert_student(name, marks)
            flash(f"Imported {len(records)} students from {upload.filename}.")

        for error in errors[:10]:
            flash(error)

        return redirect(url_for("index"))

    return render_template(
        "import.html",
        subjects=SUBJECTS,
        max_mark=MAX_MARK,
        role=current_role(),
    )


@app.route("/template")
def template_page():
    if current_role() is None:
        return redirect(url_for("login_page"))

    rows = ["Name," + ",".join(SUBJECTS)]
    rows.append("Sample Student," + ",".join(["40"] * len(SUBJECTS)))
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


if __name__ == "__main__":
    app.run(debug=True)
