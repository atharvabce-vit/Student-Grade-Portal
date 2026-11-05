import unittest

from reports import class_statistics, filter_students, sort_students

ROWS = [
    ("SGP1001", "Riya", 42, 38, 45, 40, 47),
    ("SGP1003", "Arjun", 35, 29, 31, 44, 38),
    ("SGP1002", "Neha", 10, 45, 45, 45, 45),
]


class ReportTests(unittest.TestCase):
    def test_sort_by_reg_no(self):
        rows = sort_students(ROWS, "reg_no")
        self.assertEqual([row[0] for row in rows], ["SGP1001", "SGP1002", "SGP1003"])

    def test_sort_by_name(self):
        rows = sort_students(ROWS, "name")
        self.assertEqual([row[1] for row in rows], ["Arjun", "Neha", "Riya"])

    def test_sort_by_percentage(self):
        rows = sort_students(ROWS, "percentage")
        self.assertEqual(rows[0][1], "Riya")
        self.assertEqual(rows[-1][1], "Arjun")

    def test_filter_pass(self):
        rows = filter_students(ROWS, "pass")
        self.assertEqual(sorted(row[1] for row in rows), ["Arjun", "Riya"])

    def test_filter_fail(self):
        rows = filter_students(ROWS, "fail")
        self.assertEqual([row[1] for row in rows], ["Neha"])

    def test_filter_all(self):
        self.assertEqual(len(filter_students(ROWS, "all")), 3)

    def test_statistics(self):
        summary = class_statistics(ROWS)
        self.assertEqual(summary["count"], 3)
        self.assertEqual(summary["passed"], 2)
        self.assertEqual(summary["topper"][1], "SGP1001")
        self.assertEqual(summary["lowest"][1], "SGP1003")
        self.assertAlmostEqual(summary["pass_percentage"], 66.666, places=2)

    def test_statistics_empty(self):
        summary = class_statistics([])
        self.assertEqual(summary["count"], 0)
        self.assertIsNone(summary["topper"])


if __name__ == "__main__":
    unittest.main()
