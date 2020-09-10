# -*- coding: utf-8 -*-

import logging
import unittest

logging.basicConfig(level=logging.INFO)

from lib.installed_clients.execution_engine2Client import execution_engine2
from lib.installed_clients.WorkspaceClient import Workspace
import os
import sys
import time

from dotenv import load_dotenv
from pprint import pprint

load_dotenv("env/test.env", verbose=True)


class ExecutionEngine2SchedulerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        """
        This test is used for sending commands to a live environment, such as CI.
        TravisCI doesn't need to run this test.
        :return:
        """
        next_token = ""
        os.environ["KB_AUTH_TOKEN"] = next_token
        os.environ["EE2_ENDPOINT"] = "https://next.kbase.us/services/ee2"
        os.environ["WS_ENDPOINT"] = "https://next.kbase.us/services/ws"

        if "KB_AUTH_TOKEN" not in os.environ or "EE2_ENDPOINT" not in os.environ:
            logging.error(
                "Make sure you copy the env/test.env.example file to test/env/test.env and populate it"
            )
            sys.exit(1)

        cls.ee2 = execution_engine2(
            url=os.environ["EE2_ENDPOINT"], token=os.environ["KB_AUTH_TOKEN"]
        )
        cls.ws = Workspace(
            url=os.environ["WS_ENDPOINT"], token=os.environ["KB_AUTH_TOKEN"]
        )

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, "wsName"):
            cls.wsClient.delete_workspace({"workspace": cls.wsName})
            print("Test workspace was deleted")

    def test_status(self):
        """
        Test to see if the ee2 service is up
        :return:
        """
        logging.info("Checking server time")
        self.assertIn("server_time", self.ee2.status())

    def test_config(self):
        conf = self.ee2.list_config({})
        for item in conf:
            print(item, conf[item])

    def test_check_jobs_date_range_for_all(self):
        filters = {"status__in": ["queued", "running"]}
        records = self.ee2.check_jobs_date_range_for_all(
            params={"start_time": 0, "end_time": time.time(), "filter": filters}
        )

        pprint(records["jobs"])

    def test_held_job(self):
        returnVal = self.ee2.handle_held_job(cluster_id="14574")
        pprint(returnVal)

    # def test_jobs_range(self):
    #     check_jobs_date_range_params = {}
    #     check_jobs_date_range_params = {""}
    #     self.ee2.check_jobs_date_range_for_user()
    #     self.ee2.check_jobs_date_range_for_all()

    def test_admin_perm(self):
        print("is_admin", self.ee2.is_admin())
        print("perrmission = ", self.ee2.get_admin_permission().get("permission"))

    def test_run_job_concierge(self):
        # ee2 = execution_engine2(
        #     url=os.environ["EE2_ENDPOINT"], token=os.environ["KB_AUTH_TOKEN"]
        # )

        params = {"base_number": "105"}
        runjob_params = {
            "method": "simpleapp.simple_add",
            "params": [params],
            "service_ver": "dev",
            "wsid": "48739",
            "app_id": "simpleapp",
        }

        cp = dict()
        cp["request_cpus"] = 1
        cp["request_disk"] = 1000
        cp["request_memory"] = 1000

        job_id = self.ee2.run_job_concierge(runjob_params, concierge_params=cp)
        print(f"Submitted job {job_id}")
        job_log_params = {"job_id": job_id}

        while True:
            time.sleep(5)
            try:
                print(self.ee2.get_job_status({"job_id": job_id}))
                print(self.ee2.get_job_logs(job_log_params))
                status = self.ee2.get_job_status({"job_id": job_id})
                if status == {"status": "finished"}:
                    break
            except Exception as e:
                print("Not yet", e)

    def test_start_started_job(self):
        self.ee2.start_job(params={"job_id": "5e882237456076432a5c2baa"})

    def test_job_status(self):
        status = self.ee2.check_job(params={"job_id": "5e882237456076432a5c2baa"}).get(
            "status"
        )
        print("status is", status)

    def test_run_job(self):
        """
        Test a simple job based on runjob params from the spec file

        typedef structure {
            string method;
            list<UnspecifiedObject> params;
            string service_ver;
            RpcContext rpc_context;
            string remote_url;
            list<wsref> source_ws_objects;
            string app_id;
            mapping<string, string> meta;
            int wsid;
            string parent_job_id;
        } RunJobParams;

        :return:
        """
        params = {"base_number": "105"}
        # ci_wsid = "42896"
        next_wsid = "1139"
        runjob_params = {
            "method": "simpleapp.simple_add",
            "params": [params],
            "service_ver": "dev",
            "wsid": next_wsid,
            "app_id": "simpleapp",
        }

        job_id = self.ee2.run_job(runjob_params)
        print(f"Submitted job {job_id}")
        job_log_params = {"job_id": job_id}

        while True:
            time.sleep(5)
            try:
                print(self.ee2.get_job_status(job_log_params))
                print(self.ee2.get_job_logs(job_log_params))
                status = self.ee2.get_job_status(job_log_params)
                if status == {"status": "finished"}:
                    break
            except Exception as e:
                print("Not yet", e)

    def test_admin_log(self):

        pprint(
            self.ee2.get_job_logs(
                {"job_id": "5d59bd96aa5a4d298c5dc8bc", "as_admin": True}
            )
        )


#         import datetime

#         now = datetime.datetime.utcnow()
#         line1 = {
#             "line": "Tell me the first line, the whole line, and nothing but the line",
#             "error": False,
#             "ts": now.isoformat(),
#         }
#         line2 = {"line": "This really crosses the line", "error": True}
#         lines = [line1, line2]

# self.ee2.add_job_logs(job_id, lines=lines)

# def test_add_job_log(self):
#     import datetime
#     job_id="5d51aa0517554f4cfd7b8a2b"
#     now = datetime.datetime.now()
#     line1 = {'line' : "1", 'error' : False, 'ts' : now}
#     line2 = {'line' : "1", 'error' : False}
#     lines = [line1,line2]
#
#     self.ee2.add_job_logs(job_id,lines=lines)

# def test_get_logs(self):
# job_id="5d51aa0517554f4cfd7b8a2b"
# job_log_params = {"job_id": job_id}
# print("About to get logs for", job_log_params)
# print(self.ee2.get_job_logs(job_log_params))

# def test_get_permissions(self):
#     username = 'bsadkhin'
#     perms = self.ws.get_permissions_mass({'workspaces': [{'id': '42896'}]})['perms']
#     permission = "n"
#     for p in perms:
#         if username in p:
#             permission = p[username]
#     print("Permission is")
#     print(permission)
#
# from enum import Enum
#
# class WorkspacePermissions(Enum):
#     ADMINISTRATOR = "a"
#     READ_WRITE = "w"
#     READ = "r"
#     NONE = "n"

# def test_get_workspace_permissions(self):
#     job_id='5d48821bfc8e83248c0d2cff'
#     wsid=42896
#     username="bsadkhin"
#     perms = self.ws.get_permissions_mass({'workspaces': [{'id': wsid}]})['perms']
#     permission = "n"
#     for p in perms:
#         if username in p:
#             permission = p[username]
#     print(self.WorkspacePermissions(permission))

# def get_workspace_permissions(self, wsid, ctx):
#         # Look up permissions for this workspace
#         logging.info(f"Checking for permissions for {wsid} of type {type(wsid)}")
#         gpmp = {'workspaces' : [int(wsid)]}
#         permission = self.get_workspace(ctx).get_permissions_mass(gpmp)[0]
#         return self.WorkspacePermissions(permission)
