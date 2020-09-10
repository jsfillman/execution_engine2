"""
@Authors bio-boris, tgu2

The purpose of this class is to
* Assist in authentication for reading/modifying records in ee2
* Assist in Admin access to methods
* Provide a function for the corresponding JSONRPC endpoint
* Clients are only loaded if they are necessary

"""
import json
import os
import time
from datetime import datetime
from enum import Enum

import dateutil

from installed_clients.WorkspaceClient import Workspace
from installed_clients.authclient import KBaseAuth
from lib.execution_engine2.authorization.workspaceauth import WorkspaceAuth
from lib.execution_engine2.db.MongoUtil import MongoUtil
from lib.execution_engine2.exceptions import AuthError
from lib.execution_engine2.sdk import (
    EE2Runjob,
    EE2StatusRange,
    EE2Authentication,
    EE2Status,
    EE2Logs,
)
from lib.execution_engine2.sdk.EE2Constants import KBASE_CONCIERGE_USERNAME
from lib.execution_engine2.utils.CatalogUtils import CatalogUtils
from lib.execution_engine2.utils.Condor import Condor
from lib.execution_engine2.utils.EE2Logger import get_logger
from lib.execution_engine2.utils.KafkaUtils import KafkaClient
from lib.execution_engine2.utils.SlackUtils import SlackClient
from lib.execution_engine2.db.models.models import Job


class JobPermissions(Enum):
    READ = "r"
    WRITE = "w"
    NONE = "n"


class SDKMethodRunner:
    """
    The execution engine 2 api calls functions from here.
    """

    """
    CONSTANTS
    """
    JOB_PERMISSION_CACHE_SIZE = 500
    JOB_PERMISSION_CACHE_EXPIRE_TIME = 300  # seconds
    ADMIN_READ_ROLE = "EE2_ADMIN_RO"
    ADMIN_WRITE_ROLE = "EE2_ADMIN"

    def __init__(
        self,
        config,
        user_id=None,
        token=None,
        job_permission_cache=None,
        admin_permissions_cache=None,
        mongo_util=None,
    ):
        self.deployment_config_fp = os.environ["KB_DEPLOYMENT_CONFIG"]
        self.config = config
        self.mongo_util = mongo_util
        self.condor = None
        self.workspace = None
        self.workspace_auth = None
        self.admin_roles = config.get("admin_roles", ["EE2_ADMIN", "EE2_ADMIN_RO"])
        self.catalog_utils = CatalogUtils(
            config["catalog-url"], config["catalog-token"]
        )
        self.workspace_url = config.get("workspace-url")
        self.auth_url = config.get("auth-url")
        self.auth = KBaseAuth(auth_url=config.get("auth-service-url"))
        self.user_id = user_id
        self.token = token
        self.debug = SDKMethodRunner.parse_bool_from_string(config.get("debug"))
        self.logger = get_logger()

        self.job_permission_cache = EE2Authentication.EE2Auth.get_cache(
            cache=job_permission_cache,
            size=self.JOB_PERMISSION_CACHE_SIZE,
            expire=self.JOB_PERMISSION_CACHE_EXPIRE_TIME,
        )
        self.admin_permissions_cache = EE2Authentication.EE2Auth.get_cache(
            cache=admin_permissions_cache,
            size=self.JOB_PERMISSION_CACHE_SIZE,
            expire=self.JOB_PERMISSION_CACHE_EXPIRE_TIME,
        )

        self.is_admin = False
        # self.roles = self.roles_cache.get_roles(user_id,token) or list()
        self._ee2_runjob = None
        self._ee2_status = None
        self._ee2_logs = None
        self._ee2_status_range = None
        self._ee2_auth = None
        self.kafka_client = KafkaClient(config.get("kafka-host"))
        self.slack_client = SlackClient(
            config.get("slack-token"), debug=self.debug, endpoint=config.get("ee2-url")
        )

    # Various Clients: TODO: Think about sending in just required clients, not entire SDKMR

    def get_ee2_auth(self):
        if self._ee2_auth is None:
            self._ee2_auth = EE2Authentication.EE2Auth(self)
        return self._ee2_auth

    def get_jobs_status_range(self):
        if self._ee2_status_range is None:
            self._ee2_status_range = EE2StatusRange.JobStatusRange(self)
        return self._ee2_status_range

    def get_job_logs(self) -> EE2Logs.EE2Logs:
        if self._ee2_logs is None:
            self._ee2_logs = EE2Logs.EE2Logs(self)
        return self._ee2_logs

    def get_runjob(self) -> EE2Runjob.EE2RunJob:
        if self._ee2_runjob is None:
            self._ee2_runjob = EE2Runjob.EE2RunJob(self)
        return self._ee2_runjob

    def get_jobs_status(self) -> EE2Status.JobsStatus:
        if self._ee2_status is None:
            self._ee2_status = EE2Status.JobsStatus(self)
        return self._ee2_status

    def get_workspace_auth(self) -> WorkspaceAuth:
        if self.workspace_auth is None:
            self.workspace_auth = WorkspaceAuth(
                self.token, self.user_id, self.workspace_url
            )
        return self.workspace_auth

    def get_mongo_util(self) -> MongoUtil:
        if self.mongo_util is None:
            self.mongo_util = MongoUtil(self.config)
        return self.mongo_util

    def get_condor(self) -> Condor:
        if self.condor is None:
            self.condor = Condor(self.deployment_config_fp)
        return self.condor

    def get_workspace(self) -> Workspace:
        if self.workspace is None:
            self.workspace = Workspace(token=self.token, url=self.workspace_url)
        return self.workspace

    # Permissions Decorators    #TODO Verify these actually work     #TODO add as_admin to these

    def allow_job_read(func):
        def inner(self, *args, **kwargs):
            job_id = kwargs.get("job_id")
            if job_id is None:
                raise ValueError("Please provide valid job_id")
            self._test_job_permission_with_cache(job_id, JobPermissions.READ)

            return func(self, *args, **kwargs)

        return inner

    def allow_job_write(func):
        def inner(self, *args, **kwargs):
            job_id = kwargs.get("job_id")
            if job_id is None:
                raise ValueError("Please provide valid job_id")
            self._test_job_permission_with_cache(job_id, JobPermissions.WRITE)

            return func(self, *args, **kwargs)

        return inner

    def check_as_admin(self, requested_perm):
        """Check if you have the requested admin permission"""
        return self.get_ee2_auth().check_admin_permission(requested_perm=requested_perm)

    def check_as_concierge(self):
        """Check if you have the requested concierge permission"""
        if not self.user_id == KBASE_CONCIERGE_USERNAME:
            raise AuthError(
                "You are not the concierge user. This method is not for you"
            )

    # API ENDPOINTS

    # ENDPOINTS: Admin Related Endpoints
    def check_is_admin(self):
        """ Authorization Required Read """
        # Check whether if at minimum, a read only admin"
        try:
            return self.check_as_admin(requested_perm=JobPermissions.READ)
        except PermissionError:
            return False

    def get_admin_permission(self):
        return self.get_ee2_auth().retrieve_admin_permissions()

    # ENDPOINTS: Running jobs and getting job input params
    def run_job(self, params, as_admin=False):
        """ Authorization Required Read/Write """
        return self.get_runjob().run(params=params, as_admin=as_admin)

    def run_job_concierge(self, params, concierge_params):
        """ Authorization Required : Be the kbaseconcierge user """
        return self.get_runjob().run(params=params, concierge_params=concierge_params)

    def get_job_params(self, job_id, as_admin=False):
        """ Authorization Required: Read """
        # if as_admin:
        #     self._check_as_admin(requested_perm=JobPermissions.READ)
        return self.get_runjob().get_job_params(job_id=job_id, as_admin=as_admin)

    # ENDPOINTS: Adding and retrieving Logs
    def add_job_logs(self, job_id, log_lines, as_admin=False):
        """ Authorization Required Read/Write """
        return self.get_job_logs().add_job_logs(
            job_id=job_id, log_lines=log_lines, as_admin=as_admin
        )

    def view_job_logs(self, job_id, skip_lines=None, as_admin=False, limit=None):
        """ Authorization Required Read """
        return self.get_job_logs().view_job_logs(
            job_id=job_id, skip_lines=skip_lines, as_admin=as_admin, limit=limit
        )

    # Endpoints: Changing a job's status
    def start_job(self, job_id, skip_estimation=True, as_admin=False):
        """ Authorization Required Read/Write """
        return self.get_jobs_status().start_job(
            job_id=job_id, skip_estimation=skip_estimation, as_admin=as_admin
        )

    def update_job_status(self, job_id, status, as_admin=False):
        # TODO: Make this an ADMIN ONLY function? Why would anyone need to call this who is not an admin?
        """ Authorization Required: Read/Write """
        return self.get_jobs_status().force_update_job_status(
            job_id=job_id, status=status, as_admin=as_admin
        )

    def cancel_job(self, job_id, terminated_code=None, as_admin=False):
        """ Authorization Required Read/Write """
        return self.get_jobs_status().cancel_job(
            job_id=job_id, terminated_code=terminated_code, as_admin=as_admin
        )

    def handle_held_job(self, cluster_id):
        """ Authorization Required Read/Write """
        if self.check_as_admin(requested_perm=JobPermissions.WRITE):
            return self.get_jobs_status().handle_held_job(
                cluster_id=cluster_id, as_admin=True
            )

    def finish_job(
        self,
        job_id,
        error_message=None,
        error_code=None,
        error=None,
        job_output=None,
        as_admin=False,
    ):
        """ Authorization Required Read/Write """

        return self.get_jobs_status().finish_job(
            job_id=job_id,
            error_message=error_message,
            error_code=error_code,
            error=error,
            job_output=job_output,
            as_admin=as_admin,
        )

    # Endpoints: Checking a job's status

    def check_job(self, job_id, exclude_fields=None, as_admin=False):
        """ Authorization Required: Read """
        check_permission = True

        if as_admin is True:
            self.check_as_admin(requested_perm=JobPermissions.READ)
            check_permission = False

        return self.get_jobs_status().check_job(
            job_id=job_id,
            check_permission=check_permission,
            exclude_fields=exclude_fields,
        )

    def check_job_canceled(self, job_id, as_admin=False):
        """ Authorization Required: Read """
        return self.get_jobs_status().check_job_canceled(
            job_id=job_id, as_admin=as_admin
        )

    def get_job_status_field(self, job_id, as_admin=False):
        """ Authorization Required: Read """
        return self.get_jobs_status().get_job_status(job_id=job_id, as_admin=as_admin)

    def check_jobs(
        self,
        job_ids,
        check_permission=True,
        exclude_fields=None,
        return_list=1,
        as_admin=False,
    ):
        """ Authorization Required: Read """
        if as_admin:
            self.check_as_admin(requested_perm=JobPermissions.READ)
            check_permission = False

        return self.get_jobs_status().check_jobs(
            job_ids=job_ids,
            check_permission=check_permission,
            exclude_fields=exclude_fields,
            return_list=return_list,
        )

    def check_jobs_date_range_for_user(
        self,
        creation_start_time,
        creation_end_time,
        job_projection=None,
        job_filter=None,
        limit=None,
        user=None,
        offset=None,
        ascending=None,
        as_admin=False,
    ):
        """ Authorization Required: Read """
        if as_admin:
            self.check_as_admin(requested_perm=JobPermissions.READ)

        return self.get_jobs_status_range().check_jobs_date_range_for_user(
            creation_start_time,
            creation_end_time,
            job_projection=job_projection,
            job_filter=job_filter,
            limit=limit,
            user=user,
            offset=offset,
            ascending=ascending,
        )

    def get_job_with_permission(
        self, job_id, requested_job_perm: JobPermissions, as_admin=False
    ) -> Job:
        """
        Get the job.
        When as_admin, check if you have the required admin_perm or raise a Permissions Exception.
        When requesting as a normal user, check the cache for permissions for the job.
        If the cache contains your permission, return the job
        If the cache doesn't contain your permission, check the job_id and workspace, and then add it to the cache
        If you don't have permissions or are requesting a None permission, raise a Permissions Exception

        :param job_id: KBase Job ID
        :param requested_job_perm: Read or Write Access
        :param as_admin: Check if you have admin permissions based on Permission
        :return: The Job or Raise a Permissions Exception
        """
        # TODO CHeck if a valid ENUM is passed in?
        if requested_job_perm is JobPermissions.NONE:
            raise PermissionError(f"Requesting No Permissions for {job_id}")

        if as_admin:
            self.get_ee2_auth().check_admin_permission(
                requested_perm=requested_job_perm
            )
            job = self.get_mongo_util().get_job(job_id=job_id)
        else:
            permission_found_in_cache = self.get_ee2_auth().get_job_permission_from_cache(
                job_id=job_id, level=requested_job_perm
            )
            job = self.get_mongo_util().get_job(job_id=job_id)
            if not permission_found_in_cache:
                self.get_ee2_auth().test_job_permissions(
                    job=job, job_id=job_id, level=requested_job_perm
                )
        return job

    def check_workspace_jobs(
        self, workspace_id, exclude_fields=None, return_list=None, as_admin=False
    ):
        """
        check_workspace_jobs: check job status for all jobs in a given workspace
        """
        self.logger.debug(
            "Start fetching all jobs status in workspace: {}".format(workspace_id)
        )

        if exclude_fields is None:
            exclude_fields = []
        if as_admin:
            self.check_as_admin(requested_perm=JobPermissions.READ)
        else:
            ws_auth = self.get_workspace_auth()
            if not ws_auth.can_read(workspace_id):
                self.logger.debug(
                    f"User {self.user_id} doesn't have permission to read jobs in workspace {workspace_id}."
                )
                raise PermissionError(
                    f"User {self.user_id} does not have permission to read jobs in workspace {workspace_id}"
                )

        job_ids = self.get_mongo_util().get_workspace_jobs(workspace_id=workspace_id)

        if not job_ids:
            return {}

        job_states = self.check_jobs(
            job_ids,
            check_permission=False,
            exclude_fields=exclude_fields,
            return_list=return_list,
        )

        return job_states

    @staticmethod
    def parse_bool_from_string(str_or_bool):
        if isinstance(str_or_bool, bool):
            return str_or_bool

        if isinstance(str_or_bool, int):
            return str_or_bool

        if isinstance(json.loads(str_or_bool.lower()), bool):
            return json.loads(str_or_bool.lower())

        raise Exception("Not a boolean value")

    @staticmethod
    def check_and_convert_time(time_input, assign_default_time=False):
        """
        convert input time into timestamp in epoch format
        """

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
            if assign_default_time:
                time_input = time.time()
            else:
                raise ValueError(
                    "Cannot convert time_input into timestamps: {}".format(time_input)
                )

        return time_input
