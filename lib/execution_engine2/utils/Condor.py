"""
Authors @bsadkhin
Functions to call condor to manage jobs and extract resource requirements
"""
import logging
import os
import pathlib
import pwd
from configparser import ConfigParser
from typing import Dict, Optional, Any, Tuple

import htcondor

from lib.execution_engine2.exceptions import (
    MissingCondorRequirementsException,
    MissingRunJobParamsException,
)
from lib.execution_engine2.sdk.EE2Runjob import ConciergeParams
from lib.execution_engine2.utils.CondorTuples import (
    CondorResources,
    SubmissionInfo,
    JobInfo,
)
from lib.execution_engine2.utils.Scheduler import Scheduler


class Condor(Scheduler):
    # TODO: Should these be outside of the class?
    REQUEST_CPUS = "request_cpus"
    REQUEST_MEMORY = "request_memory"
    REQUEST_DISK = "request_disk"
    CG = "+CLIENTGROUP"
    EE2 = "execution_engine2"
    ENDPOINT = "kbase-endpoint"
    EXTERNAL_URL = "external-url"
    EXECUTABLE = "executable"
    CATALOG_TOKEN = "catalog-token"
    DOCKER_TIMEOUT = "docker_timeout"
    POOL_USER = "pool_user"
    INITIAL_DIR = "initialdir"
    LEAVE_JOB_IN_QUEUE = "leavejobinqueue"
    TRANSFER_INPUT_FILES = "transfer_input_files"
    PYTHON_EXECUTABLE = "PYTHON_EXECUTABLE"
    DEFAULT_CLIENT_GROUP = "default_client_group"

    def __init__(self, config_filepath):
        self.config = ConfigParser()
        self.override_clientgroup = os.environ.get("OVERRIDE_CLIENT_GROUP", None)
        self.config.read(config_filepath)
        self.ee_endpoint = self.config.get(section=self.EE2, option=self.EXTERNAL_URL)
        self.python_executable = self.config.get(
            section=self.EE2,
            option=self.PYTHON_EXECUTABLE,
            fallback="/miniconda/bin/python",
        )
        self.initial_dir = self.config.get(
            section=self.EE2, option=self.INITIAL_DIR, fallback="/condor_shared"
        )
        executable = self.config.get(section=self.EE2, option=self.EXECUTABLE)
        if not pathlib.Path(executable).exists() and not pathlib.Path(
            self.initial_dir + "/" + executable
        ):
            raise FileNotFoundError(executable)
        self.executable = executable
        self.catalog_token = self.config.get(
            section=self.EE2, option=self.CATALOG_TOKEN
        )
        self.docker_timeout = self.config.get(
            section=self.EE2, option=self.DOCKER_TIMEOUT, fallback="604801"
        )
        self.pool_user = self.config.get(
            section=self.EE2, option=self.POOL_USER, fallback="condor_pool"
        )
        self.leave_job_in_queue = self.config.get(
            section=self.EE2, option=self.LEAVE_JOB_IN_QUEUE, fallback="True"
        )
        self.transfer_input_files = self.config.get(
            section=self.EE2,
            option=self.TRANSFER_INPUT_FILES,
            fallback="/condor_shared/JobRunner.tgz",
        )
        self.logger = logging.getLogger("ee2")

    def setup_environment_vars(self, params: Dict, client_group: str) -> str:
        # 7 day docker job timeout default, Catalog token used to get access to volume mounts
        dm = (
            str(params["cg_resources_requirements"].get("debug_mode", "")).lower()
            == "true"
        )

        environment_vars = {
            "DOCKER_JOB_TIMEOUT": self.docker_timeout,
            "KB_ADMIN_AUTH_TOKEN": self.catalog_token,
            "KB_AUTH_TOKEN": params.get("token"),
            "CLIENTGROUP": client_group,
            "JOB_ID": params.get("job_id"),
            # "WORKDIR": f"{config.get('WORKDIR')}/{params.get('USER')}/{params.get('JOB_ID')}",
            "CONDOR_ID": "$(Cluster).$(Process)",
            "PYTHON_EXECUTABLE": self.python_executable,
            "DEBUG_MODE": str(dm),
            "PARENT_JOB_ID": params.get("parent_job_id", ""),
        }

        environment = ""
        for key, val in environment_vars.items():
            environment += f"{key}={val} "

        return f'"{environment}"'

    @staticmethod
    def _check_for_missing_runjob_params(params: Dict[str, str]) -> None:
        """
        Check for missing runjob parameters
        :param params: Params saved when the job was created
        """
        for item in ("token", "user_id", "job_id", "cg_resources_requirements"):
            if item not in params:
                raise MissingRunJobParamsException(f"{item} not found in params")

    def extract_resources(self, cgrr: Dict[str, str]) -> CondorResources:
        """
        # TODO Validate MB/GB from both config and catalog.
        Checks to see if request_cpus/memory/disk is available
        If not, it sets them based on defaults from the config
        :param cgrr:
        :return:
        """
        self.logger.debug(f"About to extract from {cgrr}")

        client_group = cgrr.get("client_group", "")
        if client_group is None or client_group == "":
            client_group = self.config.get(
                section="DEFAULT", option=self.DEFAULT_CLIENT_GROUP
            )

        if client_group not in self.config.sections():
            raise ValueError(f"{client_group} not found in {self.config.sections()}")

        # TODO Validate that they are a resource followed by a unit
        for key in [self.REQUEST_DISK, self.REQUEST_CPUS, self.REQUEST_MEMORY]:
            if key not in cgrr or cgrr[key] in ["", None]:
                cgrr[key] = self.config.get(section=client_group, option=key)

        if self.override_clientgroup:
            client_group = self.override_clientgroup

        cr = CondorResources(
            str(cgrr.get(self.REQUEST_CPUS)),
            str(cgrr.get(self.REQUEST_DISK)),
            str(cgrr.get(self.REQUEST_MEMORY)),
            client_group,
        )

        return cr

    def extract_requirements(
        self, cgrr: Optional[dict] = None, client_group: Optional[str] = None
    ):
        """

        :param cgrr: Client Groups and Resource Requirements
        :param client_group: Client Group
        :return: A list of condor submit file requirements in (key == value) format
        """
        if cgrr is None or client_group is None:
            raise MissingCondorRequirementsException(
                "Please provide normalized cgrr and client_group"
            )

        requirements_statement = []

        # Default to using a regex
        if str(cgrr.get("client_group_regex", True)).lower() == "true":
            requirements_statement.append(f'regexp("{client_group}",CLIENTGROUP)')
        else:
            requirements_statement.append(f'(CLIENTGROUP == "{client_group}")')

        restricted_requirements = [
            "client_group",
            "client_group_regex",
            self.REQUEST_MEMORY,
            self.REQUEST_DISK,
            self.REQUEST_CPUS,
            "debug_mode",
        ]

        for key, value in cgrr.items():
            if key.lower() not in restricted_requirements:
                requirements_statement.append(f'({key} == "{value}")')

        return requirements_statement

    @staticmethod
    def _add_hardcoded_attributes(sub, job_id):
        sub["universe"] = "vanilla"
        sub["ShouldTransferFiles"] = "YES"
        # If a job exits incorrectly put it on hold
        sub["on_exit_hold"] = "ExitCode =!= 0"
        #  Allow up to 12 hours of no response from job
        sub["JobLeaseDuration"] = "43200"
        #  Allow up to 12 hours for condor drain
        sub["MaxJobRetirementTime"] = "43200"
        # Remove jobs running longer than 7 days
        sub["Periodic_Remove"] = "( RemoteWallClockTime > 604800 )"
        sub["log"] = "runner_logs/$(Cluster).$(Process).log"
        err_file = f"{job_id}.err"
        out_file = f"{job_id}.out"
        err_path = f"runner_logs/{err_file}"
        out_path = f"runner_logs/{out_file}"
        err_path_remap = f"cluster_logs/{err_file}"
        out_path_remap = f"cluster_logs/{out_file}"
        sub["error"] = err_path
        sub["output"] = out_path
        remap = f'"{err_path}={err_path_remap};{out_path}={out_path_remap}"'
        sub["transfer_output_remaps"] = remap
        sub["When_To_Transfer_Output"] = "ON_EXIT_OR_EVICT"
        sub["getenv"] = "false"
        return sub

    def _add_configurable_attributes(self, sub):
        sub[self.LEAVE_JOB_IN_QUEUE] = self.leave_job_in_queue
        sub["initial_dir"] = self.initial_dir
        sub["+Owner"] = f'"{self.pool_user}"'  # Must be quoted
        sub["executable"] = f"{self.initial_dir}/{self.executable}"  # Must exist
        sub["transfer_input_files"] = self.transfer_input_files
        return sub

    def _extract_resources_and_requirements(
        self, sub: Dict[str, Any], cgrr: Dict[str, str]
    ) -> Tuple[Dict[str, Any], str]:
        # Extract minimum condor resource requirements and client_group
        resources = self.extract_resources(cgrr)
        sub["request_cpus"] = resources.request_cpus
        sub["request_memory"] = resources.request_memory
        sub["request_disk"] = resources.request_disk
        client_group = resources.client_group
        # Set requirements statement
        requirements = self.extract_requirements(cgrr=cgrr, client_group=client_group)
        sub["requirements"] = " && ".join(requirements)
        sub["+KB_CLIENTGROUP"] = f'"{client_group}"'
        return (sub, client_group)

    @staticmethod
    def _modify_with_concierge(sub, concierge_params):
        # Remove Concurrency Limits for this Job
        del sub["Concurrency_Limits"]
        # Override Clientgroup
        sub["+KB_CLIENTGROUP"] = f'"{concierge_params.client_group}"'
        if concierge_params.account_group:
            sub["+AccountingGroup"] = concierge_params.account_group
            # Override Resource Requirements
        sub["request_cpus"] = concierge_params.request_cpus
        sub["request_memory"] = concierge_params.request_memory
        sub["request_disk"] = concierge_params.request_disk
        # Build up requirements w/ custom requirements
        sub["requirements"] = f'(CLIENTGROUP == "{concierge_params.client_group}")'
        requirements = []
        if concierge_params.requirements_list:
            for item in concierge_params.requirements_list:
                key, value = item.split("=")
                requirements.append(f'({key} == "{value}")')
        sub["requirements"] += " && ".join(requirements)

        return sub

    def _add_resources_and_special_attributes(
        self, params: Dict, concierge_params: ConciergeParams = None
    ) -> Dict:
        sub = dict()
        sub["JobBatchName"] = params.get("job_id")
        sub["arguments"] = f"{params['job_id']} {self.ee_endpoint}"
        sub = self.add_job_labels(sub=sub, params=params)
        # Extract special requirements
        (sub, client_group) = self._extract_resources_and_requirements(
            sub, params["cg_resources_requirements"]
        )

        sub["+AccountingGroup"] = params.get("user_id")
        sub["Concurrency_Limits"] = params.get("user_id")
        if concierge_params:
            sub = self._modify_with_concierge(sub, concierge_params)
            client_group = concierge_params.client_group
        sub["+AccountingGroup"] = f'"{sub["+AccountingGroup"]}"'

        sub["environment"] = self.setup_environment_vars(
            params, client_group=client_group
        )

        return sub

    # TODO Copy stuff from Concierge Params into #AcctGroup/Clientgroup/JobPrio, CPu/MEMORY/DISK/
    def create_submit(
        self, params: Dict, concierge_params: ConciergeParams = None
    ) -> Dict:
        self._check_for_missing_runjob_params(params)

        sub = self._add_resources_and_special_attributes(params, concierge_params)
        sub = self._add_hardcoded_attributes(sub=sub, job_id=params["job_id"])
        sub = self._add_configurable_attributes(sub)
        # Ensure all values are a string
        for item in sub.keys():
            sub[item] = str(sub[item])
        return sub

    def concierge(self, sub, concierge_params):
        pass

    @staticmethod
    def add_job_labels(sub: Dict, params: Dict[str, str]):
        sub["+KB_PARENT_JOB_ID"] = params.get("parent_job_id", "")
        sub["+KB_MODULE_NAME"] = params.get("method", "").split(".")[0]
        sub["+KB_FUNCTION_NAME"] = params.get("method", "").split(".")[-1]
        sub["+KB_APP_ID"] = params.get("app_id", "")
        sub["+KB_APP_MODULE_NAME"] = params.get("app_id", "").split("/")[0]
        sub["+KB_WSID"] = params.get("wsid", "")
        sub["+KB_SOURCE_WS_OBJECTS"] = ",".join(params.get("source_ws_objects", list()))

        # Ensure double quoted user inputs
        for key in sub.keys():
            if "+KB" in key:
                value = sub[key]
                if value != "":
                    sub[key] = f'"{value}"'

        return sub

    def run_job(
        self,
        params: Dict[str, str],
        submit_file: Dict[str, str] = None,
        concierge_params: Dict[str, str] = None,
    ) -> SubmissionInfo:
        """
        TODO: Add a retry
        TODO: Add list of required params
        :param params:  Params to run the job, such as the username, job_id, token, client_group_and_requirements
        :param submit_file: A optional completed Submit File
        :param concierge_params: Concierge Options for Submit Files
        :return:
        """
        if submit_file is None:
            submit_file = self.create_submit(params, concierge_params)

        return self.run_submit(submit_file)

    def run_submit(self, submit: Dict[str, str]) -> SubmissionInfo:

        sub = htcondor.Submit(submit)
        try:
            schedd = htcondor.Schedd()
            self.logger.debug(schedd)
            self.logger.debug(submit)
            self.logger.debug(os.getuid())
            self.logger.debug(pwd.getpwuid(os.getuid()).pw_name)
            self.logger.debug(submit)
            with schedd.transaction() as txn:
                return SubmissionInfo(str(sub.queue(txn, 1)), sub, None)
        except Exception as e:
            return SubmissionInfo(None, sub, e)

    def get_job_resource_info(
        self, job_id: Optional[str] = None, cluster_id: Optional[str] = None
    ) -> Dict[str, str]:
        if job_id is not None and cluster_id is not None:
            raise Exception("Use only batch name (job_id) or cluster_id, not both")

        condor_stats = self.get_job_info(job_id=job_id, cluster_id=cluster_id)
        # Don't leak token into the logs here
        job_info = condor_stats.info
        if job_info is None:
            return {}

        disk_keys = ["RemoteUserCpu", "DiskUsage_RAW", "DiskUsage"]
        cpu_keys = ["CpusUsage", "CumulativeRemoteSysCpu", "CumulativeRemoteUserCpu"]
        memory_keys = ["ResidentSetSize_RAW", "ResidentSetSize", "ImageSize_RAW"]

        resource_keys = disk_keys + cpu_keys + memory_keys
        held_job_keys = ["HoldReason", "HoldReasonCode"]
        machine_keys = ["RemoteHost", "LastRemoteHost"]
        time_keys = [
            "CommittedTime",
            "CommittedSuspensionTime",
            "CompletionDate",
            "CumulativeSuspensionTime",
            "CumulativeTransferTime",
            "JobCurrentFinishTransferInputDate",
            "JobCurrentFinishTransferOutputDate",
            "JobCurrentStartDate",
            "JobCurrentStartExecutingDate",
            "JobCurrentStartTransferInputDate",
            "JobCurrentStartTransferOutputDate",
        ]

        extracted_resources = dict()
        for key in resource_keys + held_job_keys + machine_keys + time_keys:
            extracted_resources[key] = job_info.get(key)

        return extracted_resources

    def get_job_info(
        self, job_id: Optional[str] = None, cluster_id: Optional[str] = None
    ) -> JobInfo:

        if job_id is not None and cluster_id is not None:
            return JobInfo(
                {}, Exception("Use only batch name (job_id) or cluster_id, not both")
            )

        constraint = None
        if job_id:
            constraint = f'JobBatchName=?="{job_id}"'
        if cluster_id:
            constraint = f"ClusterID=?={cluster_id}"
        self.logger.debug(
            f"About to get job info for {job_id} {cluster_id} {constraint}"
        )

        try:
            job = htcondor.Schedd().query(constraint=constraint, limit=1)
            if len(job) == 0:
                job = [{}]
            return JobInfo(info=job[0], error=None)
        except Exception as e:
            self.logger.debug({"constraint": constraint, "limit": 1})
            raise e
            # return JobInfo(info=None, error=e)

    def get_user_info(self, user_id, projection=None):
        pass

    def cancel_job(self, job_id: str) -> bool:
        """

        :param job_id:
        :return:
        """
        return self.cancel_jobs([f"{job_id}"])

    def cancel_jobs(self, scheduler_ids: list):
        """
        Possible return structure like this
        [
            TotalJobAds = 10;
            TotalPermissionDenied = 0;
            TotalAlreadyDone = 0;
            TotalNotFound = 0;
            TotalSuccess = 1;
            TotalChangedAds = 1;
            TotalBadStatus = 0;
            TotalError = 0
        ]
        :param scheduler_ids:  List of string of condor job ids to cancel
        :return:
        """

        if not isinstance(scheduler_ids, list):
            raise Exception("Please provide a list of condor ids to cancel")

        try:
            cancel_jobs = htcondor.Schedd().act(
                action=htcondor.JobAction.Remove, job_spec=scheduler_ids
            )
            self.logger.info(f"Cancel job message for {scheduler_ids} is")
            self.logger.debug(f"{cancel_jobs}")
            return cancel_jobs
        except Exception:
            self.logger.error(
                f"Couldn't cancel jobs f{scheduler_ids}", exc_info=True, stack_info=True
            )
            return False
