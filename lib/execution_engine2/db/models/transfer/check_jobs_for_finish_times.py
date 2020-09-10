#!/usr/bin/env python
# type: ignore
try:
    from .transfer_ujs_njs import MigrateDatabases
    from lib.execution_engine2.db.models.models import Status, valid_status
except:
    from transfer_ujs_njs import MigrateDatabases
    from models import *


ee2_jobs = MigrateDatabases().ee2_jobs
from bson import ObjectId

count = 0
for job in ee2_jobs.find():
    count += 1
    job_id = job["_id"]
    generation_time = ObjectId(job_id).generation_time
    user = job["user"]
    status = job["status"]
    job_input = job.get("job_input")
    wsid = job.get("wsid")
    try:
        valid_status(status)
    except:
        raise Exception(job_id)
    # if count % 500 == 0:
    # print(f"Processed {count} records")

    if status in [Status.error.value, Status.completed.value, Status.terminated.value]:
        end_time = job.get("finished")
        if end_time is None:
            raise Exception("End time is NONE", job_id)

    if status in [Status.running.value]:
        run_time = job.get("running")
        if run_time is None:
            raise Exception("End run_time is NONE", job_id)

    # CHECK TO SEE IF JOB DOESN"T HAVE AN INPUT
    if job_input is None:
        if wsid is not -1:
            print(f"{job_id} {wsid}\t{job_input} {user} {generation_time}")


# Fixed finished jobs with
"""
db.getCollection('ee2_jobs').updateMany({'status' : 'finished'}, {'$set' : {'status' : 'completed'}})
db.getCollection('ee2_jobs').updateMany({'status' : 'terminated'}, {'$set' : {'finished' : 0}})

"""
