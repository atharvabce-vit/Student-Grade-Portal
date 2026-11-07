"""Tests for term-wise mark sheet import."""

import io
import os
import tempfile
import unittest

import app as app_module
import database
import users
from importer import build_term_records

HEADER = ["Reg No", "Term", "Exam", "Maths", "Physics", "Chemistry", "English", "Computer"]


class TermRecordsUnitTests(unittest.TestCase):
    def test_valid_row_becomes_one_record_per_subject(self):
        rows = [["S1", "Term 1", "Final", "40", "40", "40", "40", "40"]]
        records, errors = build_term_records(HEADER, rows)
        self.assertEqual(errors, [])
        self.assertEqual(len(records), 5)
        self.assertEqual(records[0], ("S1", "Maths", "Term 1", "Final", 40))

    def test_unknown_term_is_reported(self):
        rows = [["S1", "Term 9", "Final", "40", "40", "40", "40", "40"]]
        records, errors = build_term_records(HEADER, rows)
        self.assertEqual(records, [])
        self.assertTrue(any("term" in error.lower() for error in errors))

    def test_non_numeric_mark_is_reported(self):
        rows = [["S1", "Term 1", "Final", "x", "40", "40", "40", "40"]]
        records, errors = build_term_records(HEADER, rows)
        self.assertEqual(len(records), 4)
        self.assertTrue(any("not a number" in error for error in errors))

    def test_missing_reg_no_column_is_reported(self):
        records, errors = build_term_records(["Name", "Term", "Exam"], [])
        self.assertEqual(records, [])
        self.assertTrue(any("Reg No" in error for error in errors))


class TermImportRouteTests(unittest.TestCase):
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

    def _upload(self, csv_text):
        data = {"file": (io.BytesIO(csv_text.encode()), "term_marks.csv")}
        return self.client.post(
            "/term-marks/import", data=data, content_type="multipart/form-data"
        )

    def test_import_saves_term_marks(self):
        reg_no = database.insert_student("A", [10, 10, 10, 10, 10])
        csv_text = (
            "Reg No,Term,Exam,Maths,Physics,Chemistry,English,Computer\n"
            f"{reg_no},Term 1,Final,45,45,45,45,45\n"
        )
        response = self._upload(csv_text)
        self.assertEqual(response.status_code, 302)

        grid = database.term_marks_grid("Term 1", "Final")
        self.assertEqual(grid[reg_no]["Maths"], 45)

    def test_import_skips_unknown_reg_no(self):
        csv_text = (
            "Reg No,Term,Exam,Maths,Physics,Chemistry,English,Computer\n"
            "UNKNOWN,Term 1,Final,45,45,45,45,45\n"
        )
        response = self._upload(csv_text)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(database.term_marks_grid("Term 1", "Final"), {})

    def test_template_downloads(self):
        response = self.client.get("/term-marks/template")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Reg No,Term,Exam", response.get_data(as_text=True))


if __name__ == "__main__":
    unittest.main()
