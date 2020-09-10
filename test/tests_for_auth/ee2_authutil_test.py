import unittest
import requests
import requests_mock
import os
from configparser import ConfigParser
from lib.execution_engine2.authorization.roles import AdminAuthUtil
from lib.execution_engine2.exceptions import AuthError

from test.utils_shared.test_utils import bootstrap

bootstrap()


class AdminAuthUtilTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        config_file = os.environ.get("KB_DEPLOYMENT_CONFIG", "test/deploy.cfg")
        cls.cfg = dict()
        config = ConfigParser()
        config.read(config_file)
        for nameval in config.items("execution_engine2"):
            cls.cfg[nameval[0]] = nameval[1]
        cls.auth_endpt = cls.cfg["auth-url"] + "/api/V2/me"

    def init_auth_util(self) -> AdminAuthUtil:
        return AdminAuthUtil(
            self.cfg["auth-url"], self.cfg.get("admin_roles", ["EE2_ADMIN"])
        )

    @requests_mock.Mocker()
    def test_auth_util_isadmin_ok(self, rq_mock):
        rq_mock.get(self.auth_endpt, json={"customroles": ["EE2_ADMIN", "some_role"]})
        auth_util = self.init_auth_util()
        self.assertTrue(auth_util.is_admin("some_admin_token"))

    @requests_mock.Mocker()
    def test_auth_util_notadmin_ok(self, rq_mock):
        rq_mock.get(self.auth_endpt, json={"customroles": ["some_role"]})
        auth_util = self.init_auth_util()
        self.assertFalse(auth_util.is_admin("some_nonadmin_token"))

    @requests_mock.Mocker()
    def test_auth_util_isadmin_fail(self, rq_mock):
        error = {"error": {"message": "10021 Not Allowed"}}
        rq_mock.register_uri(
            "GET", self.auth_endpt, [{"json": error, "status_code": 401}]
        )
        auth_util = self.init_auth_util()

        # test invalid token
        with self.assertRaises(AuthError) as e:
            auth_util.is_admin("some_invalid_token")
        self.assertIn("Token is not valid", str(e.exception))

        # test HTTP error
        rq_mock.register_uri(
            "GET", self.auth_endpt, [{"text": "error", "status_code": 500}]
        )
        with self.assertRaises(RuntimeError) as e:
            auth_util.is_admin("some_fail_token")
        self.assertIn(
            "An error occurred while fetching user roles from auth service",
            str(e.exception),
        )

        # test timeout
        rq_mock.register_uri(
            "GET", self.auth_endpt, exc=requests.exceptions.ConnectTimeout
        )
        with self.assertRaises(RuntimeError) as e:
            auth_util.is_admin("some_timeout_token")
        self.assertIn(
            "The auth service timed out while fetching user roles.", str(e.exception)
        )

    def test_auth_util_isadmin_bad_params(self):
        auth_util = self.init_auth_util()
        with self.assertRaises(ValueError) as e:
            auth_util.is_admin(None)
        self.assertIn("Must supply token to check privileges", str(e.exception))

    @requests_mock.Mocker()
    def test_auth_util_caching(self, rq_mock):
        token = "some_token1"

        auth_util = self.init_auth_util()
        rq_mock.get(self.auth_endpt, json={"customroles": ["some_role"]})
        auth_util.is_admin(token)
        auth_util.is_admin(token)
        self.assertEqual(rq_mock.call_count, 1)  # should cache the first result

        auth_util2 = self.init_auth_util()
        auth_util2.is_admin(token)
        self.assertEqual(rq_mock.call_count, 1)  # cache should be a singleton
