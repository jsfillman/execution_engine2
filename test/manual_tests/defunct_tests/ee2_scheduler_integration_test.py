# # -*- coding: utf-8 -*-
# import logging
# import os
# import pwd
# import unittest
#
# import htcondor
#
# logging.basicConfig(level=logging.INFO)
#
# from lib.execution_engine2.utils.Condor import Condor
#
#
# class ExecutionEngine2SchedulerIntegrationTest(unittest.TestCase):
#     @classmethod
#     def setUpClass(cls):
#         cls.deploy = "deploy_for_integration_tests.cfg"
#         cls.condor = Condor(cls.deploy)
#         cls.job_id = "1234"
#         cls.user = "kbase"
#         cls.token = "bogus"
#
#         # cls.check_kbase_user()
#         cls.schedd = htcondor.Schedd()
#         if cls.queue_is_empty():
#             cls.add_a_sleep_job()
#         jobs = cls.queue_status()
#         for job in jobs:
#             logging.info(
#                 f"clusterid {job.get('ClusterId')} running cmd ( {job.get('Cmd')} ) is in state {job.get('JobStatus')}"
#             )
#
#     @classmethod
#     def add_a_sleep_job(cls):
#         logging.info("Adding a sleep job")
#         sub = htcondor.Submit({})
#         sub["executable"] = "/bin/sleep"
#         sub["arguments"] = "5m"
#         sub["AccountingGroup"] = "kbase"
#         with cls.schedd.transaction() as txn:
#             print(sub.queue(txn, 1))
#
#     def example(self):
#         import htcondor
#
#         schedd = htcondor.Schedd()
#         sub = htcondor.Submit({})
#         sub["executable"] = "/bin/sleep"
#         sub["arguments"] = "5m"
#         sub["AccountingGroup"] = "kbase"
#         with schedd.transaction() as txn:
#             print(sub.queue(txn, 1))
#
#     def longer_example(self):
#         import htcondor
#
#         schedd = htcondor.Schedd()
#         subdict = {
#             "JobBatchName": "5d38cbc5d9b2d9ce67fdbbc4",
#             "initial_dir": "/condor_shared",
#             "executable": "/bin/sleep",
#             "arguments": "5d38cbc5d9b2d9ce67fdbbc4 https://ci.kbase.us/services",
#             "environment": "DOCKER_JOB_TIMEOUT=604805 KB_ADMIN_AUTH_TOKEN=test_auth_token KB_AUTH_TOKEN=XXXX CLIENTGROUP=None JOB_ID=5d38cbc5d9b2d9ce67fdbbc4 CONDOR_ID=$(Cluster).$(Process) ",
#             "universe": "vanilla",
#             "+AccountingGroup": "bsadkhin",
#             "Concurrency_Limits": "bsadkhin",
#             "+Owner": '"condor_pool"',
#             "ShouldTransferFiles": "YES",
#             "When_To_Transfer_Output": "ON_EXIT",
#             "request_cpus": "4",
#             "request_memory": "2000M",
#             "request_disk": "30GB",
#             "requirements": 'regexp("njs",CLIENTGROUP)',
#         }
#
#         sub = htcondor.Submit(subdict)
#         with schedd.transaction() as txn:
#             print(sub.queue(txn, 1))
#
#     @classmethod
#     def check_kbase_user(cls):
#         my_uid = os.getuid()
#         kbase_uid = pwd.getpwnam("kbase").pw_uid
#         if my_uid != kbase_uid:
#             logging.error(
#                 f"I'm not the KBASE User. My UID is {my_uid}. The KBASE uid is {kbase_uid}"
#             )
#             logging.info("Attempting to switch to kbase user")
#             try:
#                 os.setuid(kbase_uid)
#             except Exception as e:
#                 logging.error(e)
#         logging.info("Success. I'm the KBASE User")
#
#     @classmethod
#     def queue_is_empty(cls):
#         if len(cls.schedd.query(limit=1)) == 0:
#             logging.info("Queue is empty")
#             return True
#         return False
#
#     @classmethod
#     def queue_status(cls):
#         return cls.schedd.query()
#
#     @classmethod
#     def tearDownClass(cls):
#         if hasattr(cls, "wsName"):
#             cls.wsClient.delete_workspace({"workspace": cls.wsName})
#             print("Test workspace was deleted")
#
#     def _create_sample_params(self):
#         params = dict()
#         params["job_id"] = self.job_id
#
#     def test_submit_job(self):
#         # Test with empty clientgroup
#         c = self.condor
#         params = {
#             "job_id": "test_job_id",
#             "user_id": "test",
#             "token": "test_token",
#             "cg_resources_requirements": "",
#         }
#
#         submit_file = c.create_submit(params)
#         # Fix for container
#         # submit_file['+OWNER'] = ''
#         logging.info(submit_file)
#         submission_info = c.run_job(params, submit_file=submit_file)
#         print(submission_info)
#         self.assertIsNotNone(submission_info.clusterid)
#
#     def test_sleep_job(self):
#         pass
#
#     def test_client_groups(self):
#         client_group = "njs,bigmem,bigmemlong"
#
#         client_group_json = {
#             "client_group": "njs",
#             "cg_regex": "True",
#             "request_cpus": 1,
#             "request_disk": 100,
#             "request_memory": 10000,
#             "machine": "chicagoawe206",
#             "dynamic_memory": "false",
#         }
