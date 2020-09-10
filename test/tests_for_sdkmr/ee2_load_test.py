# -*- coding: utf-8 -*-
import copy
import logging
import os
import queue
import threading
import time
import unittest
from configparser import ConfigParser
from unittest.mock import patch

from lib.execution_engine2.authorization.workspaceauth import WorkspaceAuth
from lib.execution_engine2.db.MongoUtil import MongoUtil
from lib.execution_engine2.db.models.models import Job, Status
from lib.execution_engine2.execution_engine2Impl import execution_engine2
from lib.execution_engine2.sdk.EE2Status import JobsStatus
from lib.execution_engine2.sdk.SDKMethodRunner import SDKMethodRunner
from lib.execution_engine2.utils.Condor import Condor
from lib.execution_engine2.utils.CondorTuples import SubmissionInfo
from test.utils_shared.test_utils import bootstrap, get_sample_job_params
from tests_for_db.mongo_test_helper import MongoTestHelper

logging.basicConfig(level=logging.INFO)
bootstrap()
from mock import MagicMock


class ee2_server_load_test(unittest.TestCase):
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

        cls.ctx = {"token": cls.token, "user_id": cls.user_id}
        cls.impl = execution_engine2(cls.cfg)
        cls.method_runner = SDKMethodRunner(
            cls.cfg, user_id=cls.user_id, token=cls.token
        )
        cls.mongo_util = MongoUtil(cls.cfg)
        cls.mongo_helper = MongoTestHelper(cls.cfg)

        cls.test_collection = cls.mongo_helper.create_test_db(
            db=cls.cfg["mongo-database"], col=cls.cfg["mongo-jobs-collection"]
        )

        cls.thread_count = 5

    def getRunner(self) -> SDKMethodRunner:
        # Initialize these clients from None
        runner = copy.copy(self.__class__.method_runner)  # type : SDKMethodRunner
        runner._ee2_status = runner.get_jobs_status()  # type: JobsStatus
        runner._ee2_status._send_exec_stats_to_catalog = MagicMock(return_value=True)
        runner._ee2_status.update_finished_job_with_usage = MagicMock(return_value=True)
        runner.get_runjob()
        runner._ee2_runjob._get_module_git_commit = MagicMock(
            return_value="GitCommithash"
        )
        runner.get_job_logs()
        runner.get_condor()
        runner.condor = MagicMock(autospec=True)
        # runner.get_job_resource_info = MagicMock(return_val={})

        return runner

    def test_init_job_stress(self):
        """
        testing initializing 3 different jobs in multiple theads.
        """

        thread_count = self.thread_count  # threads to test

        with self.mongo_util.mongo_engine_connection():
            ori_job_count = Job.objects.count()
            runner = self.getRunner()

            # set job method differently to distinguish
            method_1 = "app_1.a_method"
            method_2 = "app_1.b_method"
            job_params_1 = get_sample_job_params(method=method_1)
            job_params_2 = get_sample_job_params(method=method_2)

            threads = list()
            job_ids = list()
            que = queue.Queue()

            # execute _init_job_rec for 2 different jobs in threads
            for index in range(thread_count):
                x = threading.Thread(
                    target=que.put(
                        runner.get_runjob()._init_job_rec(self.user_id, job_params_1)
                    )
                )
                threads.append(x)
                x.start()
                y = threading.Thread(
                    target=que.put(
                        runner.get_runjob()._init_job_rec(self.user_id, job_params_2)
                    )
                )
                threads.append(y)
                y.start()

            for index, thread in enumerate(threads):
                thread.join()

            while not que.empty():
                job_ids.append(que.get())

            jobs = self.mongo_util.get_jobs(job_ids=job_ids)  # testing get jobs

            methods = [job.job_input.method for job in jobs]  # examing methods returned
            self.assertEqual(len(methods), thread_count * 2)
            self.assertEqual(methods.count(method_1), thread_count)
            self.assertEqual(methods.count(method_2), thread_count)

            self.assertEqual(
                len(set(job_ids)), thread_count * 2
            )  # testing identicalness of job_ids returned
            self.assertEqual(len(job_ids), len(set(job_ids)))

            self.assertEqual(
                ori_job_count, Job.objects.count() - thread_count * 2
            )  # testing job numbers created

            jobs.delete()
            self.assertEqual(ori_job_count, Job.objects.count())

    def test_update_job_status_stress(self):
        """
        testing update jobs into different status in multiple threads
        """
        with self.mongo_util.mongo_engine_connection():
            ori_job_count = Job.objects.count()
            runner = self.getRunner()

            job_params = get_sample_job_params()

            thread_count = self.thread_count  # threads to test

            job_ids_queued = list()  # jobs to be set into 'queued' status
            job_ids_running = list()  # jobs to be set into 'running' status
            job_ids_completed = list()  # jobs to be set into 'completed' status

            # initializing jobs to be tested
            for index in range(thread_count):
                job_ids_queued.append(
                    runner.get_runjob()._init_job_rec(self.user_id, job_params)
                )
                job_ids_running.append(
                    runner.get_runjob()._init_job_rec(self.user_id, job_params)
                )
                job_ids_completed.append(
                    runner.get_runjob()._init_job_rec(self.user_id, job_params)
                )

            # examing newly created job status
            queued_jobs = self.mongo_util.get_jobs(job_ids=job_ids_queued)
            for job in queued_jobs:
                job_rec = job.to_mongo().to_dict()
                self.assertIsNone(job_rec.get("queued"))
                self.assertEqual(job_rec.get("status"), "created")

            running_jobs = self.mongo_util.get_jobs(job_ids=job_ids_running)
            for job in running_jobs:
                job_rec = job.to_mongo().to_dict()
                self.assertIsNone(job_rec.get("running"))
                self.assertEqual(job_rec.get("status"), "created")

            finish_jobs = self.mongo_util.get_jobs(job_ids=job_ids_completed)
            for job in finish_jobs:
                job_rec = job.to_mongo().to_dict()
                self.assertIsNone(job_rec.get("finished"))
                self.assertEqual(job_rec.get("status"), "created")

            threads = list()

            def update_states(index, job_ids_queued, job_ids_running, job_ids_finish):
                """
                update jobs status in one thread
                """
                runner.get_runjob().update_job_to_queued(
                    job_ids_queued[index], "scheduler_id"
                )
                runner.get_jobs_status().start_job(job_ids_running[index])
                runner.get_jobs_status().start_job(job_ids_finish[index])
                job_output = {
                    "version": "11",
                    "result": {"result": 1},
                    "id": "5d54bdcb9b402d15271b3208",
                }
                runner.finish_job(job_id=job_ids_finish[index], job_output=job_output)

            for index in range(thread_count):
                x = threading.Thread(
                    target=update_states(
                        index, job_ids_queued, job_ids_running, job_ids_completed
                    )
                )
                threads.append(x)
                x.start()

            for index, thread in enumerate(threads):
                thread.join()

            # examing updateed job status
            queued_jobs = self.mongo_util.get_jobs(job_ids=job_ids_queued)
            for job in queued_jobs:
                job_rec = job.to_mongo().to_dict()
                self.assertIsNotNone(job_rec.get("queued"))
                self.assertEqual(job_rec.get("status"), "queued")

            running_jobs = self.mongo_util.get_jobs(job_ids=job_ids_running)
            for job in running_jobs:
                job_rec = job.to_mongo().to_dict()
                self.assertIsNotNone(job_rec.get("running"))
                self.assertEqual(job_rec.get("status"), "running")

            finish_jobs = self.mongo_util.get_jobs(job_ids=job_ids_completed)
            for job in finish_jobs:
                job_rec = job.to_mongo().to_dict()
                self.assertIsNotNone(job_rec.get("finished"))
                self.assertEqual(job_rec.get("status"), "completed")

            jobs = self.mongo_util.get_jobs(
                job_ids=(job_ids_queued + job_ids_running + job_ids_completed)
            )
            jobs.delete()
            self.assertEqual(ori_job_count, Job.objects.count())

    # @patch.object(Catalog, "get_module_version", return_value="module.version")
    # @patch("lib.execution_engine2.utils.Condor.Condor", autospec=True)

    si = SubmissionInfo(clusterid="test", submit="job", error=None)

    @patch.object(Condor, "run_job", return_value=si)
    @patch.object(WorkspaceAuth, "can_write", return_value=True)
    @patch(
        "lib.installed_clients.CatalogClient.Catalog.get_module_version", autospec=True
    )
    @patch("lib.installed_clients.CatalogClient.Catalog.log_exec_stats", autospec=True)
    def test_run_job_stress(self, ccles, cc, workspace, condor):
        """
        testing running 3 different jobs in multiple theads.
        """
        cc.return_value = {"git_commit_hash": "moduleversiongoeshere"}

        thread_count = self.thread_count  # threads to test

        with self.mongo_util.mongo_engine_connection():
            ori_job_count = Job.objects.count()

            # set job method differently to distinguish
            method_1 = "app1.a_method"
            method_2 = "app2.b_method"
            method_3 = "app3.c_method"

            job_params_1 = get_sample_job_params(method=method_1)
            job_params_2 = get_sample_job_params(method=method_2)
            job_params_3 = get_sample_job_params(method=method_3)

            threads = list()
            job_ids = list()
            que = queue.Queue()

            # execute run_job for 3 different jobs in threads
            for index in range(thread_count):
                x = threading.Thread(
                    target=que.put(self.impl.run_job(ctx=self.ctx, params=job_params_1))
                )
                threads.append(x)
                x.start()

                y = threading.Thread(
                    target=que.put(self.impl.run_job(ctx=self.ctx, params=job_params_2))
                )
                threads.append(y)
                y.start()

                z = threading.Thread(
                    target=que.put(self.impl.run_job(ctx=self.ctx, params=job_params_3))
                )
                threads.append(z)
                z.start()

            for index, thread in enumerate(threads):
                thread.join()

            while not que.empty():
                job_ids.append(que.get()[0])

            jobs = self.mongo_util.get_jobs(job_ids=job_ids)  # testing get jobs

            methods = [job.job_input.method for job in jobs]  # examing methods returned
            self.assertEqual(len(methods), thread_count * 3)
            self.assertEqual(methods.count(method_1), thread_count)
            self.assertEqual(methods.count(method_2), thread_count)
            self.assertEqual(methods.count(method_3), thread_count)

            status = [
                job.status for job in jobs
            ]  # all jobs should eventually be put to 'queued' status
            self.assertCountEqual(status, [Status.queued.value] * thread_count * 3)

            self.assertEqual(
                len(set(job_ids)), thread_count * 3
            )  # testing identicalness of job_ids returned
            self.assertEqual(len(job_ids), len(set(job_ids)))

            self.assertEqual(
                ori_job_count, Job.objects.count() - thread_count * 3
            )  # testing job numbers created

            jobs.delete()
            self.assertEqual(ori_job_count, Job.objects.count())

    def test_update_job_status(self):
        """
        testing update jobs into different status in multiple threads
        """
        with self.mongo_util.mongo_engine_connection():
            ori_job_count = Job.objects.count()
            runner = self.getRunner()

            job_params = get_sample_job_params()

            thread_count = self.thread_count  # threads to test

            job_ids_queued = list()  # jobs to be set into 'queued' status
            job_ids_running = list()  # jobs to be set into 'running' status
            job_ids_completed = list()  # jobs to be set into 'completed' status

            # initializing jobs to be tested
            for index in range(thread_count):
                job_ids_queued.append(
                    runner.get_runjob()._init_job_rec(self.user_id, job_params)
                )
                job_ids_running.append(
                    runner.get_runjob()._init_job_rec(self.user_id, job_params)
                )
                job_ids_completed.append(
                    runner.get_runjob()._init_job_rec(self.user_id, job_params)
                )

            # examing newly created job status
            init_jobs = self.mongo_util.get_jobs(
                job_ids=job_ids_queued + job_ids_running + job_ids_completed
            )
            for job in init_jobs:
                self.assertEqual(job.to_mongo().to_dict().get("status"), "created")

            threads = list()

            def update_states(
                index, job_ids_queued, job_ids_running, job_ids_completed
            ):
                """
                update jobs status in one thread
                """
                self.impl.update_job_status(
                    ctx=self.ctx,
                    params={"job_id": job_ids_queued[index], "status": "queued"},
                )
                self.impl.update_job_status(
                    ctx=self.ctx,
                    params={"job_id": job_ids_running[index], "status": "running"},
                )
                self.impl.update_job_status(
                    ctx=self.ctx,
                    params={"job_id": job_ids_completed[index], "status": "completed"},
                )

            for index in range(thread_count):
                x = threading.Thread(
                    target=update_states(
                        index, job_ids_queued, job_ids_running, job_ids_completed
                    )
                )
                threads.append(x)
                x.start()

            for index, thread in enumerate(threads):
                thread.join()

            # examing updateed job status
            queued_jobs = self.mongo_util.get_jobs(job_ids=job_ids_queued)
            for job in queued_jobs:
                self.assertEqual(job.to_mongo().to_dict().get("status"), "queued")

            running_jobs = self.mongo_util.get_jobs(job_ids=job_ids_running)
            for job in running_jobs:
                self.assertEqual(job.to_mongo().to_dict().get("status"), "running")

            finish_jobs = self.mongo_util.get_jobs(job_ids=job_ids_completed)
            for job in finish_jobs:
                self.assertEqual(job.to_mongo().to_dict().get("status"), "completed")

            jobs = self.mongo_util.get_jobs(
                job_ids=(job_ids_queued + job_ids_running + job_ids_completed)
            )
            jobs.delete()
            self.assertEqual(ori_job_count, Job.objects.count())

    def test_check_jobs_stress(self):
        """
        testing check jobs in multiple theads.
        """

        thread_count = self.thread_count  # threads to test

        with self.mongo_util.mongo_engine_connection():
            ori_job_count = Job.objects.count()
            runner = self.getRunner()

            # set job method differently to distinguish
            method_1 = "a_method"
            method_2 = "b_method"
            job_params_1 = get_sample_job_params(method=method_1)
            job_params_2 = get_sample_job_params(method=method_2)

            # create jobs
            job_id_1 = runner.get_runjob()._init_job_rec(self.user_id, job_params_1)
            job_id_2 = runner.get_runjob()._init_job_rec(self.user_id, job_params_2)

            threads = list()
            job_status = list()
            que = queue.Queue()

            # execute check_jobs in multiple threads
            for index in range(thread_count):
                x = threading.Thread(
                    target=que.put(
                        self.impl.check_jobs(
                            ctx=self.ctx, params={"job_ids": [job_id_1, job_id_2]}
                        )
                    )
                )
                threads.append(x)
                x.start()

            for index, thread in enumerate(threads):
                thread.join()

            while not que.empty():
                job_status.append(que.get())

            # exam returned job status
            for job_status in job_status:
                job_status = job_status[0]["job_states"]
                job_ids = [js["job_id"] for js in job_status]
                job_methods = [js["job_input"]["method"] for js in job_status]
                self.assertCountEqual(job_ids, [job_id_1, job_id_2])
                self.assertCountEqual(job_methods, [method_1, method_2])

            jobs = self.mongo_util.get_jobs(job_ids=[job_id_1, job_id_2])
            jobs.delete()
            self.assertEqual(ori_job_count, Job.objects.count())

    def test_check_job_canceled_stress(self):
        """
        testing check_job_canceled in multiple theads.
        """

        thread_count = self.thread_count  # threads to test

        with self.mongo_util.mongo_engine_connection():
            ori_job_count = Job.objects.count()
            runner = self.getRunner()

            job_params = get_sample_job_params()

            # create jobs
            job_id_running = runner.get_runjob()._init_job_rec(self.user_id, job_params)
            job_id_terminated = runner.get_runjob()._init_job_rec(
                self.user_id, job_params
            )
            job_id_completed = runner.get_runjob()._init_job_rec(
                self.user_id, job_params
            )

            self.impl.update_job_status(
                ctx=self.ctx, params={"job_id": job_id_running, "status": "running"}
            )
            self.impl.update_job_status(
                ctx=self.ctx,
                params={"job_id": job_id_terminated, "status": "terminated"},
            )
            self.impl.update_job_status(
                ctx=self.ctx, params={"job_id": job_id_completed, "status": "completed"}
            )

            threads = list()
            job_canceled_status = list()
            que = queue.Queue()

            # execute check_job_canceled in multiple threads
            for index in range(thread_count):
                x = threading.Thread(
                    target=que.put(
                        self.impl.check_job_canceled(
                            ctx=self.ctx, params={"job_id": job_id_running}
                        )
                    )
                )
                threads.append(x)
                x.start()

                y = threading.Thread(
                    target=que.put(
                        self.impl.check_job_canceled(
                            ctx=self.ctx, params={"job_id": job_id_terminated}
                        )
                    )
                )
                threads.append(y)
                y.start()

                z = threading.Thread(
                    target=que.put(
                        self.impl.check_job_canceled(
                            ctx=self.ctx, params={"job_id": job_id_completed}
                        )
                    )
                )
                threads.append(z)
                z.start()

            for index, thread in enumerate(threads):
                thread.join()

            while not que.empty():
                job_canceled_status.append(que.get())

            # exam correct job ids returned
            job_ids_returned = [
                jcs_return[0]["job_id"] for jcs_return in job_canceled_status
            ]
            self.assertEqual(
                len(job_ids_returned), thread_count * 3
            )  # exam total job number returned
            self.assertEqual(job_ids_returned.count(job_id_running), thread_count)
            self.assertEqual(job_ids_returned.count(job_id_terminated), thread_count)
            self.assertEqual(job_ids_returned.count(job_id_completed), thread_count)

            # exam returned job canceled status
            for job_canceled_status_return in job_canceled_status:
                job_canceled_status_return = job_canceled_status_return[0]
                if job_canceled_status_return["job_id"] == job_id_running:
                    self.assertFalse(job_canceled_status_return["canceled"])
                    self.assertFalse(job_canceled_status_return["finished"])
                if job_canceled_status_return["job_id"] == job_id_terminated:
                    self.assertTrue(job_canceled_status_return["canceled"])
                    self.assertTrue(job_canceled_status_return["finished"])
                if job_canceled_status_return["job_id"] == job_id_completed:
                    self.assertFalse(job_canceled_status_return["canceled"])
                    self.assertTrue(job_canceled_status_return["finished"])

            jobs = self.mongo_util.get_jobs(
                job_ids=[job_id_running, job_id_terminated, job_id_completed]
            )

            for job in jobs:
                job.delete()

            self.assertEqual(ori_job_count, Job.objects.count())

    def test_get_job_logs_stress(self):
        """
        testing get_job_logs in multiple theads.
        """

        thread_count = self.thread_count  # threads to test

        with self.mongo_util.mongo_engine_connection():
            ori_job_count = Job.objects.count()
            runner = self.getRunner()

            # create job
            job_id = runner.get_runjob()._init_job_rec(
                self.user_id, get_sample_job_params()
            )

            # add one line to job
            ts = time.time()
            job_line = [{"line": "hello ee2", "is_error": 1, "ts": ts}]
            self.impl.add_job_logs(
                ctx=self.ctx, params={"job_id": job_id}, lines=job_line
            )

            threads = list()
            job_lines = list()
            que = queue.Queue()

            # execute get_job_logs in multiple threads
            for index in range(thread_count):
                x = threading.Thread(
                    target=que.put(
                        self.impl.get_job_logs(ctx=self.ctx, params={"job_id": job_id})
                    )
                )
                threads.append(x)
                x.start()

            for index, thread in enumerate(threads):
                thread.join()

            while not que.empty():
                job_lines.append(que.get())

            self.assertEqual(
                len(job_lines), thread_count
            )  # exam total number of job lines returned

            # exam each get_job_logs result
            for job_line in job_lines:
                job_line = job_line[0]["lines"][0]
                self.assertEqual(job_line["line"], "hello ee2")
                self.assertEqual(job_line["linepos"], 0)
                self.assertEqual(job_line["is_error"], 1)
                self.assertEqual(job_line["ts"], int(ts * 1000))

            jobs = self.mongo_util.get_jobs(job_ids=[job_id])
            jobs.delete()
            self.assertEqual(ori_job_count, Job.objects.count())

    def test_add_job_logs_stress(self):
        """
        testing add_job_logs in multiple theads.
        """

        thread_count = self.thread_count  # threads to test

        with self.mongo_util.mongo_engine_connection():

            ori_job_count = Job.objects.count()
            print("original job count is", ori_job_count)
            runner = self.getRunner()

            # create job
            job_id = runner.get_runjob()._init_job_rec(
                self.user_id, get_sample_job_params()
            )

            # job line to be added
            ts = time.time()
            job_line = [{"line": "hello ee2", "is_error": 1, "ts": ts}]

            threads = list()
            que = queue.Queue()
            # execute add_job_logs in multiple threads
            print("Number of threads are", thread_count)
            for index in range(thread_count):
                x = threading.Thread(
                    target=que.put(
                        self.impl.add_job_logs(
                            ctx=self.ctx, params={"job_id": job_id}, lines=job_line
                        )
                    )
                )
                threads.append(x)
                x.start()

            for index, thread in enumerate(threads):
                thread.join()

            job_lines = self.impl.get_job_logs(ctx=self.ctx, params={"job_id": job_id})[
                0
            ]

            self.assertEqual(
                job_lines["last_line_number"], thread_count - 1
            )  # exam total number of job lines created by add_job_logs

            # exam each line created by add_job_logs
            lines = job_lines["lines"]
            self.assertEqual(len(lines), thread_count)
            line_pos = list()
            for line in lines:
                self.assertEqual(line["line"], "hello ee2")
                self.assertEqual(line["is_error"], 1)
                self.assertEqual(line["ts"], int(ts * 1000))
                line_pos.append(line["linepos"])
            self.assertCountEqual(line_pos, list(range(0, thread_count)))

            jobs = self.mongo_util.get_jobs(job_ids=[job_id])

            for job in jobs:
                job.delete()

            self.assertEqual(ori_job_count, Job.objects.count())
