"""Tests for scheduled database and report snapshots."""

import datetime
import os
import sqlite3
import tempfile
import unittest

import backups
import database


class BackupTests(unittest.TestCase):
    def setUp(self):
        handle, self.path = tempfile.mkstemp(suffix=".db")
        os.close(handle)
        os.remove(self.path)
        self.original_name = database.DB_NAME
        database.DB_NAME = self.path
        database.create_table()
        database.insert_student("A", [10, 10, 10, 10, 10])
        self.directory = tempfile.mkdtemp()

    def tearDown(self):
        database.DB_NAME = self.original_name
        if os.path.exists(self.path):
            os.remove(self.path)
        for name in os.listdir(self.directory):
            os.remove(os.path.join(self.directory, name))
        os.rmdir(self.directory)

    def test_run_backup_writes_database_and_csv(self):
        when = datetime.datetime(2026, 1, 2, 3, 4, 5)
        result = backups.run_backup(self.directory, when=when)
        self.assertTrue(os.path.exists(result["database"]))
        self.assertTrue(os.path.exists(result["csv"]))
        self.assertIn("20260102-030405", result["database"])

    def test_backup_is_a_readable_copy(self):
        result = backups.run_backup(self.directory)
        connection = sqlite3.connect(result["database"])
        count = connection.execute("SELECT COUNT(*) FROM students").fetchone()[0]
        connection.close()
        self.assertEqual(count, 1)

    def test_timestamp_format(self):
        self.assertEqual(len(backups.timestamp()), 15)


if __name__ == "__main__":
    unittest.main()
