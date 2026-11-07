"""Tests for the performance trend analytics and the dashboard page."""

import os
import tempfile
import unittest

import app as app_module
import database
import users
from analytics import cohort_average, direction, grade_distribution, term_trend
from config import EXAMS, TERMS


class AnalyticsUnitTests(unittest.TestCase):
    def test_direction_labels(self):
        self.assertEqual(direction(None), "flat")
        self.assertEqual(direction(4), "up")
        self.assertEqual(direction(-4), "down")
        self.assertEqual(direction(0.1), "flat")

    def test_term_trend_computes_change(self):
        trend = term_trend([
            {"term": "Term 1", "percentage": 50.0},
            {"term": "Term 2", "percentage": 62.0},
            {"term": "Term 3", "percentage": 60.0},
        ])
        self.assertIsNone(trend[0]["change"])
        self.assertEqual(trend[0]["direction"], "flat")
        self.assertEqual(trend[1]["change"], 12.0)
        self.assertEqual(trend[1]["direction"], "up")
        self.assertEqual(trend[2]["direction"], "down")

    def test_cohort_average(self):
        self.assertEqual(cohort_average([]), 0.0)
        self.assertEqual(cohort_average([{"percentage": 40}, {"percentage": 60}]), 50.0)

    def test_grade_distribution_orders_and_appends(self):
        students = [{"grade": "A"}, {"grade": "A"}, {"grade": "F"}, {"grade": "Distinction"}]
        distribution = dict(grade_distribution(students))
        self.assertEqual(distribution["A"], 2)
        self.assertEqual(distribution["Distinction"], 1)
        self.assertEqual(distribution["B+"], 0)


class DashboardRouteTests(unittest.TestCase):
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

    def test_dashboard_renders_metrics(self):
        database.insert_student("A", [40, 40, 40, 40, 40])
        response = self.client.get("/dashboard")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Dashboard", response.get_data(as_text=True))

    def test_dashboard_shows_cohort_trend(self):
        reg_no = database.insert_student("A", [0, 0, 0, 0, 0])
        database.set_term_mark(reg_no, "Maths", TERMS[0], EXAMS[0], 40)
        response = self.client.get("/dashboard")
        self.assertIn(TERMS[0], response.get_data(as_text=True))

    def test_login_lands_on_dashboard(self):
        self.client.get("/logout")
        response = self.client.post(
            "/login", data={"username": "admin", "password": "admin123"}
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("/dashboard", response.headers.get("Location", ""))


if __name__ == "__main__":
    unittest.main()
