import os
import unittest
from configparser import ConfigParser

from execution_engine2.execution_engine2Impl import execution_engine2
from test.utils_shared.test_utils import is_timestamp, bootstrap

bootstrap()


class EE2ServerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        config_file = os.environ.get("KB_DEPLOYMENT_CONFIG", "test/deploy.cfg")
        token = os.environ.get("KB_AUTH_TOKEN")
        cls.ctx = {"token": token}
        cls.cfg = dict()
        config = ConfigParser()
        config.read(config_file)
        for nameval in config.items("execution_engine2"):
            cls.cfg[nameval[0]] = nameval[1]
        cls.impl = execution_engine2(cls.cfg)

    def test_status(self):
        status = self.impl.status(self.ctx)[0]
        self.assertTrue(is_timestamp(status.get("server_time")))
        self.assertIsNotNone(status.get("git_commit"))
        self.assertIsNotNone(status.get("version"))
        self.assertEqual(status.get("version"), self.impl.VERSION)
        self.assertEqual(status.get("service"), self.impl.SERVICE_NAME)

    def test_version(self):
        version = self.impl.ver(self.ctx)[0]
        self.assertEqual(version, self.impl.VERSION)

    def test_get_job_logs_fail(self):
        with self.assertRaises(ValueError) as context:
            self.impl.get_job_logs(ctx=self.ctx, params={"skip_lines": 2, "offset": 2})
            self.assertEqual(
                "Please provide only one of skip_lines or offset",
                str(context.exception.args),
            )
