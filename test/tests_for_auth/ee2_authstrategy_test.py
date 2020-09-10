import os
import unittest
from configparser import ConfigParser

import requests_mock

from execution_engine2.authorization.authstrategy import (
    can_read_job,
    can_read_jobs,
    can_write_job,
    can_write_jobs,
)
from test.utils_shared.test_utils import (
    get_example_job,
    custom_ws_perm_maker,
    bootstrap,
)

bootstrap()


class AuthStrategyTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):

        cls.user = "some_user"
        cls.other_user = "some_other_user"
        config_file = os.environ.get("KB_DEPLOYMENT_CONFIG", "test/deploy.cfg")
        cls.cfg = dict()
        config = ConfigParser()
        config.read(config_file)
        for nameval in config.items("execution_engine2"):
            cls.cfg[nameval[0]] = nameval[1]
        cls.ws_url = cls.cfg["workspace-url"]
        cls.ws_access = {123: "r", 456: "n", 789: "w", 321: "a"}

    def _generate_all_test_jobs(self, perm="read"):
        """
        Makes a gamut of test jobs.
        All combinations of:
        user = self.user, other_user
        wsid = ids with all permissions (r, w, a, n)
        authstrat of either "kbaseworkspace" or "execution_engine"
        And returns whether self.user would have permission to see this job
        :returns: tuple - list of all jobs, and list of all expected permissions
        """
        jobs = list()
        expected_perms = list()
        allowed_wsid = [789, 321]
        if perm == "read":
            allowed_wsid.append(123)
        for wsid in self.ws_access.keys():
            for user in [self.user, self.other_user]:
                for authstrat in ["execution_engine", "kbaseworkspace"]:
                    job = get_example_job(user=user, wsid=wsid, authstrat=authstrat)
                    expect = False
                    if user == self.user:
                        expect = True
                    elif authstrat == "kbaseworkspace" and job.wsid in allowed_wsid:
                        expect = True
                    jobs.append(job)
                    expected_perms.append(expect)
        return (jobs, expected_perms)

    def _mock_ws_deleted(self, rq_mock, ws_id):
        response = {
            "error": {
                "code": -32500,
                "error": "An error occurred!",
                "message": f"Workspace {ws_id} is deleted",
                "name": "JSONRpcError",
            },
            "version": "1.1",
        }
        rq_mock.register_uri(
            "POST", self.ws_url, [{"json": response, "status_code": 500}]
        )

    @requests_mock.Mocker()
    def test_can_read_job_ok(self, rq_mock):
        rq_mock.add_matcher(custom_ws_perm_maker(self.user, self.ws_access))
        (jobs, expected_perms) = self._generate_all_test_jobs(perm="read")
        for idx, job in enumerate(jobs):
            self.assertEqual(
                expected_perms[idx], can_read_job(job, self.user, "foo", self.cfg)
            )

    @requests_mock.Mocker()
    def test_can_read_job_fail(self, rq_mock):
        self._mock_ws_deleted(rq_mock, 123)
        job = get_example_job(
            user=self.other_user, wsid=123, authstrat="kbaseworkspace"
        )
        with self.assertRaises(RuntimeError) as e:
            can_read_job(job, self.user, "token", self.cfg)
        self.assertIn("Workspace 123 is deleted", str(e.exception))

    @requests_mock.Mocker()
    def test_can_write_job_ok(self, rq_mock):
        rq_mock.add_matcher(custom_ws_perm_maker(self.user, self.ws_access))
        (jobs, expected_perms) = self._generate_all_test_jobs(perm="write")
        for idx, job in enumerate(jobs):
            self.assertEqual(
                expected_perms[idx], can_write_job(job, self.user, "foo", self.cfg)
            )

    @requests_mock.Mocker()
    def test_can_write_job_fail(self, rq_mock):
        self._mock_ws_deleted(rq_mock, 123)
        job = get_example_job(
            user=self.other_user, wsid=123, authstrat="kbaseworkspace"
        )
        with self.assertRaises(RuntimeError) as e:
            can_write_job(job, self.user, "token", self.cfg)
        self.assertIn("Workspace 123 is deleted", str(e.exception))

    @requests_mock.Mocker()
    def test_can_read_jobs_ok(self, rq_mock):
        # cases
        # 1 job, r, w, a, n access, with and without ws, self vs. other user (so that's 16)
        # 2 jobs, each with those accesses (so that's another 32)
        # this is all looked up from the POV of the main user, so set up ws access that way
        rq_mock.add_matcher(custom_ws_perm_maker(self.user, self.ws_access))
        (jobs, expected_perms) = self._generate_all_test_jobs(perm="read")
        for idx, job in enumerate(jobs):
            self.assertEqual(
                [expected_perms[idx]], can_read_jobs([job], self.user, "foo", self.cfg)
            )

    @requests_mock.Mocker()
    def test_can_read_jobs_fail(self, rq_mock):
        self._mock_ws_deleted(rq_mock, 123)
        job = get_example_job(
            user=self.other_user, wsid=123, authstrat="kbaseworkspace"
        )
        with self.assertRaises(RuntimeError) as e:
            can_read_jobs([job], self.user, "token", self.cfg)
        self.assertIn("Workspace 123 is deleted", str(e.exception))

    @requests_mock.Mocker()
    def test_can_write_jobs_ok(self, rq_mock):
        rq_mock.add_matcher(custom_ws_perm_maker(self.user, self.ws_access))
        (jobs, expected_perms) = self._generate_all_test_jobs(perm="write")
        for idx, job in enumerate(jobs):
            self.assertEqual(
                [expected_perms[idx]], can_write_jobs([job], self.user, "foo", self.cfg)
            )

    @requests_mock.Mocker()
    def test_can_write_jobs_fail(self, rq_mock):
        self._mock_ws_deleted(rq_mock, 123)
        job = get_example_job(
            user=self.other_user, wsid=123, authstrat="kbaseworkspace"
        )
        with self.assertRaises(RuntimeError) as e:
            can_write_jobs([job], self.user, "token", self.cfg)
        self.assertIn("Workspace 123 is deleted", str(e.exception))
