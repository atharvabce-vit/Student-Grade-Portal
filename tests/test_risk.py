"""Tests for at-risk detection and the guardian alert page."""

import os
import tempfile
import unittest

import app as app_module
import database
import users
from risk import assess, identify


class RiskUnitTests(unittest.TestCase):
    def test_healthy_student_is_not_flagged(self):
        self.assertFalse(assess(82, 95, 0)["at_risk"])

    def test_low_percentage_is_flagged(self):
        verdict = assess(25, 95, 0)
        self.assertTrue(verdict["at_risk"])
        self.assertIn("percentage", verdict["reasons"][0].lower())

    def test_low_attendance_is_flagged(self):
        verdict = assess(82, 60, 0)
        self.assertTrue(verdict["at_risk"])
        self.assertIn("attendance", verdict["reasons"][0].lower())

    def test_failed_subject_is_flagged(self):
        verdict = assess(82, 95, 2)
        self.assertTrue(verdict["at_risk"])
        self.assertIn("subject", verdict["reasons"][0].lower())

    def test_identify_filters_list(self):
        students = [
            {"reg_no": "A", "name": "Good", "marks": [40, 40, 40, 40, 40], "percentage": 80},
            {"reg_no": "B", "name": "Weak", "marks": [10, 10, 10, 10, 10], "percentage": 20},
        ]
        flagged = identify(students, {"A": 95, "B": 95}, pass_mark=20)
        self.assertEqual([s["reg_no"] for s in flagged], ["B"])
        self.assertEqual(flagged[0]["failed_subjects"], 5)


class RiskRouteTests(unittest.TestCase):
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

    def test_at_risk_page_lists_flagged_student(self):
        database.insert_student("Weak", [5, 5, 5, 5, 5])
        response = self.client.get("/at-risk")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Weak", response.get_data(as_text=True))

    def test_healthy_students_are_not_flagged(self):
        database.insert_student("Great", [45, 45, 45, 45, 45])
        response = self.client.get("/at-risk")
        self.assertIn("No students are currently at risk", response.get_data(as_text=True))

    def test_alert_without_email_reports_gracefully(self):
        reg_no = database.insert_student("Weak", [5, 5, 5, 5, 5])
        response = self.client.post(f"/at-risk/notify/{reg_no}")
        self.assertEqual(response.status_code, 302)


if __name__ == "__main__":
    unittest.main()
