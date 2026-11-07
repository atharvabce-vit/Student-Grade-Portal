"""Tests for TOTP two-factor authentication."""

import os
import tempfile
import unittest

import app as app_module
import database
import totp
import users


class TotpUnitTests(unittest.TestCase):
    def test_generated_secret_verifies_its_own_code(self):
        secret = totp.generate_secret()
        self.assertTrue(totp.verify(secret, totp.code_at(secret)))

    def test_wrong_code_is_rejected(self):
        secret = totp.generate_secret()
        current = totp.code_at(secret)
        wrong = "000000" if current != "000000" else "111111"
        self.assertFalse(totp.verify(secret, wrong))

    def test_code_changes_over_time(self):
        secret = totp.generate_secret()
        self.assertNotEqual(totp.code_at(secret, 0), totp.code_at(secret, 10_000_000))

    def test_verify_handles_empty_values(self):
        self.assertFalse(totp.verify("", "123456"))
        self.assertFalse(totp.verify(totp.generate_secret(), ""))

    def test_provisioning_uri(self):
        uri = totp.provisioning_uri("ABCDEF2345", "admin")
        self.assertTrue(uri.startswith("otpauth://totp/"))
        self.assertIn("secret=ABCDEF2345", uri)
        self.assertIn("issuer=Student", uri)


class TotpFlowTests(unittest.TestCase):
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

    def _enable_two_factor(self):
        self.client.get("/2fa")
        secret = users.find_user("admin")["totp_secret"]
        self.client.post("/2fa", data={"code": totp.code_at(secret)})
        return secret

    def test_enrollment_stores_a_secret(self):
        self.client.get("/2fa")
        self.assertTrue(users.find_user("admin")["totp_secret"])

    def test_enable_then_login_requires_code(self):
        secret = self._enable_two_factor()
        self.assertTrue(users.find_user("admin")["totp_enabled"])

        self.client.get("/logout")
        response = self.client.post(
            "/login", data={"username": "admin", "password": "admin123"}
        )
        self.assertIn("/2fa/verify", response.headers.get("Location", ""))

        with self.client.session_transaction() as sess:
            self.assertNotIn("username", sess)
            self.assertEqual(sess.get("pending_2fa"), "admin")

        verify = self.client.post("/2fa/verify", data={"code": totp.code_at(secret)})
        self.assertIn("/dashboard", verify.headers.get("Location", ""))

    def test_wrong_code_does_not_log_in(self):
        secret = self._enable_two_factor()
        self.client.get("/logout")
        self.client.post("/login", data={"username": "admin", "password": "admin123"})

        current = totp.code_at(secret)
        wrong = "000000" if current != "000000" else "111111"
        response = self.client.post("/2fa/verify", data={"code": wrong})
        self.assertEqual(response.status_code, 200)
        with self.client.session_transaction() as sess:
            self.assertNotIn("username", sess)

    def test_disable_two_factor(self):
        self._enable_two_factor()
        self.client.post("/2fa", data={"action": "disable"})
        user = users.find_user("admin")
        self.assertFalse(user["totp_enabled"])
        self.assertEqual(user["totp_secret"], "")


if __name__ == "__main__":
    unittest.main()
