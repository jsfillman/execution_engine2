# -*- coding: utf-8 -*-
import logging
import os
import unittest
from configparser import ConfigParser

from bson.objectid import ObjectId

from execution_engine2.db.MongoUtil import MongoUtil
from execution_engine2.db.models.models import Job, JobLog
from test.utils_shared.test_utils import bootstrap, get_example_job
from tests_for_db.mongo_test_helper import MongoTestHelper

logging.basicConfig(level=logging.INFO)

bootstrap()


class MongoUtilTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        config_file = os.environ.get(
            "KB_DEPLOYMENT_CONFIG", os.path.join("test", "deploy.cfg")
        )

        logging.info("Reading from " + config_file)
        config_parser = ConfigParser()
        config_parser.read(config_file)

        cls.config = {}
        for nameval in config_parser.items("execution_engine2"):
            cls.config[nameval[0]] = nameval[1]

        mongo_in_docker = cls.config.get("mongo-in-docker-compose", None)
        if mongo_in_docker is not None:
            cls.config["mongo-host"] = cls.config["mongo-in-docker-compose"]

        logging.info("Setting up mongo test helper")
        cls.mongo_helper = MongoTestHelper(cls.config)
        logging.info(
            f" mongo create test db={cls.config['mongo-database']}, col={cls.config['mongo-jobs-collection']}"
        )

        cls.test_collection = cls.mongo_helper.create_test_db(
            db=cls.config["mongo-database"], col=cls.config["mongo-jobs-collection"]
        )
        logging.info("Setting up mongo util")
        cls.mongo_util = MongoUtil(cls.config)

    @classmethod
    def tearDownClass(cls):
        print("Finished testing MongoUtil")

    def getMongoUtil(self) -> MongoUtil:
        return self.__class__.mongo_util

    def test_init_ok(self):
        class_attri = [
            "mongo_host",
            "mongo_port",
            "mongo_database",
            "mongo_user",
            "mongo_pass",
            "mongo_authmechanism",
            "mongo_collection",
        ]
        mongo_util = self.getMongoUtil()
        self.assertTrue(set(class_attri) <= set(mongo_util.__dict__.keys()))

    def test_get_by_cluster(self):
        """ Get a job by its condor scheduler_id"""
        mongo_util = self.getMongoUtil()
        with mongo_util.mongo_engine_connection():
            job = get_example_job()
            job_id = job.save().id
            batch = mongo_util.get_job_batch_name(job.scheduler_id)
            self.assertEqual(str(job_id), batch)

    def test_get_job_ok(self):

        mongo_util = self.getMongoUtil()

        with mongo_util.mongo_engine_connection():
            ori_job_count = Job.objects.count()
            job = get_example_job()
            job_id = job.save().id
            self.assertEqual(ori_job_count, Job.objects.count() - 1)

            # get job with no exclude_fields
            job = mongo_util.get_job(job_id=job_id).to_mongo().to_dict()

            expected_keys = [
                "_id",
                "user",
                "authstrat",
                "wsid",
                "status",
                "updated",
                "job_input",
                "scheduler_id",
            ]
            self.assertCountEqual(job.keys(), expected_keys)

            # get job with exclude_fields
            job = (
                mongo_util.get_job(job_id=job_id, exclude_fields=["job_input"])
                .to_mongo()
                .to_dict()
            )

            expected_keys = [
                "_id",
                "user",
                "authstrat",
                "wsid",
                "status",
                "updated",
                "scheduler_id",
            ]
            self.assertCountEqual(job.keys(), expected_keys)

            # get job with multiple exclude_fields
            job = (
                mongo_util.get_job(job_id=job_id, exclude_fields=["user", "wsid"])
                .to_mongo()
                .to_dict()
            )

            expected_keys = [
                "_id",
                "authstrat",
                "status",
                "updated",
                "job_input",
                "scheduler_id",
            ]
            self.assertCountEqual(job.keys(), expected_keys)

            mongo_util.get_job(job_id=job_id).delete()
            self.assertEqual(ori_job_count, Job.objects.count())

    def test_get_jobs_ok(self):

        mongo_util = self.getMongoUtil()

        with mongo_util.mongo_engine_connection():
            ori_job_count = Job.objects.count()
            job = get_example_job()
            job_id_1 = job.save().id
            job = get_example_job()
            job_id_2 = job.save().id
            self.assertEqual(ori_job_count, Job.objects.count() - 2)

            # get jobs with no exclude_fields
            jobs = mongo_util.get_jobs(job_ids=[job_id_1, job_id_2])

            expected_keys = [
                "_id",
                "user",
                "authstrat",
                "wsid",
                "status",
                "updated",
                "job_input",
                "scheduler_id",
            ]

            for job in jobs:
                self.assertCountEqual(job.to_mongo().to_dict().keys(), expected_keys)

            # get jobs with multiple exclude_fields
            jobs = mongo_util.get_jobs(
                job_ids=[job_id_1, job_id_2], exclude_fields=["user", "wsid"]
            )

            expected_keys = [
                "_id",
                "authstrat",
                "status",
                "updated",
                "job_input",
                "scheduler_id",
            ]
            for job in jobs:
                self.assertCountEqual(job.to_mongo().to_dict().keys(), expected_keys)

            mongo_util.get_job(job_id=job_id_1).delete()
            mongo_util.get_job(job_id=job_id_2).delete()
            self.assertEqual(ori_job_count, Job.objects.count())

    def test_connection_ok(self):

        mongo_util = self.getMongoUtil()

        with mongo_util.mongo_engine_connection():
            ori_job_count = Job.objects.count()
            j = get_example_job()
            j.save()
            self.assertEqual(ori_job_count, Job.objects.count() - 1)

            job = mongo_util.get_job(job_id=j.id).to_mongo().to_dict()

            expected_keys = [
                "_id",
                "user",
                "authstrat",
                "wsid",
                "status",
                "updated",
                "job_input",
                "scheduler_id",
            ]

            self.assertCountEqual(job.keys(), expected_keys)
            self.assertEqual(job["user"], j.user)
            self.assertEqual(job["authstrat"], "kbaseworkspace")
            self.assertEqual(job["wsid"], j.wsid)

            mongo_util.get_job(job_id=j.id).delete()
            self.assertEqual(ori_job_count, Job.objects.count())

    def test_insert_one_ok(self):
        mongo_util = self.getMongoUtil()

        with mongo_util.pymongo_client(
            self.config["mongo-jobs-collection"]
        ) as pymongo_client:
            col = pymongo_client[self.config["mongo-database"]][
                self.config["mongo-jobs-collection"]
            ]

            ori_job_count = col.count_documents({})
            doc = {"test_key": "foo"}
            job_id = mongo_util.insert_one(doc)
            self.assertEqual(ori_job_count, col.count_documents({}) - 1)

            result = list(col.find({"_id": ObjectId(job_id)}))[0]
            self.assertEqual(result["test_key"], "foo")

            col.delete_one({"_id": ObjectId(job_id)})
            self.assertEqual(col.count_documents({}), ori_job_count)

    def test_find_in_ok(self):
        mongo_util = self.getMongoUtil()

        with mongo_util.pymongo_client(
            self.config["mongo-jobs-collection"]
        ) as pymongo_client:
            col = pymongo_client[self.config["mongo-database"]][
                self.config["mongo-jobs-collection"]
            ]

            ori_job_count = col.count_documents({})
            doc = {"test_key_1": "foo", "test_key_2": "bar"}
            job_id = mongo_util.insert_one(doc)
            self.assertEqual(ori_job_count, col.count_documents({}) - 1)

            # test query empty field
            elements = ["foobar"]
            docs = mongo_util.find_in(elements, "test_key_1")
            self.assertEqual(docs.count(), 0)

            # test query "foo"
            elements = ["foo"]
            docs = mongo_util.find_in(elements, "test_key_1")
            self.assertEqual(docs.count(), 1)
            doc = docs.next()
            self.assertTrue("_id" in doc.keys())
            self.assertTrue(doc.get("_id"), job_id)
            self.assertEqual(doc.get("test_key_1"), "foo")

            col.delete_one({"_id": ObjectId(job_id)})
            self.assertEqual(col.count_documents({}), ori_job_count)

    def test_update_one_ok(self):
        mongo_util = self.getMongoUtil()

        with mongo_util.pymongo_client(
            self.config["mongo-jobs-collection"]
        ) as pymongo_client:
            col = pymongo_client[self.config["mongo-database"]][
                self.config["mongo-jobs-collection"]
            ]

            ori_job_count = col.count_documents({})
            doc = {"test_key_1": "foo"}
            job_id = mongo_util.insert_one(doc)
            self.assertEqual(ori_job_count, col.count_documents({}) - 1)

            elements = ["foo"]
            docs = mongo_util.find_in(elements, "test_key_1")
            self.assertEqual(docs.count(), 1)
            doc = docs.next()
            self.assertTrue("_id" in doc.keys())
            self.assertTrue(doc.get("_id"), job_id)
            self.assertEqual(doc.get("test_key_1"), "foo")

            mongo_util.update_one({"test_key_1": "bar"}, job_id)

            elements = ["foo"]
            docs = mongo_util.find_in(elements, "test_key_1")
            self.assertEqual(docs.count(), 0)

            elements = ["bar"]
            docs = mongo_util.find_in(elements, "test_key_1")
            self.assertEqual(docs.count(), 1)

            col.delete_one({"_id": ObjectId(job_id)})
            self.assertEqual(col.count_documents({}), ori_job_count)

    def test_delete_one_ok(self):
        mongo_util = MongoUtil(self.config)
        with mongo_util.pymongo_client(self.config["mongo-jobs-collection"]) as pc:
            col = pc.get_database(self.config["mongo-database"]).get_collection(
                self.config["mongo-jobs-collection"]
            )

            doc_count = col.count_documents({})
            logging.info("Found {} documents".format(doc_count))

            doc = {"test_key_1": "foo", "test_key_2": "bar"}
            job_id = mongo_util.insert_one(doc)

            self.assertEqual(col.count_documents({}), doc_count + 1)
            logging.info("Assert 0 documents")
            mongo_util.delete_one(job_id)
            self.assertEqual(col.count_documents({}), doc_count)

    def test_get_job_log_pymongo_ok(self):

        mongo_util = self.getMongoUtil()

        primary_key = ObjectId()

        jl = JobLog()
        jl.primary_key = primary_key
        jl.original_line_count = 0
        jl.stored_line_count = 0
        jl.lines = []

        with mongo_util.pymongo_client(
            self.config["mongo-jobs-collection"]
        ) as pymongo_client:
            jl_col = pymongo_client[self.config["mongo-database"]][
                self.config["mongo-logs-collection"]
            ]

            ori_jl_count = jl_col.count_documents({})

            jl.save()  # save job log

            self.assertEqual(JobLog.objects.count(), ori_jl_count + 1)
            job_log = mongo_util.get_job_log_pymongo(str(primary_key))

            self.assertEqual(job_log.get("original_line_count"), 0)
            self.assertEqual(job_log.get("stored_line_count"), 0)
            self.assertIsNone(job_log.get("lines"))
