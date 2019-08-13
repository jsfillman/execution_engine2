import datetime
from enum import Enum
import mongoengine

from mongoengine import (
    StringField,
    IntField,
    EmbeddedDocument,
    Document,
    DateTimeField,
    BooleanField,
    ListField,
    LongField,
    EmbeddedDocumentField,
    DynamicField,
    ValidationError,
    ObjectIdField,
    EmbeddedDocumentListField,
)


# TODO Make sure Datetime is correct format
# TODO Use ReferenceField to create a mapping between WSID and JOB IDS?
"""
"created": ISODate("2019-02-19T23:00:57.119Z"),
"updated": ISODate("2019-02-19T23:01:32.132Z"),
"""


class LogLines(EmbeddedDocument):
    """
    Log lines contain the content, whether or not to display the content as an error message,
    the position of the line, and the timestamp
    """

    line = StringField(required=True)
    linepos = IntField(required=True)
    error = BooleanField(default=False)
    ts = DateTimeField(default=datetime.datetime.utcnow())


class JobLog(Document):
    """
    As a job runs, it saves its STDOUT and STDERR here

    """

    primary_key = ObjectIdField(primary_key=True, required=True)
    updated = DateTimeField(default=datetime.datetime.utcnow, autonow=True)
    original_line_count = IntField()
    stored_line_count = IntField()
    lines = ListField()
    # meta = {"db_alias": "logs"}
    meta = {"collection": "ee2_logs"}

    def save(self, *args, **kwargs):
        self.updated = datetime.datetime.utcnow()
        return super(JobLog, self).save(*args, **kwargs)


class Meta(EmbeddedDocument):
    """
    Information about from the cell where this job was run
    """

    run_id = StringField()
    token_id = StringField()
    tag = StringField()
    cell_id = StringField()
    status = StringField()


class CondorResourceUsage(EmbeddedDocument):
    """
    Storing stats about a job's usage
    """

    cpu = ListField()
    memory = ListField()
    timestamp = ListField()

    # Maybe remove this if we always want to make timestamp required
    def save(self, *args, **kwargs):
        self.timestamp.append(datetime.datetime.utcnow())
        return super(CondorResourceUsage, self).save(*args, **kwargs)


class Estimate(EmbeddedDocument):
    """
    Estimator function output goes here
    """

    cpu = IntField()
    memory = StringField()


class JobRequirements(EmbeddedDocument):
    """
    To be populated at runtime during start_job, probably from the Catalog
    """

    clientgroup = StringField()
    cpu = IntField()
    memory = StringField()
    estimate = EmbeddedDocumentField(Estimate)


class JobInput(EmbeddedDocument):
    """
    To be created from the Narrative
    """

    wsid = IntField(required=True)
    method = StringField(required=True)

    requested_release = StringField()
    params = DynamicField()
    service_ver = StringField(required=True)
    app_id = StringField(required=True)
    source_ws_objects = ListField()
    parent_job_id = StringField()
    requirements = EmbeddedDocumentField(JobRequirements)

    narrative_cell_info = EmbeddedDocumentField(Meta, required=True)


class JobOutput(EmbeddedDocument):
    """
    To be created from the successful and possibly also failure run of a job
    """

    version = StringField(required=True)
    id = LongField(required=True)
    result = DynamicField(required=True)


class Status(Enum):
    """
    A job begins at created, then can either be estimating
    """

    created = "created"
    estimating = "estimating"
    queued = "queued"
    running = "running"
    finished = "finished"  # Successful termination
    error = "error"  # Something went wrong
    terminated = "terminated"  # Canceled by user


class AuthStrat(Enum):
    """
    The strings to be passed to the auth service when checking to see if a given token
    has access to the workspace
    """

    kbaseworkspace = "kbaseworkspace"
    execution_engine = "execution_engine"


def valid_status(status):
    try:
        Status(status)
    except Exception:
        raise ValidationError(
            f"{status} is not a valid status {vars(Status)['_member_names_']}"
        )


def valid_authstrat(strat):
    if strat is None:
        pass
    try:
        AuthStrat(strat)
    except Exception:
        raise ValidationError(
            f"{strat} is not a valid Authentication strategy {vars(AuthStrat)['_member_names_']}"
        )


class Job(Document):
    """
    A job is created the execution engine service and it's updated from
    the job and the portal process for the rest of the time
    """

    user = StringField(required=True)
    authstrat = StringField(
        required=True, default="kbaseworkspace", validation=valid_authstrat
    )
    wsid = IntField(required=True)
    status = StringField(required=True, validation=valid_status)
    updated = DateTimeField(default=datetime.datetime.utcnow, autonow=True)
    started = DateTimeField(default=None)
    estimating = DateTimeField(default=None)
    running = DateTimeField(default=None)
    finished = DateTimeField(default=None)
    errormsg = StringField()
    scheduler_type = StringField()
    scheduler_id = StringField()
    scheduler_estimator_id = StringField()
    job_input = EmbeddedDocumentField(JobInput, required=True)
    job_output = EmbeddedDocumentField(JobOutput)
    # meta = {"db_alias": "ee2"}
    meta = {"collection": "ee2_jobs"}

    def save(self, *args, **kwargs):
        self.updated = datetime.datetime.utcnow()
        return super(Job, self).save(*args, **kwargs)


###
### Unused fields that we might want
###

result_example = {
    "shocknodes": [],
    "shockurl": "https://ci.kbase.us/services/shock-api/",
    "workspaceids": [],
    "workspaceurl": "https://ci.kbase.us/services/ws/",
    "results": [
        {
            "servtype": "Workspace",
            "url": "https://ci.kbase.us/services/ws/",
            "id": "psnovichkov:1450397093052/QQ",
            "desc": "description",
        }
    ],
    "prog": 0,
    "maxprog": None,
    "other": {
        "estcompl": None,
        "service": "bsadkhin",
        "desc": "Execution engine job for simpleapp.simple_add",
        "progtype": None,
    },
}


####
#### Unused Stuff to look at
####


class Results(EmbeddedDocument):
    run_id = StringField()
    shockurl = StringField()
    workspaceids = ListField()
    workspaceurl = StringField()
    shocknodes = ListField()
