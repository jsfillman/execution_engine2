#!/usr/bin/env python
# type: ignore
import os
from configparser import ConfigParser
from datetime import datetime
import dateutil


from pymongo import MongoClient

try:
    from lib.execution_engine2.db.models.models import LogLines, JobLog

except Exception:
    from models import LogLines, JobLog

UNKNOWN = "UNKNOWN"


class MigrateDatabases:
    """
    GET UJS Record, Get corresponding NJS record, combine the two and save them in a new
    collection, using the UJS ID as the primary key
    """

    documents = []

    none_jobs = 0

    def _get_ee2_connection(self) -> MongoClient:
        parser = ConfigParser()
        parser.read(os.environ.get("KB_DEPLOYMENT_CONFIG"))
        self.ee2_host = parser.get("NarrativeJobService", "mongodb-host")
        self.ee2_db = "exec_engine2"
        self.ee2_user = parser.get("NarrativeJobService", "mongodb-user")
        self.ee2_pwd = parser.get("NarrativeJobService", "mongodb-pwd")
        self.ee2_logs_collection_name = "ee2_logs"

        return MongoClient(
            self.ee2_host,
            27017,
            username=self.ee2_user,
            password=self.ee2_pwd,
            authSource=self.ee2_db,
            retryWrites=False,
        )

    def _get_njs_connection(self) -> MongoClient:
        parser = ConfigParser()
        parser.read(os.environ.get("KB_DEPLOYMENT_CONFIG"))
        self.njs_host = parser.get("NarrativeJobService", "mongodb-host")
        self.njs_db = parser.get("NarrativeJobService", "mongodb-database")
        self.njs_user = parser.get("NarrativeJobService", "mongodb-user")
        self.njs_pwd = parser.get("NarrativeJobService", "mongodb-pwd")
        self.njs_logs_collection_name = "exec_logs"

        return MongoClient(
            self.njs_host,
            27017,
            username=self.njs_user,
            password=self.njs_pwd,
            authSource=self.njs_db,
            retryWrites=False,
        )

    def __init__(self):
        self.njs = self._get_njs_connection()
        self.logs = []
        self.threshold = 20

        self.njs_logs = (
            self._get_njs_connection()
            .get_database(self.njs_db)
            .get_collection(self.njs_logs_collection_name)
        )

        self.ee2_logs = (
            self._get_ee2_connection()
            .get_database(self.ee2_db)
            .get_collection(self.ee2_logs_collection_name)
        )

    def save_log(self, log):
        self.logs.append(log.to_mongo())
        if len(self.logs) > self.threshold:
            print("INSERTING ELEMENTS")
            self.ee2_logs.insert_many(self.logs)
            self.logs = []

    def save_remnants(self):
        self.ee2_logs.insert_many(self.logs)
        self.logs = []

    def check_and_convert_time(self, time_input):
        """
        convert input time into timestamp in epoch format
        """
        if not time_input:
            return 0

        try:
            if isinstance(time_input, str):  # input time_input as string
                if time_input.replace(
                    ".", "", 1
                ).isdigit():  # input time_input as numeric string
                    time_input = (
                        float(time_input)
                        if "." in time_input
                        else int(time_input) / 1000.0
                    )
                else:  # input time_input as datetime string
                    time_input = dateutil.parser.parse(time_input).timestamp()
            elif isinstance(
                time_input, int
            ):  # input time_input as epoch timestamps in milliseconds
                time_input = time_input / 1000.0
            elif isinstance(time_input, datetime):
                time_input = time_input.timestamp()

            datetime.fromtimestamp(time_input)  # check current time_input is valid
        except Exception:
            print("Cannot convert time_input into timestamps: {}".format(time_input))
            time_input = 0

        return time_input

    def begin_log_transfer(self):  # flake8: noqa

        logs_cursor = self.njs_logs.find()
        success = 0
        failures = 0
        count = 0
        for log in logs_cursor:
            job_log = JobLog()

            job_log.primary_key = log["ujs_job_id"]
            count += 1
            print(f"Working on {log['ujs_job_id']}", count)

            job_log.original_line_count = log["original_line_count"]
            job_log.stored_line_count = log["stored_line_count"]

            lines = []
            for line in log["lines"]:
                ll = LogLines()
                ll.error = line["is_error"]
                ll.linepos = line["line_pos"]
                ll.line = line["line"]
                ll.ts = self.check_and_convert_time(line.get("ts"))
                ll.validate()
                lines.append(ll)
            job_log.lines = lines
            job_log.validate()
            try:
                print("About to insert log into", self.ee2_db, self.ee2_logs)
                self.ee2_logs.insert_one(job_log.to_mongo())
                success += 1
            except Exception as e:
                print("couldn't insert ", log["ujs_job_id"])
                print(e)
                failures += 1

            # self.save_log(job_log)
        # Save leftover jobs
        # self.save_remnants()

        # TODO SAVE up to 5000 in memory and do a bulk insert
        # a = []
        # a.append(places(**{"name": 'test', "loc": [-87, 101]}))
        # a.append(places(**{"name": 'test', "loc": [-88, 101]}))
        # x = places.objects.insert(a)


c = MigrateDatabases()
c.begin_log_transfer()
