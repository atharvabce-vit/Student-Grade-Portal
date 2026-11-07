"""Feature and route tests for the term-wise marks, transcripts, API keys
and security improvements."""

import os
import tempfile
import unittest

import app as app_module
import database
import users
from config import EXAMS, TERMS


class PortalFeatureTests(unittest.TestCase):
    def setUp(self):
        handle, self.path = tempfile.mkstemp(suffix=".db")
        os.close(handle)
        os.remove(self.path)
        self.original_name = database.DB_NAME
        database.DB_NAME = self.path
        database.create_table()
        users.seed_default_users()

        app_module.app.config["WTF_CSRF_ENABLED"] = False
        app_module.app.config["TESTING"] = True
        self.client = app_module.app.test_client()
        with self.client.session_transaction() as sess:
            sess["username"] = "admin"
            sess["role"] = "admin"
            sess["sv"] = users.session_version("admin")

    def tearDown(self):
        database.DB_NAME = self.original_name
        if os.path.exists(self.path):
            os.remove(self.path)

    # ------------------------------------------------------------------ #
    # schema
    # ------------------------------------------------------------------ #
    def test_migrations_are_idempotent(self):
        database.create_table()
        database.create_table()
        self.assertTrue(database.insert_student("A", [1, 2, 3, 4, 5]).startswith("SGP"))

    # ------------------------------------------------------------------ #
    # term-wise marks and transcripts
    # ------------------------------------------------------------------ #
    def test_term_marks_round_trip(self):
        reg_no = database.insert_student("A", [0, 0, 0, 0, 0])
        database.set_term_mark(reg_no, "Maths", TERMS[0], EXAMS[0], 42)
        grid = database.term_marks_grid(TERMS[0], EXAMS[0])
        self.assertEqual(grid[reg_no]["Maths"], 42)

    def test_term_marks_post_saves_grid(self):
        reg_no = database.insert_student("A", [0, 0, 0, 0, 0])
        form = {"term": TERMS[0], "exam": EXAMS[0]}
        for index, _subject in enumerate(database.subject_names()):
            form[f"mark_{reg_no}_{index}"] = "30"
        response = self.client.post("/term-marks", data=form)
        self.assertEqual(response.status_code, 302)
        saved = database.term_marks_grid(TERMS[0], EXAMS[0])[reg_no]
        self.assertEqual(saved["Maths"], 30)

    def test_transcript_page_lists_terms(self):
        reg_no = database.insert_student("A", [0, 0, 0, 0, 0])
        database.set_term_mark(reg_no, "Maths", TERMS[0], EXAMS[0], 42)
        response = self.client.get(f"/student/{reg_no}/transcript")
        self.assertEqual(response.status_code, 200)
        self.assertIn(TERMS[0], response.get_data(as_text=True))

    def test_transcript_pdf_downloads(self):
        reg_no = database.insert_student("A", [0, 0, 0, 0, 0])
        response = self.client.get(f"/student/{reg_no}/transcript.pdf")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "application/pdf")

    # ------------------------------------------------------------------ #
    # API keys and scopes
    # ------------------------------------------------------------------ #
    def test_api_requires_a_token(self):
        self.assertEqual(self.client.get("/api/students").status_code, 401)

    def test_api_read_scope_cannot_write(self):
        database.create_api_key("reader", users.hash_token("raw-read"), "read")
        headers = {"X-API-Token": "raw-read"}
        self.assertEqual(self.client.get("/api/students", headers=headers).status_code, 200)
        self.assertEqual(
            self.client.post("/api/students", headers=headers, json={}).status_code, 403
        )

    def test_api_key_page_lists_keys(self):
        database.create_api_key("reader", users.hash_token("raw-read"), "read")
        response = self.client.get("/api-keys")
        self.assertEqual(response.status_code, 200)
        self.assertIn("reader", response.get_data(as_text=True))

    def test_revoked_api_key_is_rejected(self):
        key_id = database.create_api_key("reader", users.hash_token("raw-read"), "read")
        database.delete_api_key(key_id)
        headers = {"X-API-Token": "raw-read"}
        self.assertEqual(self.client.get("/api/students", headers=headers).status_code, 401)

    # ------------------------------------------------------------------ #
    # security
    # ------------------------------------------------------------------ #
    def test_security_headers_present(self):
        response = self.client.get("/")
        self.assertEqual(response.headers.get("X-Frame-Options"), "DENY")
        self.assertEqual(response.headers.get("X-Content-Type-Options"), "nosniff")

    def test_password_change_invalidates_other_sessions(self):
        with self.client.session_transaction() as sess:
            sess["sv"] = 1
        users.set_password("admin", "new-password-123")
        # The stored session version no longer matches, so the session is cleared.
        response = self.client.get("/")
        self.assertEqual(response.status_code, 302)

    # ------------------------------------------------------------------ #
    # pages and bulk attendance
    # ------------------------------------------------------------------ #
    def test_new_pages_render(self):
        for path in ["/", "/term-marks", "/api-keys", "/audit", "/archive", "/stats"]:
            self.assertEqual(self.client.get(path).status_code, 200, path)

    def test_bulk_attendance_marks_all_present(self):
        reg_no = database.insert_student("A", [0, 0, 0, 0, 0])
        response = self.client.post(
            "/attendance", data={"day": "2026-01-01", "default_status": "present"}
        )
        self.assertEqual(response.status_code, 302)
        present = {row[0]: row[2] for row in database.attendance_summary()}
        self.assertEqual(present[reg_no], 1)

    # ------------------------------------------------------------------ #
    # student self-service portal
    # ------------------------------------------------------------------ #
    def _login_as_student(self, reg_no):
        users.create_user("stu", "student-pass-123", "student", reg_no)
        with self.client.session_transaction() as sess:
            sess["username"] = "stu"
            sess["role"] = "student"
            sess["reg_no"] = reg_no
            sess["sv"] = users.session_version("stu")

    def test_student_login_links_registration(self):
        reg_no = database.insert_student("A", [40, 40, 40, 40, 40])
        self._login_as_student(reg_no)
        response = self.client.get("/me")
        self.assertEqual(response.status_code, 200)
        self.assertIn(reg_no, response.get_data(as_text=True))

    def test_student_cannot_reach_staff_pages(self):
        reg_no = database.insert_student("A", [40, 40, 40, 40, 40])
        self._login_as_student(reg_no)
        for path in ["/users", "/audit", "/archive", "/subjects"]:
            response = self.client.get(path)
            self.assertEqual(response.status_code, 302, path)
            self.assertIn("/me", response.headers.get("Location", ""))

    def test_student_sees_only_their_own_transcript(self):
        mine = database.insert_student("A", [0, 0, 0, 0, 0])
        database.insert_student("B", [0, 0, 0, 0, 0])
        self._login_as_student(mine)
        self.assertEqual(self.client.get("/me/transcript").status_code, 200)
        self.assertEqual(self.client.get("/student/SGP9999").status_code, 302)

    def test_creating_student_user_requires_valid_registration(self):
        response = self.client.post(
            "/users/add",
            data={"username": "stu", "password": "student-pass-123",
                  "role": "student", "linked_reg_no": "SGP0000"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertIsNone(users.find_user("stu"))

    # ------------------------------------------------------------------ #
    # self-service password change
    # ------------------------------------------------------------------ #
    def test_change_password_flow(self):
        response = self.client.post(
            "/password",
            data={"current_password": "admin123", "new_password": "brand-new-pass",
                  "confirm_password": "brand-new-pass"},
        )
        self.assertEqual(response.status_code, 302)
        user = users.find_user("admin")
        self.assertTrue(users.verify_password(user["password_hash"], "brand-new-pass"))

    def test_change_password_rejects_wrong_current(self):
        response = self.client.post(
            "/password",
            data={"current_password": "wrong", "new_password": "brand-new-pass",
                  "confirm_password": "brand-new-pass"},
        )
        self.assertEqual(response.status_code, 200)
        user = users.find_user("admin")
        self.assertTrue(users.verify_password(user["password_hash"], "admin123"))


if __name__ == "__main__":
    unittest.main()
