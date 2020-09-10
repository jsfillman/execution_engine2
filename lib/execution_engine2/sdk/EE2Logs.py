from enum import Enum
from typing import Dict, NamedTuple

from lib.execution_engine2.db.models.models import JobLog as JLModel, LogLines
from lib.execution_engine2.exceptions import RecordNotFoundException


# if TYPE_CHECKING:
#     from lib.execution_engine2.sdk.SDKMethodRunner import SDKMethodRunner


class JobPermissions(Enum):
    READ = "r"
    WRITE = "w"
    NONE = "n"


class AddLogResult(NamedTuple):
    success: bool
    stored_line_count: int


class EE2Logs:
    def __init__(self, sdkmr):
        self.sdkmr = sdkmr
        self.mongo_util = self.sdkmr.get_mongo_util()

    def _format_job_logs(self, record_position, log_lines):

        log_lines_formatted = []
        for input_line in log_lines:
            record_position += 1
            ll = LogLines()
            ll.error = int(input_line.get("is_error", 0)) == 1
            ll.linepos = record_position
            ts = input_line.get("ts")
            if ts is not None:
                ts = self.sdkmr.check_and_convert_time(ts, assign_default_time=True)
            ll.ts = ts
            ll.line = input_line.get("line")
            ll.validate()
            log_lines_formatted.append(ll.to_mongo().to_dict())

        return log_lines_formatted

    def _create_new_log(self, pk, log_lines: list):
        """
        :param ee2_log: The mongo ee2_log to operate on
        :param log_lines: The lines to add to this log
        :return:
        """
        with self.mongo_util.mongo_engine_connection():
            jl = JLModel()
            jl.primary_key = pk
            jl.original_line_count = 0
            jl.stored_line_count = 0
            jl.lines = self._format_job_logs(record_position=-1, log_lines=log_lines)
            jl.original_line_count = jl.stored_line_count = len(log_lines)
            jl.save()
        return jl

    def _add_first_logs(self, log_lines, job_id):
        """
        Initialize the log since it doesn't exist
        :param log_lines:
        :param job_id:
        :return:
        """
        self.sdkmr.logger.debug(f"About to create new log record for {job_id}")
        log = self._create_new_log(pk=job_id, log_lines=log_lines)
        return AddLogResult(success=True, stored_line_count=log.stored_line_count)

    def _add_subsequent_logs(self, job_log, log_lines):
        """ Add logs to an existing log entry """
        formatted_logs = self._format_job_logs(
            record_position=job_log["stored_line_count"] - 1, log_lines=log_lines
        )
        record_count = int(job_log["stored_line_count"]) + len(formatted_logs)
        slc = self.mongo_util._push_job_logs(
            formatted_logs, job_id=job_log["_id"], record_count=record_count
        )
        return AddLogResult(success=True, stored_line_count=slc)

    def add_job_logs(self, job_id, log_lines, as_admin=False) -> AddLogResult:
        """
        #Authorization Required : Ability to read and write to the workspace
        #Admin Authorization Required : Ability to Write to the workspace

        #TODO Prevent too many logs in memory
        #TODO Max size of log lines = 1000
        #TODO Error with out of space happened previously. So we just update line count.
        #TODO db.updateExecLogOriginalLineCount(ujsJobId, dbLog.getOriginalLineCount() + lines.size());


        # TODO Limit amount of lines per request?
        # TODO Maybe Prevent Some lines with TS and some without
        # TODO # Handle malformed requests?

        :param sdkmr:
        :param job_id:
        :param log_lines:
        :param as_admin:
        :return:
        """
        job_log = {"stored_line_count": -1}
        self.sdkmr.get_job_with_permission(
            job_id, JobPermissions.WRITE, as_admin=as_admin
        )
        self.sdkmr.logger.debug(f"About to add logs for {job_id}")
        try:
            try:
                job_log = self.mongo_util.get_job_log_pymongo(job_id)
            except RecordNotFoundException:
                return self._add_first_logs(log_lines=log_lines, job_id=job_id)
            return self._add_subsequent_logs(job_log, log_lines)
        except Exception as e:
            self.sdkmr.logger.error(e)
            return AddLogResult(
                success=False, stored_line_count=job_log["stored_line_count"]
            )

    def _get_job_logs(self, job_id, skip_lines, limit=None) -> Dict:
        """
        # TODO Do I have to query this another way so I don't load all lines into memory?
        # Does mongoengine lazy-load it?

        # TODO IMPLEMENT SKIP LINES
        # TODO MAKE ONLY THE TIMESTAMP A STRING, so AS TO NOT HAVING TO LOOP OVER EACH ATTRIBUTE?
        # TODO Filter the lines in the mongo query?
        # TODO AVOID LOADING ENTIRE THING INTO MEMORY?
        # TODO Check if there is an off by one for line_count?


           :returns: instance of type "GetJobLogsResults" (last_line_number -
           common number of lines (including those in skip_lines parameter),
           this number can be used as next skip_lines value to skip already
           loaded lines next time.) -> structure: parameter "lines" of list
           of type "LogLine" -> structure: parameter "line" of String,
           parameter "is_error" of type "boolean" (@range [0,1]), parameter
           "last_line_number" of Long


        :param job_id:
        :param skip_lines:
        :return:
        """

        log = self.mongo_util.get_job_log_pymongo(job_id)
        lines = []
        last_line_number = 0
        count = len(log.get("lines", []))
        for log_line in log.get("lines", []):  # type: LogLines

            if skip_lines and int(skip_lines) >= log_line.get("linepos", 0):
                continue
            linepos = log_line.get("linepos")

            is_error = 0
            if log_line.get("error") is True:
                is_error = 1

            lines.append(
                {"line": log_line.get("line"), "linepos": linepos, "is_error": is_error}
            )
            ts = int(log_line.get("ts", 0) * 1000)
            jan_1_2010 = 1262307660
            if ts > jan_1_2010:
                lines[-1]["ts"] = ts

            last_line_number = max(int(linepos), last_line_number)
            if limit and limit <= len(lines):
                break

        if not lines:  # skipped all lines
            last_line_number = log["stored_line_count"]

        log_obj = {"lines": lines, "last_line_number": last_line_number, "count": count}
        return log_obj

    # @allow_job_read
    def view_job_logs(self, job_id, skip_lines, as_admin=False, limit=None):
        """
        Authorization Required: Ability to read from the workspace
        :param sdkmr: An instance of the SDK Method Runner, which contains the current request context
        :param job_id: The Job ID to view Jobs For
        :param skip_lines: An offset of the job logs
        :return:
        """
        # TODO Pass this into decorator?
        self.sdkmr.get_job_with_permission(
            job_id, JobPermissions.READ, as_admin=as_admin
        )

        return self._get_job_logs(job_id, skip_lines, limit)
