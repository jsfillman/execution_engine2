# -*- coding: utf-8 -*-

from lib.execution_engine2.db.models.models import Job, JobInput, Meta
from lib.execution_engine2.sdk.SDKMethodRunner import SDKMethodRunner


class ee2_sdkmr_test_helper:
    def __init__(self, mr: SDKMethodRunner, wsid: str = 9999):
        self.user_id = mr.user_id
        self.ws_id = wsid
        self.token = mr.token
        self.method_runner = mr

    def create_job_rec(self):
        """ Save a job, forgoing runjob.run"""

        job = Job()

        inputs = JobInput()

        job.user = self.user_id
        job.authstrat = "kbaseworkspace"
        job.wsid = self.ws_id
        job.status = "created"

        job_params = {
            "wsid": self.ws_id,
            "method": "MEGAHIT.run_megahit",
            "app_id": "MEGAHIT/run_megahit",
            "service_ver": "2.2.1",
            "params": [
                {
                    "k_list": [],
                    "k_max": None,
                    "output_contigset_name": "MEGAHIT.contigs",
                }
            ],
            "source_ws_objects": ["a/b/c", "e/d"],
            "parent_job_id": "9998",
        }

        inputs.wsid = job.wsid
        inputs.method = job_params.get("method")
        inputs.params = job_params.get("params")
        inputs.service_ver = job_params.get("service_ver")
        inputs.app_id = job_params.get("app_id")
        inputs.source_ws_objects = job_params.get("source_ws_objects")
        inputs.parent_job_id = job_params.get("parent_job_id")

        inputs.narrative_cell_info = Meta()

        job.job_input = inputs
        job.job_output = None
        job.scheduler_id = "123"

        with self.method_runner.get_mongo_util().mongo_engine_connection():
            job.save()

        return str(job.id)
