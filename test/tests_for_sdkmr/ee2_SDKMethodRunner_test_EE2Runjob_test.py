# -*- coding: utf-8 -*-
import copy
import logging
import os
import unittest
from configparser import ConfigParser
from unittest.mock import patch

import requests_mock
from mock import MagicMock

from lib.execution_engine2.db.MongoUtil import MongoUtil
from lib.execution_engine2.db.models.models import Job
from lib.execution_engine2.sdk.SDKMethodRunner import SDKMethodRunner
from lib.execution_engine2.utils.CondorTuples import SubmissionInfo, CondorResources
from test.utils_shared.test_utils import bootstrap, get_example_job, run_job_adapter
from tests_for_db.mongo_test_helper import MongoTestHelper

logging.basicConfig(level=logging.INFO)
bootstrap()

from test.tests_for_sdkmr.ee2_SDKMethodRunner_test_utils import ee2_sdkmr_test_helper


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
        runner = copy.copy(self.__class__.method_runner)  # type : SDKMethodRunner
        runner.get_jobs_status()
        runner.get_runjob()
        runner.get_job_logs()
        return runner

    def create_job_rec(self):
        return self.sdkmr_test_helper.create_job_rec()

    def test_init_ok(self):
        class_attri = ["config", "catalog_utils", "workspace", "mongo_util", "condor"]
        runner = self.getRunner()
        self.assertTrue(set(class_attri) <= set(runner.__dict__.keys()))

    def test_init_job_rec(self):
        with self.mongo_util.mongo_engine_connection():
            ori_job_count = Job.objects.count()
            runner = self.getRunner()

            job_params = {
                "wsid": self.ws_id,
                "method": "MEGAHIT.run_megahit",
                "app_id": "MEGAHIT/run_megahit",
                "service_ver": "2.2.1",
                "params": [
                    {
                        "workspace_name": "wjriehl:1475006266615",
                        "read_library_refs": ["18836/5/1"],
                        "output_contigset_name": "rhodo_contigs",
                        "recipe": "auto",
                        "assembler": None,
                        "pipeline": None,
                        "min_contig_len": None,
                    }
                ],
                "source_ws_objects": ["a/b/c", "e/d"],
                "parent_job_id": "9998",
                "meta": {"tag": "dev", "token_id": "12345"},
            }

            job_id = runner.get_runjob()._init_job_rec(self.user_id, job_params)

            self.assertEqual(ori_job_count, Job.objects.count() - 1)

            job = Job.objects.get(id=job_id)

            self.assertEqual(job.user, self.user_id)
            self.assertEqual(job.authstrat, "kbaseworkspace")
            self.assertEqual(job.wsid, self.ws_id)

            job_input = job.job_input

            self.assertEqual(job_input.wsid, self.ws_id)
            self.assertEqual(job_input.method, "MEGAHIT.run_megahit")
            self.assertEqual(job_input.app_id, "MEGAHIT/run_megahit")
            # TODO this is an integration test
            # self.assertEqual(job_input.service_ver, "2.2.1")
            self.assertEqual(
                job_input.service_ver, "048baf3c2b76cb923b3b4c52008ed77dbe20292d"
            )

            self.assertCountEqual(job_input.source_ws_objects, ["a/b/c", "e/d"])
            self.assertEqual(job_input.parent_job_id, "9998")

            narrative_cell_info = job_input.narrative_cell_info
            self.assertEqual(narrative_cell_info.tag, "dev")
            self.assertEqual(narrative_cell_info.token_id, "12345")
            self.assertFalse(narrative_cell_info.status)

            self.assertFalse(job.job_output)

            self.mongo_util.get_job(job_id=job_id).delete()
            self.assertEqual(ori_job_count, Job.objects.count())

    def test_get_job_params(self):

        with self.mongo_util.mongo_engine_connection():
            ori_job_count = Job.objects.count()
            job_id = self.create_job_rec()
            self.assertEqual(ori_job_count, Job.objects.count() - 1)

            runner = self.getRunner()
            runner._test_job_permissions = MagicMock(return_value=True)
            params = runner.get_job_params(job_id)

            expected_params_keys = [
                "wsid",
                "method",
                "params",
                "service_ver",
                "app_id",
                "source_ws_objects",
                "parent_job_id",
            ]
            self.assertCountEqual(params.keys(), expected_params_keys)
            self.assertEqual(params["wsid"], self.ws_id)
            self.assertEqual(params["method"], "MEGAHIT.run_megahit")
            self.assertEqual(params["app_id"], "MEGAHIT/run_megahit")
            self.assertEqual(params["service_ver"], "2.2.1")
            self.assertCountEqual(params["source_ws_objects"], ["a/b/c", "e/d"])
            self.assertEqual(params["parent_job_id"], "9998")

            self.mongo_util.get_job(job_id=job_id).delete()
            self.assertEqual(ori_job_count, Job.objects.count())

    def test_start_job(self):

        with self.mongo_util.mongo_engine_connection():
            ori_job_count = Job.objects.count()
            job_id = self.create_job_rec()
            self.assertEqual(ori_job_count, Job.objects.count() - 1)

            job = self.mongo_util.get_job(job_id=job_id)
            self.assertEqual(job.status, "created")
            self.assertFalse(job.finished)
            self.assertFalse(job.running)
            self.assertFalse(job.estimating)

            runner = self.getRunner()
            runner._test_job_permissions = MagicMock(return_value=True)

            # test missing job_id input
            with self.assertRaises(ValueError) as context:
                runner.start_job(None)
                self.assertEqual("Please provide valid job_id", str(context.exception))

            # start a created job, set job to estimation status
            runner.start_job(job_id, skip_estimation=False)

            job = self.mongo_util.get_job(job_id=job_id)
            self.assertEqual(job.status, "estimating")
            self.assertFalse(job.running)
            self.assertTrue(job.estimating)

            # start a estimating job, set job to running status
            runner.start_job(job_id, skip_estimation=False)

            job = self.mongo_util.get_job(job_id=job_id)
            self.assertEqual(job.status, "running")
            self.assertTrue(job.running)
            self.assertTrue(job.estimating)

            # test start a job with invalid status
            with self.assertRaises(ValueError) as context:
                runner.start_job(job_id)
            self.assertIn("Unexpected job status", str(context.exception))

            self.mongo_util.get_job(job_id=job_id).delete()
            self.assertEqual(ori_job_count, Job.objects.count())

    @requests_mock.Mocker()
    @patch("lib.execution_engine2.utils.Condor.Condor", autospec=True)
    def test_run_job(self, rq_mock, condor_mock):
        rq_mock.add_matcher(
            run_job_adapter(
                ws_perms_info={"user_id": self.user_id, "ws_perms": {self.ws_id: "a"}}
            )
        )
        runner = self.getRunner()
        runner.get_condor = MagicMock(return_value=condor_mock)
        job = get_example_job(user=self.user_id, wsid=self.ws_id).to_mongo().to_dict()
        job["method"] = job["job_input"]["app_id"]
        job["app_id"] = job["job_input"]["app_id"]
        job["service_ver"] = job["job_input"]["service_ver"]

        si = SubmissionInfo(clusterid="test", submit=job, error=None)
        condor_mock.run_job = MagicMock(return_value=si)
        condor_mock.extract_resources = MagicMock(return_value=self.cr)

        job_id = runner.run_job(params=job)
        print(f"Job id is {job_id} ")

    @requests_mock.Mocker()
    @patch("lib.execution_engine2.utils.Condor.Condor", autospec=True)
    def test_run_job_fail(self, rq_mock, condor_mock):
        rq_mock.add_matcher(
            run_job_adapter(
                ws_perms_info={"user_id": self.user_id, "ws_perms": {self.ws_id: "a"}}
            )
        )
        runner = self.getRunner()

        job = get_example_job(user=self.user_id, wsid=self.ws_id).to_mongo().to_dict()
        job["method"] = job["job_input"]["app_id"]
        job["app_id"] = job["job_input"]["app_id"]
        job["service_ver"] = job["job_input"]["service_ver"]

        si = SubmissionInfo(clusterid="test", submit=job, error=None)
        condor_mock.run_job = MagicMock(return_value=si)
        condor_mock.extract_resources = MagicMock(return_value=self.cr)

        with self.assertRaises(expected_exception=RuntimeError):
            runner.run_job(params=job)
