# -*- coding: utf-8 -*-
import copy
import json
import logging
import os
import time
import unittest
from configparser import ConfigParser
from datetime import datetime, timedelta
from pprint import pprint
from unittest.mock import patch

import bson
import dateutil
import requests_mock
from bson import ObjectId
from mock import MagicMock

from lib.execution_engine2.db.MongoUtil import MongoUtil
from lib.execution_engine2.db.models.models import Job, Status, TerminatedCode
from lib.execution_engine2.exceptions import AuthError
from lib.execution_engine2.exceptions import InvalidStatusTransitionException
from lib.execution_engine2.sdk.SDKMethodRunner import SDKMethodRunner
from lib.execution_engine2.utils.CondorTuples import SubmissionInfo, CondorResources
from test.tests_for_sdkmr.ee2_SDKMethodRunner_test_utils import ee2_sdkmr_test_helper
from test.utils_shared.test_utils import (
    bootstrap,
    get_example_job,
    validate_job_state,
    run_job_adapter,
)
from tests_for_db.mongo_test_helper import MongoTestHelper

logging.basicConfig(level=logging.INFO)
bootstrap()

from lib.execution_engine2.sdk.EE2Runjob import EE2RunJob


class ee2_SDKMethodRunner_test(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        config_file = os.environ.get("KB_DEPLOYMENT_CONFIG", "test/deploy.cfg")
        logging.info(f"Loading config from {config_file}")

        config_parser = ConfigParser()
        config_parser.read(config_file)

        cls.cfg = {}

        for nameval in config_parser.items("execution_engine2"):
            cls.cfg[nameval[0]] = nameval[1]

        mongo_in_docker = cls.cfg.get("mongo-in-docker-compose", None)
        if mongo_in_docker is not None:
            cls.cfg["mongo-host"] = cls.cfg["mongo-in-docker-compose"]

        cls.user_id = "wsadmin"
        cls.ws_id = 9999
        cls.token = "token"

        cls.method_runner = SDKMethodRunner(
            cls.cfg, user_id=cls.user_id, token=cls.token
        )
        cls.mongo_util = MongoUtil(cls.cfg)
        cls.mongo_helper = MongoTestHelper(cls.cfg)

        cls.test_collection = cls.mongo_helper.create_test_db(
            db=cls.cfg["mongo-database"], col=cls.cfg["mongo-jobs-collection"]
        )

        cls.cr = CondorResources(
            request_cpus="1",
            request_disk="1GB",
            request_memory="100M",
            client_group="njs",
        )
        cls.sdkmr_test_helper = ee2_sdkmr_test_helper(mr=cls.method_runner)

    def getRunner(self) -> SDKMethodRunner:
        # Initialize these clients from None
        os.environ["LOGLEVEL"] = "DEBUG"
        runner = copy.copy(self.__class__.method_runner)  # type : SDKMethodRunner
        runner.get_jobs_status()
        runner.get_runjob()
        runner.get_job_logs()
        return runner

    def create_job_rec(self):
        return self.sdkmr_test_helper.create_job_rec()

    # TODO Think about what we want to do here, as this is an integration test and not a unit test
    # def test_get_client_groups(self):
    #     runner = self.getRunner()
    #
    #     client_groups = runner._get_client_groups(
    #         "kb_uploadmethods.import_sra_from_staging"
    #     )
    #
    #     expected_groups = "kb_upload"  # expected to fail if CI catalog is updated
    #     self.assertCountEqual(expected_groups, client_groups)
    #     client_groups = runner._get_client_groups("MEGAHIT.run_megahit")
    #     self.assertEqual(0, len(client_groups))
    #
    #     with self.assertRaises(ValueError) as context:
    #         runner._get_client_groups("kb_uploadmethods")
    #
    #     self.assertIn("unrecognized method:", str(context.exception.args))
    #
    # def test_get_module_git_commit(self):
    #
    #     runner = self.getRunner()
    #
    #     git_commit_1 = runner._get_module_git_commit("MEGAHIT.run_megahit", "2.2.1")
    #     self.assertEqual(
    #         "048baf3c2b76cb923b3b4c52008ed77dbe20292d", git_commit_1
    #     )  # TODO: works only in CI
    #
    #     git_commit_2 = runner._get_module_git_commit("MEGAHIT.run_megahit")
    #     self.assertTrue(isinstance(git_commit_2, str))
    #     self.assertEqual(len(git_commit_1), len(git_commit_2))
    #    self.assertNotEqual(git_commit_1, git_commit_2)

    # Status
    @patch("lib.execution_engine2.utils.Condor.Condor", autospec=True)
    def test_cancel_job(self, condor):
        logging.info("\n\n  Test cancel job")
        sdk = self.getRunner()
        sdk.condor = condor

        with sdk.get_mongo_util().mongo_engine_connection():
            job = get_example_job()
            job.user = self.user_id
            job.wsid = self.ws_id
            job.save()
            job_id = job.id

        logging.info(
            f"Created job in wsid={job.wsid} status={job.status} scheduler={job.scheduler_id}. About to cancel {job_id}"
        )
        print("About to cancel job,", job_id)
        sdk.cancel_job(job_id=job_id)

        self.assertEqual(
            Status(sdk.get_mongo_util().get_job(job_id=job_id).status),
            Status.terminated,
        )
        self.assertEqual(
            TerminatedCode(sdk.get_mongo_util().get_job(job_id=job_id).terminated_code),
            TerminatedCode.terminated_by_user,
        )

        with sdk.get_mongo_util().mongo_engine_connection():
            job = get_example_job()
            job.user = self.user_id
            job.wsid = self.ws_id
            job_id = job.save().id

        logging.info(
            f"Created job {job_id} in {job.wsid} status {job.status}. About to cancel"
        )

        sdk.cancel_job(
            job_id=job_id, terminated_code=TerminatedCode.terminated_by_automation.value
        )

        self.assertEqual(
            Status(sdk.get_mongo_util().get_job(job_id=job_id).status),
            Status.terminated,
        )
        self.assertEqual(
            TerminatedCode(sdk.get_mongo_util().get_job(job_id=job_id).terminated_code),
            TerminatedCode.terminated_by_automation,
        )

    # Status
    # flake8: noqa: C901
    @requests_mock.Mocker()
    @patch("lib.execution_engine2.utils.Condor.Condor", autospec=True)
    def test_cancel_job2(self, rq_mock, condor_mock):
        rq_mock.add_matcher(
            run_job_adapter(
                ws_perms_info={"user_id": self.user_id, "ws_perms": {self.ws_id: "a"}}
            )
        )

        user_name = "wsadmin"

        runner = self.getRunner()
        runner.workspace_auth = MagicMock()
        runner.auth.get_user = MagicMock(return_value=user_name)
        runner.is_admin = True
        runner._is_admin = MagicMock(return_value=True)

        runner.workspace_auth.can_read = MagicMock(return_value=True)
        runner.get_permissions_for_workspace = MagicMock(return_value=True)

        # _#get_module_git_commit
        # runner.get_runjob = MagicMock(return_value="git_commit_goes_here")

        runner.get_condor = MagicMock(return_value=condor_mock)
        fixed_rj = EE2RunJob(runner)
        fixed_rj._get_module_git_commit = MagicMock(return_value="hash_goes_here")
        fixed_rj.sdkmr.catalog_utils.list_client_group_configs = MagicMock(
            return_value="cg goes her"
        )

        runner.get_runjob = MagicMock(return_value=fixed_rj)

        # ctx = {"user_id": self.user_id, "wsid": self.ws_id, "token": self.token}
        job = get_example_job().to_mongo().to_dict()
        job["method"] = job["job_input"]["app_id"]
        job["app_id"] = job["job_input"]["app_id"]
        job["service_ver"] = job["job_input"]["service_ver"]

        si = SubmissionInfo(clusterid="test", submit=job, error=None)

        condor_mock.run_job = MagicMock(return_value=si)
        condor_mock.extract_resources = MagicMock(return_value=self.cr)
        print("About to run job with params")
        pprint(job)
        job_id0 = runner.run_job(params=job)
        job_id1 = runner.run_job(params=job)
        job_id2 = runner.run_job(params=job)
        job_id3 = runner.run_job(params=job)
        job_id4 = runner.run_job(params=job)
        print(f"About to cancel job_id1 {job_id1}")
        runner.cancel_job(
            job_id=job_id1,
            terminated_code=TerminatedCode.terminated_by_automation.value,
        )
        print(f"About to cancel job_id2 {job_id2}")
        runner.cancel_job(
            job_id=job_id2, terminated_code=TerminatedCode.terminated_by_admin.value
        )
        print(f"About to cancel job_id3 {job_id3}")
        runner.cancel_job(
            job_id=job_id3, terminated_code=TerminatedCode.terminated_by_user.value
        )
        print(f"About to cancel job_id4 {job_id4}")
        runner.cancel_job(
            job_id=job_id4, terminated_code=TerminatedCode.terminated_by_user.value
        )

        terminated_0 = runner.check_job_canceled(job_id=job_id0)
        terminated_1 = runner.check_job_canceled(job_id=job_id1)
        terminated_2 = runner.check_job_canceled(job_id=job_id2)
        terminated_3 = runner.check_job_canceled(job_id=job_id3)
        terminated_4 = runner.check_job_canceled(job_id=job_id4)
        self.assertTrue(terminated_1["canceled"])
        self.assertTrue(terminated_2["canceled"])
        self.assertTrue(terminated_3["canceled"])
        self.assertTrue(terminated_4["canceled"])
        self.assertFalse(terminated_0["canceled"])

        status0 = runner.check_job(job_id=job_id0)
        status1 = runner.check_job(job_id=job_id1)
        status2 = runner.check_job(job_id=job_id2)
        status3 = runner.check_job(job_id=job_id3)
        status4 = runner.check_job(job_id=job_id4)

        self.assertTrue("terminated_code" not in status0)
        self.assertEquals(
            status1["terminated_code"], TerminatedCode.terminated_by_automation.value
        )
        self.assertEquals(
            status2["terminated_code"], TerminatedCode.terminated_by_admin.value
        )
        self.assertEquals(
            status3["terminated_code"], TerminatedCode.terminated_by_user.value
        )
        self.assertEquals(
            status4["terminated_code"], TerminatedCode.terminated_by_user.value
        )

    # status
    @patch("execution_engine2.db.MongoUtil.MongoUtil", autospec=True)
    def test_check_job_canceled(self, mongo_util):
        # def generateJob(job_id):
        #     j = Job()
        #     j.status = job_id
        #     return j

        #
        # runner.get_mongo_util = MagicMock(return_value=mongo_util)
        # mongo_util.get_job = MagicMock(side_effect=generateJob)
        #
        #
        runner = self.getRunner()
        with self.mongo_util.mongo_engine_connection():
            job_id = self.create_job_rec()

            call_count = 0
            rv = runner.check_job_canceled(job_id)
            self.assertFalse(rv["canceled"])
            self.assertFalse(rv["finished"])
            call_count += 1
            # estimating
            runner.update_job_status(job_id=job_id, status=Status.estimating.value)
            rv = runner.check_job_canceled(job_id)
            self.assertFalse(rv["canceled"])
            self.assertFalse(rv["finished"])
            call_count += 1

            runner.update_job_status(job_id=job_id, status=Status.queued.value)
            rv = runner.check_job_canceled(job_id)
            self.assertFalse(rv["canceled"])
            self.assertFalse(rv["finished"])
            call_count += 1

            runner.update_job_status(job_id=job_id, status=Status.running.value)
            rv = runner.check_job_canceled(job_id)
            self.assertFalse(rv["canceled"])
            self.assertFalse(rv["finished"])
            call_count += 1

            runner.update_job_status(job_id=job_id, status=Status.completed.value)
            rv = runner.check_job_canceled(job_id)
            self.assertFalse(rv["canceled"])
            self.assertTrue(rv["finished"])
            call_count += 1

            runner.update_job_status(job_id=job_id, status=Status.error.value)
            rv = runner.check_job_canceled(job_id)
            self.assertFalse(rv["canceled"])
            self.assertTrue(rv["finished"])
            call_count += 1

            runner.update_job_status(job_id=job_id, status=Status.terminated.value)
            rv = runner.check_job_canceled(job_id)
            self.assertTrue(rv["canceled"])
            self.assertTrue(rv["finished"])
            call_count += 1

    @requests_mock.Mocker()
    @patch("lib.execution_engine2.utils.Condor.Condor", autospec=True)
    def test_run_job_and_add_log(self, rq_mock, condor_mock):
        """
        This test runs a job and then adds logs

        :param condor_mock:
        :return:
        """
        runner = self.getRunner()
        rq_mock.add_matcher(
            run_job_adapter(
                ws_perms_info={"user_id": self.user_id, "ws_perms": {self.ws_id: "a"}}
            )
        )
        runner.get_condor = MagicMock(return_value=condor_mock)
        job = get_example_job(user=self.user_id, wsid=self.ws_id).to_mongo().to_dict()
        job["method"] = job["job_input"]["app_id"]
        job["app_id"] = job["job_input"]["app_id"]
        job["service_ver"] = job["job_input"]["service_ver"]

        si = SubmissionInfo(clusterid="test", submit=job, error=None)
        condor_mock.run_job = MagicMock(return_value=si)
        condor_mock.extract_resources = MagicMock(return_value=self.cr)

        job_id = runner.run_job(params=job)
        logging.info(f"Job id is {job_id} ")

        lines = []
        for item in ["this", "is", "a", "test"]:
            line = {"error": False, "line": item}
            lines.append(line)

        log_pos_1 = runner.add_job_logs(
            job_id=job_id, log_lines=lines
        ).stored_line_count
        logging.info(f"After insert log position is now {log_pos_1}")
        log = runner.view_job_logs(job_id=job_id, skip_lines=None)

        log_lines = log["lines"]
        for i, inserted_line in enumerate(log_lines):
            self.assertEqual(inserted_line["line"], lines[i]["line"])
            self.assertEqual(inserted_line["linepos"], i)

        line1 = {
            "error": False,
            "line": "This is the read deal",
            "ts": str(datetime.now()),
        }
        line2 = {
            "error": False,
            "line": "This is the read deal2",
            "ts": int(datetime.now().timestamp() * 1000),
        }
        line3 = {
            "error": False,
            "line": "This is the read deal3",
            "ts": datetime.now().timestamp(),
        }
        line4 = {
            "error": False,
            "line": "This is the read deal4",
            "ts": str(datetime.now().timestamp()),
        }

        input_lines2 = [line1, line2, line3, line4]

        for line in input_lines2:
            print(line)

        log_pos2 = runner.add_job_logs(
            job_id=job_id, log_lines=input_lines2
        ).stored_line_count
        logging.info(
            f"After inserting timestamped logs,  log position is now {log_pos2}"
        )
        print("Comparing ", log_pos_1, log_pos2, log_pos2 - len(lines))
        self.assertEqual(log_pos_1, log_pos2 - len(lines))

        log = runner.view_job_logs(job_id=job_id, skip_lines=None)
        log_lines = log["lines"]

        print("Before SkipLines Test")
        for i, inserted_line in enumerate(log_lines):
            if i < log_pos_1:
                continue
            print("Checking", i)
            print("Checking to see if", inserted_line["line"])
            print(input_lines2[i - log_pos_1]["line"])
            self.assertEqual(inserted_line["line"], input_lines2[i - log_pos_1]["line"])
            print("SUCCESS")

            time_input = input_lines2[i - log_pos_1]["ts"]
            print("Time input is", time_input)
            if isinstance(time_input, str):
                if time_input.replace(".", "", 1).isdigit():
                    time_input = (
                        float(time_input)
                        if "." in time_input
                        else int(time_input) / 1000.0
                    )
                else:
                    time_input = dateutil.parser.parse(time_input).timestamp()
            elif isinstance(time_input, int):
                time_input = time_input / 1000.0

            print("Time 2 is", time_input)
            self.assertEqual(inserted_line["ts"], int(time_input * 1000))

            error1 = line["error"]

            error2 = input_lines2[i - log_pos_1]["error"]

            print(line)
            print(input_lines2[i - log_pos_1])
            self.assertEqual(error1, error2)

        print("SkipLines Test")

        log = runner.view_job_logs(job_id=job_id, skip_lines=1)
        self.assertEqual(log["lines"][0]["linepos"], 2)

        log = runner.view_job_logs(job_id=job_id, skip_lines=8)
        self.assertEqual(log["lines"], [])
        self.assertEqual(log["last_line_number"], 8)

        # Test limit
        log = runner.view_job_logs(job_id=job_id, limit=2)
        self.assertEqual(len(log["lines"]), 2)
        self.assertEqual(log["lines"][0]["linepos"], 0)
        self.assertEqual(log["lines"][-1]["linepos"], 1)
        self.assertEqual(log["last_line_number"], 1)

        log = runner.view_job_logs(job_id=job_id, limit=3, skip_lines=0)
        self.assertEqual(
            3, len(log["lines"]),
        )
        self.assertEqual(0, log["lines"][0]["linepos"])
        self.assertEqual(2, log["lines"][-1]["linepos"])
        self.assertEqual(log["last_line_number"], 2)

        log = runner.view_job_logs(job_id=job_id, limit=3, skip_lines=5)
        self.assertEqual(
            2, len(log["lines"]),
        )
        self.assertEqual(6, log["lines"][0]["linepos"])
        self.assertEqual(7, log["last_line_number"])

        log = runner.view_job_logs(job_id=job_id, limit=3, skip_lines=8)
        self.assertEqual(log["lines"], [])
        self.assertEqual(log["last_line_number"], 8)

    @patch("lib.execution_engine2.utils.Condor.Condor", autospec=True)
    def test_finish_job(self, condor):

        with self.mongo_util.mongo_engine_connection():
            ori_job_count = Job.objects.count()
            job_id = self.create_job_rec()
            self.assertEqual(ori_job_count, Job.objects.count() - 1)

            job = self.mongo_util.get_job(job_id=job_id)
            self.assertEqual(job.status, "created")
            self.assertFalse(job.finished)

            runner = self.getRunner()
            runner._test_job_permissions = MagicMock(return_value=True)
            runner.catalog_utils.catalog.log_exec_stats = MagicMock(return_value=True)

            # test missing job_id input
            with self.assertRaises(ValueError) as context1:
                logging.info("Finish Job Case 0 Raises Error")
                runner.finish_job(job_id=None)
            self.assertEqual("Please provide a valid job id", str(context1.exception))

            # test finish job with invalid status (This was removed)
            # with self.assertRaises(ValueError) as context2:
            #     logging.info("Finish Job Case 1 Raises Error")
            #     runner.finish_job(job_id=job_id)
            # self.assertIn("Unexpected job status", str(context2.exception))

            # update job status to running

            runner.start_job(job_id=job_id, skip_estimation=True)

            # self.mongo_util.update_job_status(job_id=job_id, status=Status.running.value)
            # job.running = datetime.datetime.utcnow()
            # job.save()

            # test finish job without error
            job_output = dict()
            job_output["version"] = "1"
            job_output["id"] = "5d54bdcb9b402d15271b3208"  # A valid objectid
            job_output["result"] = {"output": "output"}
            logging.info("Case2 : Finish a running job")

            print(f"About to finish job {job_id}. The job status is currently")
            print(runner.get_job_status_field(job_id))
            try:
                runner.finish_job(job_id=job_id, job_output=job_output)
            except:
                pass
            print("Job is now finished, status is")
            print(runner.get_job_status_field(job_id))
            self.assertEqual(
                {"status": "completed"}, runner.get_job_status_field(job_id)
            )

            job = self.mongo_util.get_job(job_id=job_id)
            self.assertEqual(job.status, Status.completed.value)
            self.assertFalse(job.errormsg)
            self.assertTrue(job.finished)
            # if job_output not a dict#
            # job_output2 = job.job_output.to_mongo().to_dict()
            job_output2 = job.job_output
            self.assertEqual(job_output2["version"], "1")
            self.assertEqual(str(job_output2["id"]), job_output["id"])

            # update finished status to running
            with self.assertRaises(InvalidStatusTransitionException):
                self.mongo_util.update_job_status(
                    job_id=job_id, status=Status.running.value
                )

    @patch("lib.execution_engine2.utils.Condor.Condor", autospec=True)
    def test_finish_job_with_error_message(self, condor):

        with self.mongo_util.mongo_engine_connection():
            ori_job_count = Job.objects.count()
            job_id = self.create_job_rec()
            job = self.mongo_util.get_job(job_id=job_id)
            new_count = Job.objects.count()
            self.assertEqual(ori_job_count, new_count - 1)

        runner = self.getRunner()
        condor.get_job_info = MagicMock(return_value={})
        condor.get_job_resource_info = MagicMock(return_value={})
        runner.condor = condor
        runner._send_exec_stats_to_catalog = MagicMock(return_value=True)
        runner.catalog_utils = MagicMock(return_value=True)
        runner._test_job_permissions = MagicMock(return_value=True)

        # with self.assertRaises(InvalidStatusTransitionException):
        #     runner.finish_job(job_id=job_id, error_message="error message")

        runner.start_job(job_id=job_id, skip_estimation=True)
        time.sleep(2)
        job = self.mongo_util.get_job(job_id=job_id)
        print("Job is", job.to_mongo().to_dict())
        runner.finish_job(job_id=job_id, error_message="error message")
        job2 = self.mongo_util.get_job(job_id=job_id)
        print("Job2 is", job2.to_mongo().to_dict())
        job = self.mongo_util.get_job(job_id=job_id)

        self.assertEqual(job.status, "error")
        self.assertEqual(job.errormsg, "error message")
        self.assertEqual(job.error_code, 1)
        self.assertIsNone(job.error)
        self.assertTrue(job.finished)

        with self.mongo_util.mongo_engine_connection():
            job_id = runner.update_job_status(
                job_id, "running"
            )  # put job back to running status

        error = {
            "message": "error message",
            "code'": -32000,
            "name": "Server error",
            "error": """Traceback (most recent call last):\n  File "/kb/module/bin/../lib/simpleapp/simpleappServer.py""",
        }

        runner.finish_job(
            job_id=job_id, error_message="error message", error=error, error_code=0
        )

        job = self.mongo_util.get_job(job_id=job_id)

        self.assertEqual(job.status, "error")
        self.assertEqual(job.errormsg, "error message")
        self.assertEqual(job.error_code, 0)
        self.assertCountEqual(job.error, error)

        self.mongo_util.get_job(job_id=job_id).delete()
        self.assertEqual(ori_job_count, Job.objects.count())

    @requests_mock.Mocker()
    def test_check_job_global_perm(self, rq_mock):
        rq_mock.add_matcher(
            run_job_adapter(
                ws_perms_info={"user_id": self.user_id, "ws_perms": {self.ws_id: "n"}},
                ws_perms_global=[self.ws_id],
                user_roles=[],
            )
        )
        with self.mongo_util.mongo_engine_connection():
            ori_job_count = Job.objects.count()
            job_id = self.create_job_rec()
            self.assertEqual(ori_job_count, Job.objects.count() - 1)

            job = self.mongo_util.get_job(job_id=job_id)
            self.assertEqual(job.status, "created")
            self.assertFalse(job.finished)
            self.assertFalse(job.running)
            self.assertFalse(job.estimating)

            # test check_job
            runner = self.getRunner()
            job_state = runner.check_job(job_id)
            json.dumps(job_state)  # make sure it's JSON serializable
            self.assertTrue(validate_job_state(job_state))
            self.assertEqual(job_state["status"], "created")
            self.assertEqual(job_state["wsid"], self.ws_id)

            self.assertAlmostEqual(
                job_state["created"] / 1000.0, job_state["updated"] / 1000.0, places=-1
            )

            # test globally
            job_states = runner.get_jobs_status().check_workspace_jobs(self.ws_id)
            self.assertTrue(job_id in job_states)
            self.assertEqual(job_states[job_id]["status"], "created")

            # now test with a different user
            other_method_runner = SDKMethodRunner(
                self.cfg, user_id="some_other_user", token="other_token"
            )
            job_states = other_method_runner.get_jobs_status().check_workspace_jobs(
                self.ws_id
            )
            self.assertTrue(job_id in job_states)
            self.assertEqual(job_states[job_id]["status"], "created")

    @requests_mock.Mocker()
    def test_check_job_ok(self, rq_mock):
        rq_mock.add_matcher(
            run_job_adapter(
                ws_perms_info={"user_id": self.user_id, "ws_perms": {self.ws_id: "a"}},
                user_roles=[],
            )
        )

        with self.mongo_util.mongo_engine_connection():
            ori_job_count = Job.objects.count()
            job_id = self.create_job_rec()
            job_id_1 = self.create_job_rec()
            job_id_fake = str(bson.objectid.ObjectId())
            print(f"Saved job_id {job_id}")
            print(f"Saved job_id_1 {job_id_1}")
            print(f"Created fake {job_id_fake}")

            new_count = Job.objects.count()
            self.assertEqual(ori_job_count, new_count - 2)

            job = self.mongo_util.get_job(job_id=job_id)
            self.assertEqual(job.status, "created")
            self.assertFalse(job.finished)
            self.assertFalse(job.running)
            self.assertFalse(job.estimating)

            runner = self.getRunner()
            runner._test_job_permissions = MagicMock(return_value=True)

            # test missing job_id input
            with self.assertRaises(ValueError) as context:
                runner.check_job(None)
                self.assertEqual("Please provide valid job_id", str(context.exception))

            # test check_job in a regular way
            job_state = runner.check_job(job_id)
            json.dumps(job_state)  # make sure it's JSON serializable
            self.assertTrue(validate_job_state(job_state))
            self.assertEqual(job_state["status"], "created")
            self.assertEqual(job_state["wsid"], self.ws_id)
            # Test both
            job_state1 = runner.check_job(job_id_1)
            self.assertEqual(job_state1["status"], "created")

            print(f'Job status of {job_id}={job_state["status"]}')
            print(f'Job status of {job_id_1}={job_state1["status"]}')

            # test check_job with exclude_fields
            job_state_exclude = runner.check_job(job_id, exclude_fields=["status"])
            self.assertFalse("status" in job_state_exclude.keys())
            self.assertEqual(job_state_exclude["wsid"], self.ws_id)

            # test check_job with exclude_fields
            job_state_exclude2 = runner.check_job(job_id, exclude_fields=["status"])
            self.assertFalse("status" in job_state_exclude2.keys())
            self.assertEqual(job_state_exclude2["wsid"], self.ws_id)

            # test check_jobs
            job_states_rl_0 = runner.check_jobs(
                [job_id, job_id_1, job_id_fake], return_list=0
            )
            logging.info(
                json.dumps(job_states_rl_0)
            )  # make sure it's JSON serializable
            self.assertEqual(len(job_states_rl_0.keys()), 3)
            self.assertEqual(list(job_states_rl_0.keys())[0], job_id)
            self.assertEqual(list(job_states_rl_0.keys())[1], job_id_1)
            self.assertEqual(list(job_states_rl_0.keys())[2], job_id_fake)
            self.assertTrue(validate_job_state(job_states_rl_0[job_id]))
            self.assertTrue(job_id in job_states_rl_0)
            self.assertEqual(job_states_rl_0[job_id]["status"], "created")
            self.assertEqual(job_states_rl_0[job_id]["wsid"], self.ws_id)

            # test check_jobs return list
            job_states_rl_1 = runner.check_jobs(
                [job_id, job_id_1, job_id_fake], return_list=1
            )["job_states"]
            json.dumps(job_states_rl_1)  # make sure it's JSON serializable
            self.assertEqual(len(job_states_rl_1), 3)
            self.assertEqual(job_states_rl_1[0]["job_id"], job_id)
            self.assertEqual(job_states_rl_1[1]["job_id"], job_id_1)
            self.assertEqual(job_states_rl_1[2], [])
            self.assertTrue(isinstance(job_states_rl_1, list))
            print(type(job_states_rl_1))
            self.assertCountEqual(job_states_rl_1, list(job_states_rl_0.values()))

            job_states_list_rl_t = runner.check_jobs(
                [job_id, job_id_1], return_list="True"
            )["job_states"]
            json.dumps(job_states_list_rl_t)  # make sure it's JSON serializable
            self.assertEqual(job_states_list_rl_t[0]["job_id"], job_id)
            self.assertEqual(job_states_list_rl_t[1]["job_id"], job_id_1)
            self.assertTrue(isinstance(job_states_list_rl_t, list))
            self.assertCountEqual(
                job_states_list_rl_t, list(job_states_rl_0.values())[:2]
            )

            # test check_jobs with exclude_fields
            job_states_rl0_exclude_wsid = runner.check_jobs(
                [job_id], exclude_fields=["wsid"], return_list=0
            )
            self.assertTrue(job_id in job_states_rl0_exclude_wsid)
            self.assertFalse("wsid" in job_states_rl0_exclude_wsid[job_id].keys())
            self.assertEqual(job_states_rl0_exclude_wsid[job_id]["status"], "created")

            # test check_workspace_jobs
            job_states_from_workspace_check = runner.get_jobs_status().check_workspace_jobs(
                self.ws_id, return_list="False"
            )
            for job_id_from_wsid in job_states_from_workspace_check:
                self.assertTrue(job_states_from_workspace_check[job_id_from_wsid])
            print("Job States are")
            for job_key in job_states_from_workspace_check:
                if job_key in job_states_rl_1:
                    print(
                        job_key,
                        job_states_from_workspace_check[job_key]["status"],
                        runner.check_job(job_id=job_key)["status"],
                        job_states_rl_0[job],
                    )

            json.dumps(
                job_states_from_workspace_check
            )  # make sure it's JSON serializable
            self.assertTrue(job_id in job_states_from_workspace_check)
            self.assertEqual(
                job_states_from_workspace_check[job_id]["status"], "created"
            )
            self.assertEqual(
                job_states_from_workspace_check[job_id]["wsid"], self.ws_id
            )

            self.assertTrue(job_id_1 in job_states_from_workspace_check)
            self.assertEqual(
                job_states_from_workspace_check[job_id_1]["status"], "created"
            )
            self.assertEqual(
                job_states_from_workspace_check[job_id_1]["wsid"], self.ws_id
            )

            # test check_workspace_jobs with exclude_fields
            job_states_with_exclude_wsid = runner.get_jobs_status().check_workspace_jobs(
                self.ws_id, exclude_fields=["wsid"], return_list=False
            )

            logging.info(
                json.dumps(job_states_with_exclude_wsid)
            )  # make sure it's JSON serializable
            self.assertTrue(job_id in job_states_with_exclude_wsid)
            self.assertFalse("wsid" in job_states_with_exclude_wsid[job_id].keys())
            self.assertEqual(job_states_with_exclude_wsid[job_id]["status"], "created")
            self.assertTrue(job_id_1 in job_states_with_exclude_wsid)
            self.assertFalse("wsid" in job_states_with_exclude_wsid[job_id_1].keys())
            self.assertEqual(
                job_states_with_exclude_wsid[job_id_1]["status"], "created"
            )

            with self.assertRaises(PermissionError) as e:
                runner.get_jobs_status().check_workspace_jobs(1234)
            self.assertIn(
                f"User {self.user_id} does not have permission to read jobs in workspace {1234}",
                str(e.exception),
            )

    @staticmethod
    def create_job_from_job(job, new_job_id):
        j = Job()
        j.id = new_job_id
        j.wsid = job.wsid
        j.user = job.user
        j.authstrat = job.authstrat
        j.status = job.status
        j.finished = new_job_id.generation_time.timestamp()
        j.job_input = job.job_input
        return j

    def replace_job_id(self, job1, new_id):
        with self.mongo_util.mongo_engine_connection():
            job2 = self.create_job_from_job(job1, new_id)
            job2.save()
            print("Saved job with id", job2.id, job2.id.generation_time)
            job1.delete()

    # flake8: noqa: C901
    @patch("lib.execution_engine2.utils.Condor.Condor", autospec=True)
    def test_check_jobs_date_range(self, condor_mock):
        user_name = "wsadmin"

        runner = self.getRunner()

        runner.workspace_auth = MagicMock()
        runner.auth.get_user = MagicMock(return_value=user_name)
        runner.is_admin = True
        runner.check_is_admin = MagicMock(return_value=True)

        runner.workspace_auth.can_read = MagicMock(return_value=True)

        self.mock = MagicMock(return_value=True)
        runner._ee2_runjob._get_module_git_commit = MagicMock(
            return_value="hash_goes_here"
        )

        # fixed_rj = RunJob(runner)
        # fixed_rj._get_module_git_commit = MagicMock(return_value='hash_goes_here')

        runner._get_module_git_commit = MagicMock(return_value="git_commit_goes_here")

        runner.get_condor = MagicMock(return_value=condor_mock)
        # ctx = {"user_id": self.user_id, "wsid": self.ws_id, "token": self.token}
        job = get_example_job().to_mongo().to_dict()
        job["method"] = job["job_input"]["app_id"]
        job["app_id"] = job["job_input"]["app_id"]
        job["service_ver"] = job["job_input"]["service_ver"]

        si = SubmissionInfo(clusterid="test", submit=job, error=None)
        condor_mock.run_job = MagicMock(return_value=si)
        condor_mock.extract_resources = MagicMock(return_value=self.cr)

        job_id1 = runner.run_job(params=job)
        job_id2 = runner.run_job(params=job)
        job_id3 = runner.run_job(params=job)
        job_id4 = runner.run_job(params=job)
        job_id5 = runner.run_job(params=job)
        job_id6 = runner.run_job(params=job)
        time.sleep(1)

        new_job_ids = []

        now = datetime.utcnow()
        last_month = now - timedelta(days=30)
        last_month_and_1_hour = now - timedelta(days=30) - timedelta(hours=1)

        last_week = now - timedelta(days=7)
        yesterday = now - timedelta(days=1)
        tomorrow = now + timedelta(days=1)
        day_after = now + timedelta(days=2)

        with self.mongo_util.mongo_engine_connection():
            # Last Month
            job = Job.objects.with_id(job_id1)  # type : Job
            new_id_last_month = ObjectId.from_datetime(last_month)
            print(last_month, new_id_last_month, new_id_last_month.generation_time)

            print("About to replace job id")
            print(job)
            print(new_id_last_month)
            self.replace_job_id(job, new_id_last_month)
            new_job_ids.append(str(new_id_last_month))

            # Last week
            job = Job.objects.with_id(job_id2)  # type : Job
            new_id_last_week = ObjectId.from_datetime(last_week)
            self.replace_job_id(job, new_id_last_week)
            new_job_ids.append(str(new_id_last_week))

            # Yesterday
            job = Job.objects.with_id(job_id3)  # type : Job
            new_id_yesterday = ObjectId.from_datetime(yesterday)
            self.replace_job_id(job, new_id_yesterday)
            new_job_ids.append(str(new_id_yesterday))

            # Now
            job = Job.objects.with_id(job_id4)  # type : Job
            new_id_now = ObjectId.from_datetime(now)
            self.replace_job_id(job, new_id_now)
            new_job_ids.append(str(new_id_now))

            # Tomorrow
            job = Job.objects.with_id(job_id5)  # type : Job
            new_id_tomorrow = ObjectId.from_datetime(tomorrow)
            self.replace_job_id(job, new_id_tomorrow)
            new_job_ids.append(str(new_id_tomorrow))

            # Day After
            job = Job.objects.with_id(job_id6)  # type : Job
            new_id_day_after = ObjectId.from_datetime(day_after)
            self.replace_job_id(job, new_id_day_after)
            new_job_ids.append(str(new_id_day_after))

        # JOB ID GETS GENERATED HERE
        with self.mongo_util.mongo_engine_connection():
            ori_job_count = Job.objects.count()
            job_id = self.create_job_rec()
            self.assertEqual(ori_job_count, Job.objects.count() - 1)

            job = self.mongo_util.get_job(job_id=job_id)
            self.assertEqual(job.status, "created")
            self.assertFalse(job.finished)
            self.false = self.assertFalse(job.running)
            self.assertFalse(job.estimating)

            runner.check_permission_for_job = MagicMock(return_value=True)
            # runner.get_permissions_for_workspace = MagicMock(
            #     return_value=SDKMethodRunner.WorkspacePermissions.ADMINISTRATOR
            # )
            runner.is_admin = MagicMock(return_value=True)

            print(
                "Test case 1. Retrieving Jobs from last_week and tomorrow_max (yesterday and now jobs) "
            )
            job_state = runner.check_jobs_date_range_for_user(
                creation_end_time=str(tomorrow),
                creation_start_time=last_week.timestamp(),  # test timestamp input
                user="ALL",
            )
            count = 0
            for js in job_state["jobs"]:
                job_id = js["job_id"]
                print("Job is id", job_id)
                if job_id in new_job_ids:
                    count += 1
                    self.assertIn(js["status"], ["created", "queued"])
                    print(js["created"])
                    print(type(js["created"]))
                    date = SDKMethodRunner.check_and_convert_time(js["created"])
                    ts = date
                    print(
                        f"Creation date {date}, LastWeek:{last_week}, Tomorrow{tomorrow})"
                    )
                    print(ts, last_week.timestamp())
                    self.assertTrue(float(ts) >= last_week.timestamp())
                    print(ts, tomorrow.timestamp())
                    self.assertTrue(float(ts) <= tomorrow.timestamp())
            self.assertEqual(2, count)

            print(
                "Test case 2A. Retrieving Jobs from last_month and tomorrow_max (last_month, last_week, yesterday and now jobs) "
            )

            job_state = runner.check_jobs_date_range_for_user(
                creation_end_time=str(
                    tomorrow.timestamp()
                ),  # test timestamp string input
                creation_start_time=last_month_and_1_hour,  # test datetime input
                user="ALL",
            )

            count = 0
            for js in job_state["jobs"]:
                job_id = js["job_id"]
                print("Job is id", job_id)
                if job_id in new_job_ids:
                    count += 1
                    self.assertIn(js["status"], ["created", "queued"])
                    date = SDKMethodRunner.check_and_convert_time(js["created"])
                    ts = date
                    print(date, last_week, tomorrow)
                    print(ts, last_week.timestamp(), tomorrow.timestamp())
                    self.assertTrue(ts > last_month_and_1_hour.timestamp())
                    self.assertTrue(ts < tomorrow.timestamp())
            self.assertEqual(4, count)

            print("Found all of the jobs", len(new_job_ids))

            with self.assertRaises(Exception) as context:
                job_state = runner.check_jobs_date_range_for_user(
                    creation_end_time=str(yesterday),
                    creation_start_time=str(tomorrow),
                    user="ALL",
                )
                self.assertEqual(
                    "The start date cannot be greater than the end date.",
                    str(context.exception),
                )

            print("Test case 2B. Same as above but with FAKE user (NO ADMIN) ")
            runner.is_admin = False
            runner.check_is_admin = MagicMock(return_value=False)
            with self.assertRaisesRegex(
                AuthError,
                "You are not authorized to view all records or records for others.",
            ) as error:
                job_state = runner.check_jobs_date_range_for_user(
                    creation_end_time=str(tomorrow),
                    creation_start_time=str(last_month_and_1_hour),
                    user="FAKE",
                )
                print("Exception raised is", error)

            print("Test case 2C. Same as above but with FAKE_TEST_USER + ADMIN) ")
            runner.is_admin = True
            runner.check_is_admin = MagicMock(return_value=True)
            job_state = runner.check_jobs_date_range_for_user(
                creation_end_time=str(tomorrow),
                creation_start_time=str(last_month_and_1_hour),
                user=user_name,
            )

            count = 0
            for js in job_state["jobs"]:
                job_id = js["job_id"]
                print("Job is id", job_id)
                if job_id in new_job_ids:
                    count += 1
                    self.assertIn(js["status"], ["created", "queued"])
                    date = SDKMethodRunner.check_and_convert_time(js["created"])
                    ts = date
                    print(date, last_week, tomorrow)
                    print(ts, last_week.timestamp(), tomorrow.timestamp())
                    self.assertTrue(ts > last_month_and_1_hour.timestamp())
                    self.assertTrue(ts < tomorrow.timestamp())

            # May need to change this if other db entries get added
            self.assertEqual(4, count)

            print("Found all of the jobs", len(new_job_ids))

            print("Test case 3. Assert Raises error")

            with self.assertRaises(Exception) as context:
                job_state = runner.check_jobs_date_range_for_user(
                    creation_end_time=str(yesterday),
                    creation_start_time=str(tomorrow),
                    user="ALL",
                )
                self.assertEqual(
                    "The start date cannot be greater than the end date.",
                    str(context.exception),
                )

            print("Test case 4, find the original job")
            job_state = runner.check_jobs_date_range_for_user(
                creation_end_time=str(tomorrow),
                creation_start_time=str(last_month_and_1_hour),
                user=user_name,
            )
            self.assertTrue(len(job_state["jobs"][0].keys()) > 0)
            print(f"Checking {job_id}")

            found = False
            for job in job_state["jobs"]:
                if job_id == job["job_id"]:
                    found = True

            if found is False:
                raise Exception("Didn't find the original job")

            print(job_state)

            print("Test 5, find the original job, but with projections")
            job_states = runner.check_jobs_date_range_for_user(
                creation_end_time=str(tomorrow),
                creation_start_time=str(last_month_and_1_hour),
                user=user_name,
                job_projection=["wsid"],
            )
            job_state_with_proj = None
            for job in job_states["jobs"]:
                if job_id == job["job_id"]:
                    job_state_with_proj = job

            example_job_stat = {
                "_id": "5d892ede9ea3d7d3b824dbff",
                "authstrat": "kbaseworkspace",
                "wsid": 9999,
                "updated": "2019-09-23 20:45:19.468032",
                "job_id": "5d892ede9ea3d7d3b824dbff",
                "created": "2019-09-23 20:45:18+00:00",
            }

            required_headers = list(example_job_stat.keys())
            required_headers.append("wsid")

            for member in required_headers:
                self.assertIn(member, job_state_with_proj)
            self.assertNotIn("status", job_state_with_proj)

            print("Test 6a, find the original job, but with projections and filters")
            job_state = runner.check_jobs_date_range_for_user(
                creation_end_time=str(tomorrow),
                creation_start_time=str(last_month_and_1_hour),
                user="ALL",
                job_projection=["wsid", "status"],
                job_filter={"wsid": 9999},
            )

            for record in job_state["jobs"]:

                print(record)
                if record["wsid"] != 9999:
                    raise Exception("Only records with wsid 9999 should be allowed")
                self.assertIn("wsid", record)
                self.assertIn("status", record)
                self.assertNotIn("service_ver", record)
            print("job state is", "len is", len(job_state["jobs"]))

            self.assertTrue(len(job_state["jobs"]) >= 1)

            print("Test 6b, find the original job, but with projections and filters")
            job_state2 = runner.check_jobs_date_range_for_user(
                creation_end_time=str(tomorrow),
                creation_start_time=str(last_month_and_1_hour),
                user="ALL",
                job_projection=["wsid", "status"],
                job_filter=["wsid=123"],
            )

            for record in job_state2["jobs"]:

                if record["wsid"] != 123:
                    print(record)
                    print("ID IS", record["wsid"])
                    raise Exception("Only records with wsid 123 should be allowed")
                self.assertIn("wsid", record)
                self.assertIn("status", record)
                self.assertNotIn("service_ver", record)

            print(len(job_state2["jobs"]))
            self.assertTrue(len(job_state2["jobs"]) > 0)

            print(
                "Test 7, find same jobs as test 2 or 3, but also filter, project, and limit"
            )
            job_state_limit = runner.check_jobs_date_range_for_user(
                creation_end_time=str(tomorrow),
                creation_start_time=str(last_month_and_1_hour),
                user="ALL",
                job_projection=["wsid", "status"],
                job_filter=["wsid=123"],
                limit=2,
            )

            self.assertTrue(len(job_state_limit["jobs"]) > 0)

            print(
                "Test 8, ascending and descending (maybe should verify jobs count > 2)"
            )
            job_state_limit_asc = runner.check_jobs_date_range_for_user(
                creation_end_time=str(tomorrow),
                creation_start_time=str(last_month_and_1_hour),
                user="ALL",
                job_projection=["wsid", "status"],
                ascending="True",
            )

            epoch = datetime.utcfromtimestamp(0)

            job_id_temp = str(ObjectId.from_datetime(epoch))
            for item in job_state_limit_asc["jobs"]:
                job_id = item["job_id"]
                if ObjectId(job_id) > ObjectId(job_id_temp):
                    job_id_temp = job_id
                else:
                    raise Exception(
                        "Not ascending"
                        + "JobIdPrev"
                        + str(job_id_temp)
                        + "JobIdNext"
                        + str(job_id)
                    )

            job_state_limit_desc = runner.check_jobs_date_range_for_user(
                creation_end_time=str(tomorrow),
                creation_start_time=str(last_month_and_1_hour),
                user="ALL",
                job_projection=["wsid", "status"],
                ascending="False",
            )

            # TimeDelta Over 9999 days
            job_id_temp = str(ObjectId.from_datetime(now + timedelta(days=9999)))

            for item in job_state_limit_desc["jobs"]:
                job_id = item["job_id"]
                if ObjectId(job_id) < ObjectId(job_id_temp):
                    job_id_temp = job_id
                else:
                    raise Exception(
                        "Not Descending"
                        + "JobIdPrev:"
                        + str(job_id_temp)
                        + "JobIdNext:"
                        + str(job_id)
                    )

            for key in job_state_limit_desc.keys():
                print(key)
                print(job_state_limit_desc[key])


# TODO  TEST _finish_job_with_success, TEST finish_job_with_error
