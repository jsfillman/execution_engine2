#!/usr/bin/env python
# type: ignore
import os
from collections import Counter
from configparser import ConfigParser

jobs_database_name = "ee2_jobs"
from mongoengine import connect

from datetime import datetime

try:
    from lib.execution_engine2.db.models.models import Job, Status, JobInput

except Exception:
    from models import Status, Job, JobInput


class FixEE2JobsDatabase:
    """
    Iterate over each record and set
    * If status is completed/error, set Finished to Updated
    * Running to created
    * Terminated jobs are allowed to not have a running timestamp
    * Estimating jobs are allowed to not have a running timestamp
    """

    def _get_ee2_connection(self):
        parser = ConfigParser()
        parser.read(os.environ.get("KB_DEPLOYMENT_CONFIG"))
        self.ee2_host = parser.get("execution_engine2", "mongo-host")
        self.ee2_db = "exec_engine2"
        self.ee2_user = parser.get("execution_engine2", "mongo-user")
        self.ee2_pwd = parser.get("execution_engine2", "mongo-password")

        return connect(
            db=self.ee2_db,
            host=self.ee2_host,
            port=27017,
            username=self.ee2_user,
            password=self.ee2_pwd,
            authentication_source=self.ee2_db,
            authentication_mechanism="DEFAULT",
        )

    def __init__(self):
        self.ee2 = self._get_ee2_connection()

    @staticmethod
    def fix(dry_run=True):
        statuses = Counter()
        no_running = 0
        no_finished = 0
        broken = 0
        count = 0
        for job in Job.objects:
            count += 1
            print(count)

            running_stamp = True
            finished_stamp = True
            statuses[job.status] += 1
            if job.status in [Status.error.value, Status.completed.value]:

                if job.running is None:
                    # Job is error or complete, should have a running
                    no_running += 1
                    running_stamp = False
                    new_running = job.id.generation_time.timestamp()
                    print(
                        f"About to set new running time to creation of {new_running} "
                    )
                    job.running = new_running

                if job.finished is None:
                    # Job is error or complete, should have had a finished
                    no_finished += 1
                    finished_stamp = False
                    new_finished = job.updated
                    print(
                        f"About to set new finished time to  update time  of {new_finished} {datetime.utcfromtimestamp(new_finished)} "
                    )
                    job.finished = new_finished

                if running_stamp is False or finished_stamp is False:
                    print(
                        f"Found issue with {job.id} {job.user} RunningStampPopulated={running_stamp} FinishedStampPopulated={finished_stamp}"
                    )
                    broken += 1

                if job.queued is None:
                    broken += 1
                    job.queued = job.id.generation_time.timestamp()

                if dry_run is False:
                    job.save(validate=False)

        print("No finished ", no_finished)
        print("No running", no_running)
        print("Broken", broken)
        print(statuses)


if __name__ == "__main__":
    c = FixEE2JobsDatabase()
    c.fix(dry_run=False)
