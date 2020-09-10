from dataclasses import dataclass
from typing import Optional, NamedTuple

KBASE_CONCIERGE_USERNAME = "kbaseconcierge"
CONCIERGE_CLIENTGROUP = "kbase_concierge"


class JobError(NamedTuple):
    name: str
    message: str
    code: int
    error: str


@dataclass()
class ConciergeParams:
    """ Set requested params. If you don't specify CG, its automatically set for you"""

    request_cpus: int
    request_memory: int
    request_disk: int
    job_priority: int = None
    account_group: str = None
    requirements_list: list = None
    client_group: Optional[str] = CONCIERGE_CLIENTGROUP
