#!/usr/bin/env python
import os
from datetime import datetime
from bson.objectid import ObjectId
import copy


from configparser import ConfigParser
from pymongo import MongoClient


class RollbakDatabases:

    def _get_ujs_connection(self):
        parser = ConfigParser()
        parser.read(os.environ.get("KB_DEPLOYMENT_CONFIG"))
        self.ujs_host = parser.get("NarrativeJobService", "ujs-mongodb-host")
        self.ujs_db = parser.get("NarrativeJobService", "ujs-mongodb-database")
        self.ujs_user = parser.get("NarrativeJobService", "ujs-mongodb-user")
        self.ujs_pwd = parser.get("NarrativeJobService", "ujs-mongodb-pwd")

        return MongoClient(
            self.ujs_host,
            27017,
            username=self.ujs_user,
            password=self.ujs_pwd,
            authSource=self.ujs_db,
        )

    def _get_exec_engine_connection(self):
        parser = ConfigParser()
        parser.read(os.environ.get("KB_DEPLOYMENT_CONFIG"))
        self.exec_engine_host = parser.get("NarrativeJobService", "mongodb-host")
        self.exec_engine_db = parser.get("NarrativeJobService", "mongodb-database")
        self.exec_engine_user = parser.get("NarrativeJobService", "mongodb-user")
        self.exec_engine_pwd = parser.get("NarrativeJobService", "mongodb-pwd")

        return MongoClient(
            self.exec_engine_host,
            27017,
            username=self.exec_engine_user,
            password=self.exec_engine_pwd,
            authSource=self.exec_engine_db,
        )

    @classmethod
    def _create_ujs_job_rec(self, ee2_job):

        job_id = ee2_job["_id"]
        job_input = ee2_job.get("job_input", {})
        error = ee2_job.get("error", {})

        ujs_job_doc = {"_id": job_id,
                       "user": ee2_job.get("user"),
                       "authstrat": ee2_job.get("authstrat"),
                       "authparam": ee2_job.get("authstrat"),
                       "created": job_id.generation_time,
                       "updated": datetime.fromtimestamp(ee2_job.get("updated")),
                       "estcompl": None,
                       "service": ee2_job.get("user"),
                       "complete": ee2_job.get("status") in ["completed", "terminated", "error"],
                       "desc": ee2_job.get("status"),
                       "error": bool(error),
                       "errormsg": error.get('message'),
                       "maxprog": None,
                       "prog": 0,
                       "progtype": None,
                       "results": {"shocknodes": None,
                                   "shockurl": None,
                                   "workspaceids": None,
                                   "workspaceurl": None},
                       "status": ee2_job.get("status")}

        ujs_job_doc['meta'] = job_input.get("narrative_cell_info")

        running = ee2_job.get("running")
        if running is None:
            ujs_job_doc['started'] = None
        else:
            ujs_job_doc['started'] = datetime.fromtimestamp(running)

        return ujs_job_doc

    @classmethod
    def _create_njs_job_rec(self, ee2_job):

        job_id = ee2_job["_id"]
        job_input = ee2_job.get("job_input", {})

        njs_job_doc = {"_id": ObjectId(),
                       "ujs_job_id": job_id,
                       "awe_job_id": None,
                       "input_shock_id": None,
                       "output_shock_id": None,
                       "app_job_id": None,
                       "creation_time": int(datetime.timestamp(job_id.generation_time) * 1000),
                       "job_output": ee2_job.get("job_output"),
                       "scheduler_type": ee2_job.get("scheduler_type"),
                       "task_id": ee2_job.get("scheduler_id"),
                       "last_job_state": ee2_job.get("status"),
                       "parent_job_id": job_input.get('parent_job_id')}

        njs_job_input = copy.deepcopy(job_input)
        njs_job_input["meta"] = njs_job_input.pop("narrative_cell_info")
        njs_job_doc['job_input'] = njs_job_input

        queued = ee2_job.get("queued")
        if queued is None:
            queue_time = None
        else:
            queue_time = int(queued * 1000)
        njs_job_doc['queue_time'] = queue_time

        running = ee2_job.get("running")
        if running is None:
            exec_start_time = None
        else:
            exec_start_time = int(running * 1000)
        njs_job_doc['exec_start_time'] = exec_start_time

        finished = ee2_job.get("finished")
        if finished is None:
            finish_time = None
        else:
            finish_time = int(finished * 1000)
        njs_job_doc['finish_time'] = finish_time

        return njs_job_doc

    def __init__(self):

        self.exec_engine = self._get_exec_engine_connection()
        self.ujs = self._get_ujs_connection()

        self.ujs_jobs_collection = "jobstate"

        self.njs_jobs_collection = "exec_tasks"
        self.njs_logs_collection = "exec_logs"

        self.ee2_jobs_collection = "ee2_jobs"
        self.ee2_logs_collection = "ee2_logs"

        self.ee2_db = "exec_engine2"

    def rollback_jobs(self):

        ee2_jobs = (
            self.exec_engine
            .get_database(self.ee2_db)
            .get_collection(self.ee2_jobs_collection))

        njs_jobs = (
            self.exec_engine
            .get_database(self.exec_engine_db)
            .get_collection(self.njs_jobs_collection))

        ujs_jobs = (
            self.ujs
            .get_database(self.ujs_db)
            .get_collection(self.ujs_jobs_collection))

        ee2_jobs_cursor = ee2_jobs.find()
        count = 0
        failed_ujs_insert = list()
        failed_njs_insert = list()

        for ee2_job in ee2_jobs_cursor:
            count += 1
            job_id = ee2_job["_id"]

            if not ujs_jobs.find({"id": job_id}).count():

                ujs_job_doc = self._create_ujs_job_rec(ee2_job)

                try:
                    ujs_jobs.insert(ujs_job_doc)
                except Exception:
                    failed_ujs_insert.append(str(job_id))

                njs_job_doc = self._create_njs_job_rec(ee2_job)

                try:
                    njs_jobs.insert(njs_job_doc)
                except Exception:
                    failed_njs_insert.append(str(job_id))

                if count % 100 == 0:
                    print("inserted 100 jobs to NJS/UJS")

        return count, failed_ujs_insert, failed_njs_insert

    def rollback_logs(self):
        ee2_logs = (
            self.exec_engine
            .get_database(self.ee2_db)
            .get_collection(self.ee2_logs_collection))

        njs_logs = (
            self.exec_engine
            .get_database(self.exec_engine_db)
            .get_collection(self.njs_logs_collection))

        ee2_logs_cursor = ee2_logs.find()
        count = 0
        failed_njs_insert = list()

        for ee2_log in ee2_logs_cursor:
            count += 1
            job_id = ee2_log["_id"]

            if not njs_logs.find({"ujs_job_id": str(job_id)}).count():
                njs_logs_doc = {"lines": ee2_log.get("lines"),
                                "ujs_job_id": str(job_id),
                                "original_line_count": ee2_log.get("original_line_count"),
                                "stored_line_count": ee2_log.get("stored_line_count")}

                try:
                    njs_logs.insert(njs_logs_doc)
                except Exception:
                    failed_njs_insert.append(str(job_id))

            if count % 100 == 0:
                print("inserted 100 logs to NJS")

        return count, failed_njs_insert


def main():
    rd = RollbakDatabases()
    count, failed_ujs_insert, failed_njs_insert = rd.rollback_jobs()
    print("attempted to rollback {} job records".format(count))
    print("failed to insert UJS jobs:\n{}\nfailed to insert NJS jobs:\n{}\n".format(failed_ujs_insert, failed_njs_insert))

    count, failed_njs_insert = rd.rollback_logs()
    print("attempted to rollback {} log records".format(count))
    print("failed to insert NJS logs:\n{}\n".format(failed_njs_insert))


if __name__ == "__main__":
    main()
