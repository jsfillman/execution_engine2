import json
from configparser import ConfigParser
from datetime import datetime
from typing import List, Dict
import uuid

import requests
from dotenv import load_dotenv
from lib.execution_engine2.utils.CondorTuples import CondorResources, JobInfo
from lib.execution_engine2.db.models.models import Job, JobInput, Meta
from lib.execution_engine2.db.models.models import Status
from lib.execution_engine2.exceptions import MalformedTimestampException

import os.path


def bootstrap():
    test_env_0 = "../test.env"
    test_env_1 = "test.env"
    test_env_2 = "test/test.env"

    for item in [test_env_0, test_env_1, test_env_2]:
        try:
            load_dotenv(item, verbose=True)
        except Exception:
            pass


def get_example_job(
    user: str = "boris",
    wsid: int = 123,
    authstrat: str = "kbaseworkspace",
    scheduler_id: str = None,
) -> Job:
    j = Job()
    j.user = user
    j.wsid = wsid
    job_input = JobInput()
    job_input.wsid = j.wsid

    job_input.method = "method"
    job_input.requested_release = "requested_release"
    job_input.params = {}
    job_input.service_ver = "dev"
    job_input.app_id = "super_module.super_function"

    m = Meta()
    m.cell_id = "ApplePie"
    job_input.narrative_cell_info = m
    j.job_input = job_input
    j.status = "queued"
    j.authstrat = authstrat

    if scheduler_id is None:
        scheduler_id = str(uuid.uuid4())

    j.scheduler_id = scheduler_id

    return j


def get_example_job_as_dict_for_runjob(
    user=None, wsid=None, authstrat=None, scheduler_id=None
):

    job = get_example_job(
        user=user, wsid=wsid, authstrat=authstrat, scheduler_id=scheduler_id
    )
    job_dict = job.to_mongo().to_dict()
    job_dict["method"] = job["job_input"]["app_id"]
    job_dict["app_id"] = job["job_input"]["app_id"]
    job_dict["service_ver"] = job["job_input"]["service_ver"]
    return job_dict


def _create_sample_params(self):
    params = dict()
    params["job_id"] = self.job_id
    params["user"] = "kbase"
    params["token"] = "test_token"
    params["client_group_and_requirements"] = "njs"
    return params


def read_config_into_dict(config="deploy.cfg", section="execution_engine2"):

    if not os.path.isfile(config):
        raise FileNotFoundError(config + " pwd=" + os.getcwd())
    config_parser = ConfigParser()
    config_parser.read(config)
    config = dict()
    print(config_parser.sections())
    for key, val in config_parser[section].items():
        config[key] = val
    return config


# flake8: noqa: C901
def validate_job_state(state):
    """
    Validates whether a returned Job State has all the required fields with the right format.
    If all is well, returns True,
    otherwise this prints out errors to the command line and returns False.
    Can be just used with assert in tests, like "assert validate_job_state(state)"
    """
    required_fields = {
        "job_id": str,
        "user": str,
        "wsid": int,
        "authstrat": str,
        "job_input": dict,
        "updated": int,
        "created": int,
        "status": str,
    }

    optional_fields = {
        "estimating": int,
        "queued": int,
        "running": int,
        "finished": int,
        "error_code": int,
        "terminated_code": int,
        "errormsg": str,
    }

    timestamp_fields = [
        "created",
        "updated",
        "estimating",
        "queued",
        "running",
        "completed",
    ]

    # fields that have to be present based on the context of different statuses

    valid_statuses = vars(Status)["_member_names_"]

    status_context = {
        "estimating": ["estimating"],
        "running": ["running"],
        "completed": ["completed"],
        "error": ["error_code", "errormsg"],
        "terminated": ["terminated_code"],
    }

    # 1. Make sure required fields are present and of the correct type
    missing_reqs = list()
    wrong_reqs = list()
    for req in required_fields.keys():
        if req not in state:
            missing_reqs.append(req)
        elif not isinstance(state[req], required_fields[req]):
            wrong_reqs.append(req)

    if missing_reqs or wrong_reqs:
        print(f"Job state is missing required fields: {missing_reqs}.")
        for req in wrong_reqs:
            print(
                f"Job state has faulty req - {req} should be of type {required_fields[req]}, but had value {state[req]}."
            )
        return False

    # 2. Make sure that context-specific fields are present and the right type
    status = state["status"]
    if status not in valid_statuses:
        print(f"Job state has invalid status {status}.")
        return False

    if status in status_context:
        context_fields = status_context[status]
        missing_context = list()
        wrong_context = list()
        for field in context_fields:
            if field not in state:
                missing_context.append(field)
            elif not isinstance(state[field], optional_fields[field]):
                wrong_context.append(field)
        if missing_context or wrong_context:
            print(f"Job state is missing status context fields: {missing_context}.")
            for field in wrong_context:
                print(
                    f"Job state has faulty context field - {field} should be of type {optional_fields[field]}, but had value {state[field]}."
                )
            return False

    # 3. Make sure timestamps are really timestamps
    bad_ts = list()
    for ts_type in timestamp_fields:
        if ts_type in state:
            is_second_ts = is_timestamp(state[ts_type])
            if not is_second_ts:
                print(state[ts_type], "is not a second ts")

            is_ms_ts = is_timestamp(state[ts_type] / 1000)
            if not is_ms_ts:
                print(state[ts_type], "is not a millisecond ts")

            if not is_second_ts and not is_ms_ts:
                bad_ts.append(ts_type)

    if bad_ts:
        for ts_type in bad_ts:
            print(
                f"Job state has a malformatted timestamp: {ts_type} with value {state[ts_type]}"
            )
        raise MalformedTimestampException()

    return True


def is_timestamp(ts: int):
    """
    Simple enough - if dateutil.parser likes the string, it's a time string and we return True.
    Otherwise, return False.
    """
    try:
        datetime.fromtimestamp(ts)
        return True
    except ValueError:
        return False


def custom_ws_perm_maker(user_id: str, ws_perms: dict):
    """
    Returns an Adapter for requests_mock that deals with mocking workspace permissions.
    :param user_id: str - the user id
    :param ws_perms: dict of permissions, keys are ws ids, values are permission. Example:
        {123: "a", 456: "w"} means workspace id 123 has admin permissions, and 456 has
        write permission
    :return: an adapter function to be passed to request_mock
    """

    def perm_adapter(request):
        perms_req = request.json().get("params")[0].get("workspaces", [])
        ret_perms = []
        for ws in perms_req:
            ret_perms.append({user_id: ws_perms.get(ws["id"], "n")})
        response = requests.Response()
        response.status_code = 200
        response._content = bytes(
            json.dumps({"result": [{"perms": ret_perms}], "version": "1.1"}), "UTF-8"
        )
        return response

    return perm_adapter


def run_job_adapter(
    ws_perms_info: Dict = None,
    ws_perms_global: List = [],
    client_groups_info: Dict = None,
    module_versions: Dict = None,
    user_roles: List = None,
):
    """
    Mocks POST calls to:
        Workspace.get_permissions_mass,
        Catalog.list_client_group_configs,
        Catalog.get_module_version
    Mocks GET calls to:
        Auth (/api/V2/me)
        Auth (/api/V2/token)

    Returns an Adapter for requests_mock that deals with mocking workspace permissions.
    :param ws_perms_info: dict - keys user_id, and ws_perms
            user_id: str - the user id
            ws_perms: dict of permissions, keys are ws ids, values are permission. Example:
                {123: "a", 456: "w"} means workspace id 123 has admin permissions, and 456 has
                write permission
    :param ws_perms_global: list - list of global workspaces - gives those workspaces a global (user "*") permission of "r"
    :param client_groups_info: dict - keys client_groups (list), function_name, module_name
    :param module_versions: dict - key git_commit_hash (str), others aren't used
    :return: an adapter function to be passed to request_mock
    """

    def perm_adapter(request):
        response = requests.Response()
        response.status_code = 200
        rq_method = request.method.upper()
        if rq_method == "POST":
            params = request.json().get("params")
            method = request.json().get("method")

            result = []
            if method == "Workspace.get_permissions_mass":
                perms_req = params[0].get("workspaces")
                ret_perms = []
                user_id = ws_perms_info.get("user_id")
                ws_perms = ws_perms_info.get("ws_perms", {})
                for ws in perms_req:
                    perms = {user_id: ws_perms.get(ws["id"], "n")}
                    if ws["id"] in ws_perms_global:
                        perms["*"] = "r"
                    ret_perms.append(perms)
                result = [{"perms": ret_perms}]
                print(result)
            elif method == "Catalog.list_client_group_configs":
                result = []
                if client_groups_info is not None:
                    result = [client_groups_info]
            elif method == "Catalog.get_module_version":
                result = [{"git_commit_hash": "some_commit_hash"}]
                if module_versions is not None:
                    result = [module_versions]
            response._content = bytes(
                json.dumps({"result": result, "version": "1.1"}), "UTF-8"
            )
        elif rq_method == "GET":
            if request.url.endswith("/api/V2/me"):
                response._content = bytes(
                    json.dumps({"customroles": user_roles}), "UTF-8"
                )
        return response

    return perm_adapter


def get_sample_condor_resources():
    cr = CondorResources(
        request_cpus="1", request_disk="1GB", request_memory="100M", client_group="njs"
    )
    return cr


def get_sample_condor_info(job=None, error=None):
    if job is None:
        job = dict()
    return JobInfo(info=job, error=error)


def get_sample_job_params(method=None, wsid="123"):

    if not method:
        method = "default_method"

    job_params = {
        "wsid": wsid,
        "method": method,
        "app_id": "MEGAHIT/run_megahit",
        "service_ver": "2.2.1",
        "params": [
            {
                "workspace_name": "wjriehl:1475006266615",
                "read_library_refs": ["18836/5/1"],
                "output_contigset_name": "rhodo_contigs",
                "recipe": "auto",
                "assembler": None,
                "pipeline": None,
                "min_contig_len": None,
            }
        ],
        "job_input": {},
        "parent_job_id": "9998",
        "meta": {"tag": "dev", "token_id": "12345"},
    }

    return job_params
