# -*- coding: utf-8 -*-
import unittest

from mock import MagicMock

from lib.execution_engine2.sdk.SDKMethodRunner import SDKMethodRunner
from lib.execution_engine2.utils.CondorTuples import CondorResources
from test.utils_shared.test_utils import bootstrap

bootstrap()
import os
from configparser import ConfigParser
import copy
from mock import patch
from lib.execution_engine2.utils.Condor import Condor
from lib.execution_engine2.utils.CondorTuples import SubmissionInfo
from test.utils_shared.test_utils import get_sample_job_params
from inspect import getmembers, isfunction, getfullargspec

bootstrap()


class EE2TestAdminMode(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        config_file = os.environ.get("KB_DEPLOYMENT_CONFIG", "test/deploy.cfg")
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

        cls.cr = CondorResources(
            request_cpus="1",
            request_disk="1GB",
            request_memory="100M",
            client_group="njs",
        )

        cls.submit_info = SubmissionInfo

        cls.ADMIN_WRITE_ROLE = "EE2_ADMIN"

    def setUp(self) -> None:
        """
        Patch out Catalog and Condor
        :return:
        """
        self.catalog_patch = patch(
            "lib.installed_clients.CatalogClient.Catalog.get_module_version"
        )
        self.catalog = self.catalog_patch.start()
        self.catalog.return_value = {"git_commit_hash": "moduleversiongoeshere"}

        si = SubmissionInfo(clusterid="123", submit={"scheduler_id": "123"}, error=None)
        self.condor_patch = patch.object(Condor, "run_job", return_value=si)
        condor = self.condor_patch.start()
        condor.get_job_info = MagicMock(return_value="")
        condor.get_job_resource_info = MagicMock(return_value="njs")
        condor.extract_resources = MagicMock(return_value=self.cr)

        self.condor = condor

        self.setup_runner = self.getRunner()
        self.method_1 = "module_name.function_name"
        self.job_params_1 = get_sample_job_params(method=self.method_1, wsid=self.ws_id)

        # TODO
        # PATCH OUT LOGIN/WORKSPACE HERE
        # self.good_job_id_user1 = setup_runner.run_job(params=job_params_1,as_admin=False)
        # self.good_job_id_user2 = setup_runner.run_job(params=job_params_1,as_admin=False)

    def tearDown(self) -> None:
        self.catalog_patch.stop()
        self.condor_patch.stop()

    def getRunner(self) -> SDKMethodRunner:
        # Initialize these clients from None
        runner = copy.copy(self.__class__.method_runner)  # type : SDKMethodRunner
        runner.get_jobs_status()
        runner.get_runjob()
        runner.get_job_logs()

        return runner

    # function_inputs = {"add_job_logs": {"job_id": 123, "log_lines": logline}}

    def test_regular_user(self):
        runner = self.getRunner()
        functions_list = [o for o in getmembers(runner.__class__) if isfunction(o[1])]

        as_admin_functions = []
        for function in functions_list:
            if "as_admin" in getfullargspec(function[1]).args:
                as_admin_functions.append(function[0])

        for function in as_admin_functions:
            print("Testing function", function)
            print(getattr(runner, function)())

    def test_admin_with_read_only(self):
        pass

    def test_admin_with_write_only(self):
        pass

    def test_anonymous_user(self):
        pass

    # TODO
    # This file can help standardize the Exceptions handled by these functions..
    # TODO This file is an idea for a way to automatically test new functiosn with "as_admin" in their args
