import os
import tempfile
import unittest

import database


class DatabaseTests(unittest.TestCase):
    def setUp(self):
        handle, self.path = tempfile.mkstemp(suffix=".db")
        os.close(handle)
        os.remove(self.path)
        self.original_name = database.DB_NAME
        database.DB_NAME = self.path
        database.create_table()

    def tearDown(self):
        database.DB_NAME = self.original_name
        if os.path.exists(self.path):
            os.remove(self.path)

    def test_insert_and_fetch(self):
        reg_no = database.insert_student("Test Student", [40, 41, 42, 43, 44])
        rows = database.fetch_all_students()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][0], reg_no)
        self.assertEqual(rows[0][1], "Test Student")
        self.assertEqual(list(rows[0][2:7]), [40, 41, 42, 43, 44])

    def test_reg_numbers_increment(self):
        first = database.insert_student("A", [1, 2, 3, 4, 5])
        second = database.insert_student("B", [1, 2, 3, 4, 5])
        self.assertEqual(int(second[3:]) - int(first[3:]), 1)

    def test_fetch_single(self):
        reg_no = database.insert_student("A", [10, 20, 30, 40, 50])
        row = database.fetch_student(reg_no)
        self.assertEqual(row[0], reg_no)
        self.assertIsNone(database.fetch_student("SGP0000"))

    def test_update(self):
        reg_no = database.insert_student("A", [1, 2, 3, 4, 5])
        database.update_student_record(reg_no, "A Updated", [10, 20, 30, 40, 50])
        row = database.fetch_student(reg_no)
        self.assertEqual(row[1], "A Updated")
        self.assertEqual(list(row[2:7]), [10, 20, 30, 40, 50])

    def test_delete(self):
        reg_no = database.insert_student("A", [1, 2, 3, 4, 5])
        database.delete_student_record(reg_no)
        self.assertIsNone(database.fetch_student(reg_no))
        self.assertEqual(database.fetch_all_students(), [])

    def test_search_case_insensitive(self):
        database.insert_student("Riya Sharma", [1, 2, 3, 4, 5])
        database.insert_student("Arjun Mehta", [1, 2, 3, 4, 5])
        results = database.search_students("riya")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0][1], "Riya Sharma")

    def test_existing_signatures(self):
        database.insert_student("A", [1, 2, 3, 4, 5])
        self.assertIn(("a", (1, 2, 3, 4, 5)), database.existing_signatures())


if __name__ == "__main__":
    unittest.main()
