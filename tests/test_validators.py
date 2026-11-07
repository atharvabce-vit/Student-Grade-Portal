import unittest

from rules import dump_scale, parse_scale
from validators import (
    is_valid_date,
    is_valid_email,
    is_valid_phone,
    validate_details,
    validate_mark,
)


class ValidatorTests(unittest.TestCase):
    def test_email(self):
        self.assertTrue(is_valid_email("a@b.com"))
        self.assertFalse(is_valid_email("a@b"))
        self.assertFalse(is_valid_email("nope"))

    def test_phone(self):
        self.assertTrue(is_valid_phone("+91 98765 43210"))
        self.assertFalse(is_valid_phone("call-me"))

    def test_date(self):
        self.assertTrue(is_valid_date("2005-06-01"))
        self.assertFalse(is_valid_date("2005-13-40"))
        self.assertFalse(is_valid_date("01/06/2005"))

    def test_validate_details(self):
        self.assertEqual(validate_details({"email": "", "phone": "", "dob": ""}), [])
        errors = validate_details({"email": "bad", "phone": "x", "dob": "today"})
        self.assertEqual(len(errors), 3)

    def test_validate_mark(self):
        self.assertEqual(validate_mark("40", 50), "")
        self.assertIn("between", validate_mark("60", 50))
        self.assertIn("whole", validate_mark("abc", 50))

    def test_parse_and_dump_scale(self):
        scale = parse_scale("50 Merit\n70 Distinction\n")
        self.assertEqual(scale, [(70, "Distinction"), (50, "Merit")])
        self.assertEqual(dump_scale(scale), '[[70, "Distinction"], [50, "Merit"]]')


if __name__ == "__main__":
    unittest.main()
