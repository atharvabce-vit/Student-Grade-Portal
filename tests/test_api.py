"""Tests for the JSON API expansion (pagination, PATCH, marks) and /healthz."""

import os
import tempfile
import unittest

import app as app_module
import database
import users
from config import API_TOKEN


class ApiTests(unittest.TestCase):
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
        self.headers = {"X-API-Token": API_TOKEN}

    def tearDown(self):
        database.DB_NAME = self.original_name
        if os.path.exists(self.path):
            os.remove(self.path)

    def test_list_is_paginated(self):
        for index in range(5):
            database.insert_student(f"S{index}", [10, 10, 10, 10, 10])
        response = self.client.get("/api/students?page=1&page_size=2", headers=self.headers)
        body = response.get_json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(body["students"]), 2)
        self.assertEqual(body["total"], 5)
        self.assertEqual(body["page_size"], 2)

    def test_patch_updates_name_and_marks(self):
        reg_no = database.insert_student("Old", [10, 10, 10, 10, 10])
        response = self.client.patch(
            f"/api/students/{reg_no}", headers=self.headers,
            json={"name": "New", "marks": [40, 40, 40, 40, 40]},
        )
        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertEqual(body["student"]["name"], "New")
        self.assertEqual(body["student"]["result"], "PASS")

    def test_patch_rejects_bad_marks(self):
        reg_no = database.insert_student("A", [10, 10, 10, 10, 10])
        response = self.client.patch(
            f"/api/students/{reg_no}", headers=self.headers, json={"marks": [1, 2]}
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"], "invalid_marks")

    def test_marks_round_trip(self):
        reg_no = database.insert_student("A", [10, 10, 10, 10, 10])
        response = self.client.put(
            f"/api/students/{reg_no}/marks", headers=self.headers,
            json={"marks": [45, 45, 45, 45, 45]},
        )
        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertEqual(body["marks"]["Maths"], 45)

        fetched = self.client.get(f"/api/students/{reg_no}/marks", headers=self.headers)
        self.assertEqual(fetched.get_json()["marks"]["Maths"], 45)

    def test_healthz_reports_database(self):
        response = self.client.get("/healthz")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["database"])

    def test_openapi_spec_lists_marks_path(self):
        spec = self.client.get("/api/openapi.json").get_json()
        self.assertIn("/api/students/{reg_no}/marks", spec["paths"])
        self.assertIn("/healthz", spec["paths"])


if __name__ == "__main__":
    unittest.main()
