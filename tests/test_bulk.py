"""Tests for the bulk operations page (batch update, archive and restore)."""

import os
import tempfile
import unittest

import app as app_module
import database
import users


class BulkRouteTests(unittest.TestCase):
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

    def test_bulk_update_applies_class_to_selected(self):
        first = database.insert_student("A", [10, 10, 10, 10, 10])
        second = database.insert_student("B", [10, 10, 10, 10, 10])
        untouched = database.insert_student("C", [10, 10, 10, 10, 10])

        response = self.client.post(
            "/bulk",
            data={"reg_no": [first, second], "action": "update", "student_class": "10A"},
        )
        self.assertEqual(response.status_code, 302)

        self.assertEqual(database.fetch_student_details(first)["student_class"], "10A")
        self.assertEqual(database.fetch_student_details(second)["student_class"], "10A")
        self.assertEqual(database.fetch_student_details(untouched)["student_class"], "")

    def test_bulk_delete_then_restore(self):
        first = database.insert_student("A", [10, 10, 10, 10, 10])
        second = database.insert_student("B", [10, 10, 10, 10, 10])

        self.client.post("/bulk", data={"reg_no": [first, second], "action": "delete"})
        archived = {row[0] for row in database.fetch_deleted_students()}
        self.assertEqual(archived, {first, second})

        self.client.post("/bulk", data={"reg_no": [first, second], "action": "restore"})
        self.assertEqual(database.fetch_deleted_students(), [])
        self.assertIsNotNone(database.fetch_student(first))

    def test_bulk_without_selection_warns(self):
        database.insert_student("A", [10, 10, 10, 10, 10])
        response = self.client.post("/bulk", data={"action": "update", "student_class": "10A"})
        self.assertEqual(response.status_code, 302)
        followed = self.client.get(response.headers["Location"])
        self.assertIn("Select at least one student", followed.get_data(as_text=True))


if __name__ == "__main__":
    unittest.main()
