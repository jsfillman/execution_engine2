import json
from collections import OrderedDict
from enum import Enum
from typing import Dict

from bson import ObjectId

from execution_engine2.exceptions import InvalidStatusTransitionException
from execution_engine2.sdk.EE2Constants import JobError
from lib.execution_engine2.authorization.authstrategy import can_read_jobs
from lib.execution_engine2.db.models.models import (
    Job,
    JobOutput,
    Status,
    ErrorCode,
    TerminatedCode,
)
from lib.execution_engine2.utils.KafkaUtils import (
    KafkaCancelJob,
    KafkaCondorCommand,
    KafkaFinishJob,
    KafkaStatusChange,
    KafkaStartJob,
)


class JobPermissions(Enum):
    READ = "r"
    WRITE = "w"
    NONE = "n"


class JobsStatus:
    def __init__(self, sdkmr):
        self.sdkmr = sdkmr

    def handle_held_job(self, cluster_id, as_admin):
        """
        If the job is held, attempt to mark it as an error
        However, if the job finished OK, but then something bad happened with the scheduler,
        leave the job alone
        #TODO Only Admin Users can call this, but only automation really should
        #TODO Reduce number of db calls?
        #TODO Make error code a param?
        :param cluster_id:
        :return:
        """
        job_id = self.sdkmr.get_mongo_util().get_job_batch_name(cluster_id=cluster_id)
        j = self.sdkmr.get_mongo_util().get_job(job_id=job_id)  # type: Job

        try:
            error_message_long = "Job was terminated by automation due to an unexpected error. Please resubmit."
            error_message_short = "Job was held"

            error = JobError(
                code=ErrorCode.job_terminated_by_automation.value,
                name="Job was held",
                message=error_message_long,
                error=error_message_long,
            )._asdict()

            self.finish_job(
                job_id=job_id,
                error_message=error_message_short,
                error_code=ErrorCode.job_terminated_by_automation.value,
                error=dict(error),
                as_admin=as_admin,
            )
            log_line = {
                "line": error_message_long,
                "is_error": True,
            }
            self.sdkmr.get_job_logs().add_job_logs(
                job_id=job_id, log_lines=[log_line], as_admin=True
            )
            j.reload()

        except InvalidStatusTransitionException:
            # Just return the record but don't update it
            pass
        # There's probably a better way and a return type, but not really sure what I need yet
        return json.loads(json.dumps(j.to_mongo().to_dict(), default=str))

    def cancel_job(self, job_id, terminated_code=None, as_admin=False):
        """
        Authorization Required: Ability to Read and Write to the Workspace
        Default for terminated code is Terminated By User
        :param job_id: Job ID To cancel
        :param terminated_code:
        :param as_admin: Cancel the job for a different user
        """
        # Is it inefficient to get the job twice? Is it cached?
        # Maybe if the call fails, we don't actually cancel the job?

        job = self.sdkmr.get_job_with_permission(
            job_id, JobPermissions.WRITE, as_admin=as_admin
        )

        if terminated_code is None:
            terminated_code = TerminatedCode.terminated_by_user.value

        self.sdkmr.get_mongo_util().cancel_job(
            job_id=job_id, terminated_code=terminated_code
        )

        self.sdkmr.logger.debug(
            f"About to cancel job in CONDOR using jobid {job_id} {job.scheduler_id}"
        )

        # TODO Issue #190 IF success['TotalSuccess = 0'] == FALSE, don't send a kafka message?
        self.sdkmr.get_condor().cancel_job(job_id=f"{job.scheduler_id}.0")
        self.sdkmr.kafka_client.send_kafka_message(
            message=KafkaCancelJob(
                job_id=str(job_id),
                previous_status=job.status,
                new_status=Status.terminated.value,
                scheduler_id=job.scheduler_id,
                terminated_code=terminated_code,
            )
        )

        self.sdkmr.kafka_client.send_kafka_message(
            message=KafkaCondorCommand(
                job_id=str(job_id),
                scheduler_id=job.scheduler_id,
                condor_command="condor_rm",
            )
        )

    def check_job_canceled(self, job_id, as_admin=False) -> Dict:
        """
        Authorization Required: None
        Check to see if job is terminated by the user
        :param job_id: KBase Job ID
        :param as_admin: Check whether the job is terminated for a different user
        :return: job_id, whether or not job is canceled, and whether or not job is finished
        """
        job = self.sdkmr.get_job_with_permission(
            job_id, JobPermissions.READ, as_admin=as_admin
        )
        job_status = job.status
        rv = {"job_id": job_id, "canceled": False, "finished": False}
        if Status(job_status) is Status.terminated:
            rv["canceled"] = True
            rv["finished"] = True
        if Status(job_status) in [Status.completed, Status.error, Status.terminated]:
            rv["finished"] = True
        return rv

    def force_update_job_status(
        self, job_id, status, as_admin=False, running_stamp=None, estimating_stamp=None
    ) -> str:
        """
        #TODO Deprecate this in favor of specific methods with specific checks?
        * update_job_status: update status of a job runner record.
        * raise error if job is not found or status is not listed in models.Status
        * Does not update TerminatedCode or ErrorCode
        * Does not update Timestamps
        * Allows invalid state transitions, e.g. Running -> Created
        :param job_id: KBase Job ID
        :param status: A Valid Status based on Status Enum
        :param as_admin: Update the job status for an arbitrary status for a different user
        :return: KBase Job ID
        """

        if not (job_id and status):
            raise ValueError("Please provide both job_id and status")

        if running_stamp and estimating_stamp:
            raise ValueError("Cannot provide both running and estimating stamp!")

        job = self.sdkmr.get_job_with_permission(
            job_id, JobPermissions.WRITE, as_admin=as_admin
        )
        previous_status = job.status
        job.status = status

        if running_stamp:
            job.running = running_stamp
        if estimating_stamp:
            job.estimating = estimating_stamp

        with self.sdkmr.get_mongo_util().mongo_engine_connection():
            job.save()

        self.sdkmr.kafka_client.send_kafka_message(
            message=KafkaStatusChange(
                job_id=str(job_id),
                new_status=status,
                previous_status=previous_status,
                scheduler_id=job.scheduler_id,
            )
        )

        return str(job.id)

    def get_job_status(self, job_id, as_admin=False) -> Dict:
        """
        fetch status of a job runner record. raise error if job is not found
        :param job_id: The KBase Job ID
        :param as_admin: Get the status of someone else's job
        :return: The status of the job
        """
        return_val = dict()
        if not job_id:
            raise ValueError("Please provide valid job_id")
        job = self.sdkmr.get_job_with_permission(
            job_id, JobPermissions.READ, as_admin=as_admin
        )
        return_val["status"] = job.status
        return return_val

    def _finish_job_with_error(self, job_id, error_message, error_code, error=None):
        if error_code is None:
            error_code = ErrorCode.unknown_error.value

        self.sdkmr.get_mongo_util().finish_job_with_error(
            job_id=job_id,
            error_message=error_message,
            error_code=error_code,
            error=error,
        )

    def _finish_job_with_success(self, job_id, job_output):
        """
        Allow either blank job outputs or outputs in a specific format (version/id/result)

        :param job_id: The job to finish
        :param job_output: Either the job output or {}, else something is not right
        """
        output = JobOutput()
        output.version = job_output.get("version")
        output.id = ObjectId(job_output.get("id"))
        output.result = job_output.get("result")

        if job_output != {}:
            try:
                output.validate()
            except Exception as e:
                self.sdkmr.logger.debug(e)
                error_message = "Something was wrong with the output object"
                error_code = ErrorCode.job_missing_output.value
                error = {
                    "code": -1,
                    "name": "Output object is invalid",
                    "message": str(e),
                    "error": str(e),
                }

                self.sdkmr.get_mongo_util().finish_job_with_error(
                    job_id=job_id,
                    error_message=error_message,
                    error_code=error_code,
                    error=error,
                )
                raise Exception(str(e) + str(error_message))

        self.sdkmr.get_mongo_util().finish_job_with_success(
            job_id=job_id, job_output=job_output
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
        """
        #TODO Fix too many open connections to mongoengine

        finish_job: set job record to finish status and update finished timestamp
                    (set job status to "finished" by default. If error_message is given, set job to "error" status)
                    raise error if job is not found or current job status is not "running"
                    (general work flow for job status created -> queued -> estimating -> running -> finished/error/terminated)
        Parameters:
        :param job_id: string - id of job
        :param error_message: string - default None, if given set job to error status
        :param error_code: int - default None, if given give this job an error code
        :param error: dict - default None, if given, set the error to this structure
        :param job_output: dict - default None, if given this job has some output
        """

        job = self.sdkmr.get_job_with_permission(
            job_id=job_id, requested_job_perm=JobPermissions.WRITE, as_admin=as_admin
        )
        if job.status in [
            Status.error.value,
            Status.completed.value,
            Status.terminated.value,
        ]:
            raise InvalidStatusTransitionException(
                f"Cannot finish job with a status of {job.status}"
            )

        if error_message:
            self.sdkmr.logger.debug("Finishing job with an error")
            if error_code is None:
                error_code = ErrorCode.job_crashed.value

            self._finish_job_with_error(
                job_id=job_id,
                error_message=error_message,
                error_code=error_code,
                error=error,
            )

            self.sdkmr.kafka_client.send_kafka_message(
                message=KafkaFinishJob(
                    job_id=str(job_id),
                    new_status=Status.error.value,
                    previous_status=job.status,
                    error_message=error_message,
                    error_code=error_code,
                    scheduler_id=job.scheduler_id,
                )
            )
        elif job_output is None:
            self.sdkmr.logger.debug("Finishing job with an error and missing output")
            if error_code is None:
                error_code = ErrorCode.job_missing_output.value
            msg = "Missing job output required in order to successfully finish job. Something went wrong"
            if error is None:
                error = {"code": error_code, "name": msg, "error": msg, "message": msg}

            self._finish_job_with_error(
                job_id=job_id, error_message=msg, error_code=error_code, error=error
            )

            self.sdkmr.kafka_client.send_kafka_message(
                message=KafkaFinishJob(
                    job_id=str(job_id),
                    new_status=Status.error.value,
                    previous_status=job.status,
                    error_message=msg,
                    error_code=error_code,
                    scheduler_id=job.scheduler_id,
                )
            )
        else:
            self.sdkmr.logger.debug("Finishing job with a success")
            self._finish_job_with_success(job_id=job_id, job_output=job_output)
            self.sdkmr.kafka_client.send_kafka_message(
                message=KafkaFinishJob(
                    job_id=str(job_id),
                    new_status=Status.completed.value,
                    previous_status=job.status,
                    scheduler_id=job.scheduler_id,
                    error_code=None,
                    error_message=None,
                )
            )
            self._send_exec_stats_to_catalog(job_id=job_id)
        self.update_finished_job_with_usage(job_id, as_admin=as_admin)

    def update_finished_job_with_usage(self, job_id, as_admin=None) -> Dict:
        """
        # TODO Does this need a kafka message?
        :param job_id:
        :param as_admin:
        :return:
        """
        job = self.sdkmr.get_job_with_permission(
            job_id=job_id, requested_job_perm=JobPermissions.WRITE, as_admin=as_admin
        )
        if job.status not in [
            Status.completed.value,
            Status.terminated.value,
            Status.error.value,
        ]:
            raise Exception(
                f"Cannot update job {job_id} because it was not yet finished. {job.status}"
            )
        condor = self.sdkmr.get_condor()
        resources = condor.get_job_resource_info(job_id=job_id)
        self.sdkmr.logger.debug(f"Extracted the following condor job ads {resources}")
        self.sdkmr.get_mongo_util().update_job_resources(
            job_id=job_id, resources=resources
        )
        return resources

    def check_job(self, job_id, check_permission, exclude_fields=None):

        """
        check_job: check and return job status for a given job_id

        Parameters:
        job_id: id of job
        """

        self.sdkmr.logger.debug("Start fetching status for job: {}".format(job_id))

        if exclude_fields is None:
            exclude_fields = []

        if not job_id:
            raise ValueError("Please provide valid job_id")

        job_state = self.check_jobs(
            [job_id],
            check_permission=check_permission,
            exclude_fields=exclude_fields,
            return_list=0,
        ).get(job_id)

        if "checkjob_error" in job_state:
            raise PermissionError(job_state["error"])

        return job_state

    def check_jobs(
        self, job_ids, check_permission: bool, exclude_fields=None, return_list=None
    ):
        """
        check_jobs: check and return job status for a given of list job_ids
        """

        if exclude_fields is None:
            exclude_fields = []

        with self.sdkmr.get_mongo_util().mongo_engine_connection():
            jobs = self.sdkmr.get_mongo_util().get_jobs(
                job_ids=job_ids, exclude_fields=exclude_fields
            )

        if check_permission:
            try:
                self.sdkmr.logger.debug(
                    "Checking for read permission to: {}".format(job_ids)
                )
                perms = can_read_jobs(
                    jobs, self.sdkmr.user_id, self.sdkmr.token, self.sdkmr.config
                )
            except RuntimeError as e:
                self.sdkmr.logger.error(
                    f"An error occurred while checking read permissions for jobs {jobs}"
                )
                raise e
        else:
            self.sdkmr.logger.debug(
                "Start fetching status for jobs: {}".format(job_ids)
            )
            perms = [True] * len(jobs)

        job_states = dict()
        for idx, job in enumerate(jobs):
            if not perms[idx]:
                job_states[str(job.id)] = {
                    "failure": f"No read permissions for {job.id}",
                    "check_job_error": True,
                }
            else:
                mongo_rec = job.to_mongo().to_dict()
                del mongo_rec["_id"]
                mongo_rec["job_id"] = str(job.id)
                mongo_rec["created"] = int(job.id.generation_time.timestamp() * 1000)
                mongo_rec["updated"] = int(job.updated * 1000)
                if job.estimating:
                    mongo_rec["estimating"] = int(job.estimating * 1000)
                if job.running:
                    mongo_rec["running"] = int(job.running * 1000)
                if job.finished:
                    mongo_rec["finished"] = int(job.finished * 1000)
                if job.queued:
                    mongo_rec["queued"] = int(job.queued * 1000)

                job_states[str(job.id)] = mongo_rec

        job_states = OrderedDict(
            {job_id: job_states.get(job_id, []) for job_id in job_ids}
        )

        if return_list is not None and self.sdkmr.parse_bool_from_string(return_list):
            job_states = {"job_states": list(job_states.values())}

        return job_states

    def check_workspace_jobs(self, workspace_id, exclude_fields=None, return_list=None):
        """
        check_workspace_jobs: check job status for all jobs in a given workspace
        """
        self.sdkmr.logger.debug(
            "Start fetching all jobs status in workspace: {}".format(workspace_id)
        )

        if exclude_fields is None:
            exclude_fields = []

        ws_auth = self.sdkmr.get_workspace_auth()
        if not ws_auth.can_read(workspace_id):
            self.sdkmr.logger.debug(
                f"User {self.sdkmr.user_id} doesn't have permission to read jobs in workspace {workspace_id}."
            )
            raise PermissionError(
                f"User {self.sdkmr.user_id} does not have permission to read jobs in workspace {workspace_id}"
            )

        with self.sdkmr.get_mongo_util().mongo_engine_connection():
            job_ids = [str(job.id) for job in Job.objects(wsid=workspace_id)]

        if not job_ids:
            return {}

        job_states = self.sdkmr.check_jobs(
            job_ids,
            check_permission=False,
            exclude_fields=exclude_fields,
            return_list=return_list,
        )

        return job_states

    def _send_exec_stats_to_catalog(self, job_id):
        job = self.sdkmr.get_mongo_util().get_job(job_id)

        job_input = job.job_input

        log_exec_stats_params = dict()
        log_exec_stats_params["user_id"] = job.user
        app_id = job_input.app_id
        log_exec_stats_params["app_module_name"] = app_id.split("/")[0]
        log_exec_stats_params["app_id"] = app_id
        method = job_input.method
        log_exec_stats_params["func_module_name"] = method.split(".")[0]
        log_exec_stats_params["func_name"] = method.split(".")[-1]
        log_exec_stats_params["git_commit_hash"] = job_input.service_ver
        log_exec_stats_params["creation_time"] = job.id.generation_time.timestamp()
        log_exec_stats_params["exec_start_time"] = job.running
        log_exec_stats_params["finish_time"] = job.finished
        log_exec_stats_params["is_error"] = int(job.status == Status.error.value)
        log_exec_stats_params["job_id"] = job_id

        self.sdkmr.catalog_utils.catalog.log_exec_stats(log_exec_stats_params)

    def start_job(self, job_id, skip_estimation=True, as_admin=False):
        """
        start_job: set job record to start status ("estimating" or "running") and update timestamp
                   (set job status to "estimating" by default, if job status currently is "created" or "queued".
                    set job status to "running", if job status currently is "estimating")
                   raise error if job is not found or current job status is not "created", "queued" or "estimating"
                   (general work flow for job status created -> queued -> estimating -> running -> finished/error/terminated)

        Parameters:
        job_id: id of job
        skip_estimation: skip estimation step and set job to running directly
        """

        if not job_id:
            raise ValueError("Please provide valid job_id")

        job = self.sdkmr.get_job_with_permission(
            job_id, JobPermissions.WRITE, as_admin=as_admin
        )

        job_status = job.status

        allowed_states = [
            Status.created.value,
            Status.queued.value,
            Status.estimating.value,
        ]
        if job_status not in allowed_states:
            raise ValueError(
                f"Unexpected job status for {job_id}: {job_status}.  You cannot start a job that is not in {allowed_states}"
            )

        with self.sdkmr.get_mongo_util().mongo_engine_connection():
            if job_status == Status.estimating.value or skip_estimation:
                # set job to running status
                self.sdkmr.get_mongo_util().update_job_status(
                    job_id=job_id, status=Status.running.value
                )
            else:
                # set job to estimating status
                self.sdkmr.get_mongo_util().update_job_status(
                    job_id=job_id, status=Status.estimating.value
                )
            job.save()
            job.reload("status")

        self.sdkmr.kafka_client.send_kafka_message(
            message=KafkaStartJob(
                job_id=str(job_id),
                new_status=job.status,
                previous_status=job_status,
                scheduler_id=job.scheduler_id,
            )
        )
