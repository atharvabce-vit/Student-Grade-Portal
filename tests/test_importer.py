import os
import tempfile
import unittest

from importer import import_students


class ImporterTests(unittest.TestCase):
    def write(self, text, suffix=".csv"):
        handle, path = tempfile.mkstemp(suffix=suffix)
        os.close(handle)
        with open(path, "w", newline="", encoding="utf-8") as file:
            file.write(text)
        self.addCleanup(os.remove, path)
        return path

    def test_reads_csv(self):
        path = self.write("Name,Maths,Physics,Chemistry,English,Computer\nRiya,42,38,45,40,47\n")
        records, errors = import_students(path)
        self.assertEqual(records, [("Riya", [42, 38, 45, 40, 47])])
        self.assertEqual(errors, [])

    def test_accepts_column_aliases(self):
        path = self.write("Student Name,Math,Phy,Chem,Eng,CS\nArjun,35,29,31,44,38\n")
        records, errors = import_students(path)
        self.assertEqual(records, [("Arjun", [35, 29, 31, 44, 38])])

    def test_skips_bad_rows(self):
        path = self.write(
            "Name,Maths,Physics,Chemistry,English,Computer\n"
            "Bad,10,abc,20,30,40\n"
            "Good,10,20,30,40,50\n"
        )
        records, errors = import_students(path)
        self.assertEqual(records, [("Good", [10, 20, 30, 40, 50])])
        self.assertEqual(len(errors), 1)

    def test_semicolon_delimited_text(self):
        path = self.write(
            "Name;Maths;Physics;Chemistry;English;Computer\nRiya;42;38;45;40;47\n",
            ".txt"
        )
        records, errors = import_students(path)
        self.assertEqual(records, [("Riya", [42, 38, 45, 40, 47])])

    def test_missing_subject_column(self):
        path = self.write("Name,Maths,Physics,Chemistry,English\nRiya,42,38,45,40\n")
        records, errors = import_students(path)
        self.assertEqual(records, [])
        self.assertEqual(len(errors), 1)

    def test_unsupported_extension(self):
        path = self.write("Name,Maths,Physics,Chemistry,English,Computer\nRiya,42,38,45,40,47\n", ".doc")
        with self.assertRaises(ValueError):
            import_students(path)


if __name__ == "__main__":
    unittest.main()
