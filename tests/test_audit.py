"""Tests for audit log filtering and CSV export."""

import os
import tempfile
import unittest

import app as app_module
import database
import users


class AuditFilterTests(unittest.TestCase):
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

        database.record_audit("alice", "add_student", "S1", "added")
        database.record_audit("bob", "delete_student", "S2", "deleted")

    def tearDown(self):
        database.DB_NAME = self.original_name
        if os.path.exists(self.path):
            os.remove(self.path)

    def test_filter_by_action(self):
        body = self.client.get("/audit?action=add_student").get_data(as_text=True)
        self.assertIn("S1", body)
        self.assertNotIn("S2", body)

    def test_filter_by_username(self):
        body = self.client.get("/audit?username=bob").get_data(as_text=True)
        self.assertIn("S2", body)
        self.assertNotIn("S1", body)

    def test_actions_helper_lists_distinct_actions(self):
        self.assertEqual(database.audit_actions(), ["add_student", "delete_student"])

    def test_csv_export_respects_filter(self):
        response = self.client.get("/audit/export?action=add_student")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "text/csv")
        text = response.get_data(as_text=True)
        self.assertIn("Time,User,Action,Target,Details,IP", text)
        self.assertIn("add_student", text)
        self.assertNotIn("delete_student", text)


if __name__ == "__main__":
    unittest.main()
