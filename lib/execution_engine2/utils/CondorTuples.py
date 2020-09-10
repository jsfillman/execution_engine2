from typing import NamedTuple, Optional, Dict
import enum

# TODO: Update this with proper htcondor type


class JobInfo(NamedTuple):
    info: Optional[Dict]
    error: Optional[Exception]


class SubmissionInfo(NamedTuple):
    clusterid: Optional[str]
    submit: Dict
    error: Optional[Exception]


class CondorResources(NamedTuple):
    request_cpus: str
    request_disk: str
    request_memory: str
    client_group: str


class JobStatusCodes(enum.Enum):
    UNEXPANDED = 0
    IDLE = 1
    RUNNING = 2
    REMOVED = 3
    COMPLETED = 4
    HELD = 5
    SUBMISSION_ERROR = 6
    NOT_FOUND = -1


jsc = {
    "0": "Unexepanded",
    1: "Idle",
    2: "Running",
    3: "Removed",
    4: "Completed",
    5: "Held",
    6: "Submission_err",
    -1: "Not found in condor",
}
