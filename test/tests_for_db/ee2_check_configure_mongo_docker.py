# -*- coding: utf-8 -*-
import logging
import os
import unittest

from pymongo import MongoClient
from pymongo.errors import OperationFailure

from test.utils_shared.test_utils import read_config_into_dict, bootstrap

logging.basicConfig(level=logging.INFO)
bootstrap()


class ExecutionEngine2SchedulerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        deploy = os.environ.get("KB_DEPLOYMENT_CONFIG", "test/deploy.cfg")

        config = read_config_into_dict(deploy, "execution_engine2")

        # For running python interpreter in a docker container
        mongo_in_docker = config.get("mongo-in-docker-compose", None)
        if mongo_in_docker is not None:
            config["mongo-host"] = config["mongo-in-docker-compose"]

        cls.config = config

        cls.ctx = {"job_id": "test", "user_id": "test", "token": "test"}

        cls.mongo_client = MongoClient(
            host=cls.config["mongo-host"],
            port=int(cls.config["mongo-port"]),
            username=cls.config["mongo-user"],
            password=cls.config["mongo-password"],
            authSource="admin",
            authMechanism=cls.config["mongo-authmechanism"],
        )

        cls.db = cls.mongo_client.get_database(cls.config["mongo-database"])

        logging.info(f"Dropping user {cls.config['mongo-user']}")
        try:
            cls.db.command("dropUser", cls.config["mongo-user"])
        except OperationFailure as e:
            logging.info("Couldn't drop user")
            logging.info(e)

        # TODO ADD USER TO EE2?

        try:
            cls.db.command(
                "createUser",
                cls.config["mongo-user"],
                pwd=cls.config["mongo-password"],
                roles=["dbOwner"],
            )
        except OperationFailure:
            logging.info("Couldn't add user")

        logging.info("Done running mongo setup")

    def test_database_configured(self):
        logging.info("\nChecking privileged user exists")
        users_info = self.db.command("usersInfo")
        success = 0
        for user in users_info["users"]:
            if user["user"] == "travis":
                self.assertEqual(
                    [{"role": "dbOwner", "db": self.config["mongo-database"]}],
                    user["roles"],
                )
                success = 1
        self.assertTrue(success)
