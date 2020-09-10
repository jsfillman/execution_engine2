"""
A module with commands for checking user privileges for jobs.
This doesn't include checking admin rights.
"""
from typing import Dict, List
from lib.execution_engine2.authorization.workspaceauth import WorkspaceAuth
from lib.execution_engine2.db.models.models import Job
from collections import defaultdict

KBASE_WS_AUTHSTRAT = "kbaseworkspace"


def can_read_job(job: Job, user_id: str, token: str, config: Dict[str, str]) -> bool:
    """
    Returns True if the user has read access to the job, False otherwise.
    :param job: a Job model object
    :param user_id: string - the user id
    :param token: string - the user's auth token
    :param config: dict - the service config
    :returns: bool - True if the user can read the job info
    """
    return _check_permissions(job, user_id, token, config, level="read")


def can_write_job(job: Job, user_id: str, token: str, config: Dict[str, str]) -> bool:
    """
    Returns True if the user has write access to the job, False otherwise.
    :param job: a Job model object
    :param user_id: string - the user id
    :param token: string - the user's auth token
    :param config: dict - the service config
    :returns: bool - True if the user can read the job info
    """
    return _check_permissions(job, user_id, token, config, level="write")


def can_read_jobs(
    jobs: List[Job], user_id: str, token: str, config: Dict[str, str]
) -> List[bool]:
    """
    Returns a list of job permissions in the same order as the given list of Jobs.
    :param job: a Job model object
    :param user_id: string - the user id
    :param token: string - the user's auth token
    :param config: dict - the service config
    :returns: List[bool] - Has True values if the user can read job info, False otherwise
    """
    return _check_permissions_list(jobs, user_id, token, config, level="read")


def can_write_jobs(
    jobs: List[Job], user_id: str, token: str, config: Dict[str, str]
) -> List[bool]:
    """
    Returns a list of job write permissions in the same order as the given list of Jobs.
    :param job: a Job model object
    :param user_id: string - the user id
    :param token: string - the user's auth token
    :param config: dict - the service config
    :returns: List[bool] - Has True values if the user can write job info, False otherwise
    """
    return _check_permissions_list(jobs, user_id, token, config, level="write")


def _check_permissions(
    job: Job, user_id: str, token: str, config: Dict[str, str], level="read"
) -> bool:
    """
    Returns a job permissions, for either read or write ability
    :param job: a Job model object
    :param user_id: string - the user id
    :param token: string - the user's auth token
    :param config: dict - the service config
    :param level: string - if "read", then returns the read value, if "write", return whether the user can write.
    :returns: bool - True if the permission is valid, False otherwise.
    """
    if user_id == job.user:
        return True
    if job.authstrat == KBASE_WS_AUTHSTRAT:
        if job.wsid is None:
            return False
        ws_auth = WorkspaceAuth(token, user_id, config["workspace-url"])
        if level == "read":
            return ws_auth.can_read(job.wsid)
        else:
            return ws_auth.can_write(job.wsid)
    else:
        return user_id == job.user


def _check_permissions_list(
    jobs: List[Job], user_id: str, token: str, config: Dict[str, str], level="read"
) -> List[bool]:
    """
    Returns True for each job the user has read access to, and False for the ones they don't.
    :param job: a Job model object
    :param user_id: string - the user id
    :param token: string - the user's auth token
    :param config: dict - the service config
    :param level: string - if "read" then tests if the Job can be read, otherwise checks if it can be written
    :returns: List[bool] - Has True values if the user can write job info, False otherwise
    """

    # This is a little tricky, but makes either 0 or 1 workspace call.
    # 0. Init list of permissions to all be False.
    # 1. Go over the list of jobs. The ones that match user ids are ok, so set them as True.
    # 2. The ones that don't match, and have an authstrat of kbaseworkspace, get their ws ids and
    #    put them aside in a separate dict. This should have a key of wsid and a (growing) list
    #    of job indices as values.
    # 3. The rest (not the same user, and a different authstrat) are not allowed, so leave them
    #    marked False in the perms list
    # 4. Now, if there's any ids in that wsid dict, use WorkspaceAuth to look 'em up.
    # 5. We can now unravel the mappings. ws_auth_perms -> wsid -> list of indices of jobs with that
    #    wsid.
    # should be just a single ws call to get_permissions_mass, and up to 2 loops over the list of
    # jobs (O(2N) if there's a unique ws id for each job, and fewer comparisons)

    perms = len(jobs) * [False]  # permissions start False

    # job_idx_to_perm = dict()                      # permissions that get returned
    ws_ids_to_jobs = defaultdict(list)
    for idx, j in enumerate(jobs):
        if j.user == user_id:
            # If this job belongs to our user, then they can read it
            perms[idx] = True
            # job_idx_to_perm[idx] = True
        elif j.authstrat == "kbaseworkspace" and j.wsid:
            # If this job has a workspace stuck to it, then mark it
            ws_ids_to_jobs[j.wsid].append(idx)
        else:
            # Otherwise, they can't read it.
            # already set as False, so pass
            pass

    if len(ws_ids_to_jobs):
        # If there's workspaces to look up, go do it.
        ws_auth = WorkspaceAuth(token, user_id, config["workspace-url"])
        if level == "read":
            ws_perms = ws_auth.can_read_list(
                list(ws_ids_to_jobs.keys())
            )  # map from ws_id -> perm
        else:
            ws_perms = ws_auth.can_write_list(list(ws_ids_to_jobs.keys()))
        for ws_id in ws_ids_to_jobs:
            perm = False
            if ws_id in ws_perms:
                perm = ws_perms[ws_id]
            for idx in ws_ids_to_jobs[ws_id]:
                perms[idx] = perm
    return perms
