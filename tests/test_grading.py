import unittest

from grading import calculate, get_grade, get_result


class GradingTests(unittest.TestCase):
    def test_total(self):
        self.assertEqual(calculate([40, 40, 40, 40, 40])[0], 200)

    def test_percentage(self):
        self.assertEqual(calculate([50, 50, 50, 50, 50])[1], 100)
        self.assertEqual(calculate([25, 25, 25, 25, 25])[1], 50)

    def test_pass_needs_every_subject(self):
        self.assertEqual(get_result([40, 40, 40, 40, 40]), "PASS")
        self.assertEqual(get_result([40, 19, 40, 40, 40]), "FAIL")

    def test_pass_boundary(self):
        self.assertEqual(get_result([20, 20, 20, 20, 20]), "PASS")

    def test_grade_scale(self):
        self.assertEqual(get_grade(95), "A+")
        self.assertEqual(get_grade(85), "A")
        self.assertEqual(get_grade(75), "B+")
        self.assertEqual(get_grade(65), "B")
        self.assertEqual(get_grade(55), "C")
        self.assertEqual(get_grade(45), "D")
        self.assertEqual(get_grade(30), "F")

    def test_grade_boundary(self):
        self.assertEqual(get_grade(90), "A+")
        self.assertEqual(get_grade(89.9), "A")
        self.assertEqual(get_grade(40), "D")
        self.assertEqual(get_grade(39.9), "F")

    def test_custom_pass_mark(self):
        self.assertEqual(get_result([30, 30, 30, 30, 30], pass_mark=35), "FAIL")
        self.assertEqual(get_result([40, 40, 40, 40, 40], pass_mark=35), "PASS")

    def test_custom_grade_scale(self):
        scale = [(70, "Distinction"), (50, "Merit")]
        self.assertEqual(get_grade(75, scale), "Distinction")
        self.assertEqual(get_grade(55, scale), "Merit")
        self.assertEqual(get_grade(45, scale), "F")


if __name__ == "__main__":
    unittest.main()
