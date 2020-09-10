# -*- coding: utf-8 -*-
import logging
import os
import unittest

from bson import ObjectId

from lib.execution_engine2.db.MongoUtil import MongoUtil
from lib.execution_engine2.db.models.models import LogLines, JobLog
from test.utils_shared.test_utils import (
    read_config_into_dict,
    bootstrap,
    get_example_job,
)

logging.basicConfig(level=logging.INFO)
bootstrap()


class EE2ModelTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        deploy = os.environ.get("KB_DEPLOYMENT_CONFIG", "test/deploy.cfg")
        config = read_config_into_dict(deploy)
        # Should this just be added into read_config_into_dict function?
        mongo_in_docker = config.get("mongo-in-docker-compose", None)
        if mongo_in_docker is not None:
            config["mongo-host"] = config["mongo-in-docker-compose"]

        # For using mongo running in docker
        config["start-local-mongo"] = 0

        cls.config = config
        cls.ctx = {"job_id": "test", "user_id": "test", "token": "test"}
        cls.mongo_util = MongoUtil(cls.config)

    def test_insert_job(self):
        logging.info("Testing insert job")
        with self.mongo_util.mongo_engine_connection(), self.mongo_util.pymongo_client(
            self.config["mongo-jobs-collection"]
        ) as pc:
            job = get_example_job()
            job.save()

            logging.info(f"Inserted {job.id}")

            logging.info(f"Searching for {job.id}")
            db = self.config["mongo-database"]
            coll = self.config["mongo-jobs-collection"]
            saved_job = pc[db][coll].find_one({"_id": ObjectId(job.id)})
            logging.info("Found")
            logging.info(saved_job)

            print(job.wsid)
            print(saved_job["wsid"])
            self.assertEqual(job.wsid, saved_job["wsid"])
            self.assertEqual(
                job.job_input.narrative_cell_info.cell_id,
                saved_job["job_input"]["narrative_cell_info"]["cell_id"],
            )

    def test_insert_log(self):
        """
        This test inserts a log via the models
        :return:
        """
        with self.mongo_util.mongo_engine_connection():
            logging.info(self.mongo_util.config)

            job = get_example_job()
            job.save()

            j = JobLog()
            print(job.id)
            j.primary_key = job.id

            j.original_line_count = 1
            j.stored_line_count = 1
            j.lines = []
            j.lines.append(
                LogLines(
                    error=True,
                    linepos=0,
                    line="The quick brown fox jumps over a lazy dog.",
                )
            )

            j.save()

        # TODO Test adding lines to existing log, but we need the functions in ee2 first

    def test_insert_more_logs(self):
        """
        This test inserts a log via the api callss
        :return:
        """
        pass

    def test_retrieve_job(self):
        pass

    def test_retrieve_logs(self):
        pass
