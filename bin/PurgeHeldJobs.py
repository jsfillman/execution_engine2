#!/usr/bin/env python3
import logging
import os
import sys
import time
from configparser import ConfigParser
from datetime import datetime, timedelta
from pathlib import Path

import htcondor

# I wish a knew a better way to do this
sys.path.append(".")

from lib.execution_engine2.utils.SlackUtils import SlackClient
from lib.installed_clients.execution_engine2Client import execution_engine2
from lib.execution_engine2.utils.Condor import Condor

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

config = ConfigParser()
config_filepath = os.environ["KB_DEPLOYMENT_CONFIG"]

# Condor
condor = Condor(config_filepath=config_filepath)
# EE2

cfg = condor.config
ee2_endpoint = cfg.get(section="execution_engine2", option="ee2-url")

ee2 = execution_engine2(url=ee2_endpoint, token=os.environ["EE2_ADMIN_SERVICE_TOKEN"])
# Slack
slack_token = cfg.get(section="execution_engine2", option="slack-token")
# TODO change this channel
slack_client = SlackClient(slack_token, channel="#ee_notifications", debug=True)


def read_events(path):
    """Produce events from a schedd event log forever, blocking until they appear."""
    yield from htcondor.JobEventLog(path.as_posix()).events(None)


def process_events(events, callbacks=None, skip_through=None):
    """
    Consumes job events from an iterator and runs handlers on them.
    Parameters
    ----------
    events
        An iterator of events, as produced by read_event().
    callbacks
        A dictionary mapping htcondor.JobEventType values to handler functions.
        Handler functions should have signature handler(event).
        Their return values are not used.
    skip_through
        The latest timestamp that we have already seen.
        Events with smaller timestamps will be skipped.
        Skipped events will not have handlers called on them.
    """
    if callbacks is None:
        callbacks = {}

    event_timestamp = None
    for event in events:
        event_id = f"{event.type} for {event.cluster}.{event.proc} with timestamp {event.timestamp}"
        logger.debug(f"Processing event {event_id}")
        event_timestamp = event.timestamp
        if skip_through is not None and event.timestamp <= skip_through:
            logger.debug(
                f"Skipping event {event_id} because skipping through event timestamp {skip_through}"
            )
            continue

        handler = callbacks.get(event.type, None)
        if handler is not None:
            logger.debug(f"Calling handler {handler} on event {event_id}")
            handler(event)
        else:
            logger.debug(f"No handler found for event {event_id}")
    return event_timestamp


def get_base_json(event):
    """Get a dictionary populated with basic event information."""
    return {
        "timestamp": event.timestamp,
        "event_type": str(event.type),
        "cluster": event.cluster,
        "proc": event.proc,
    }


def calculate_hold_reason(job_record):
    job_input = job_record.get("job_input")
    condor_job_ads = job_input.get("condor_job_ads")
    if job_input is None or condor_job_ads is None:
        return None

    requested_cpu = None
    requested_disk = None
    requested_memory = None

    requirements = job_input.get("requirements")
    if requirements:
        requested_cpu = requirements.get("cpu")
        requested_disk = requirements.get("disk")
        requested_memory = requirements.get("memory")

    cpu_usage = None
    disk_usage = None
    mem_usage = None

    if condor_job_ads:
        cpu_usage = condor_job_ads.get("CpusUsage")
        disk_usage = condor_job_ads.get("DiskUsage_RAW")
        mem_usage = condor_job_ads.get("ResidentSetSize_RAW")

    hold_reason_message = {}

    if requested_cpu and cpu_usage:
        # todo something here
        pass
    if requested_disk and disk_usage:
        if int(disk_usage) / 1000 >= int(requested_disk):
            hold_reason_message[
                "over_disk"
            ] = f"disk_used ({disk_usage}) >= disk_requested ({requested_disk})"
    if requested_memory and mem_usage:
        if int(mem_usage) / 1000 >= int(requested_memory):
            hold_reason_message[
                "over_memory"
            ] = f"memory_used ({mem_usage}) >= memory_requested ({requested_memory})"

    return hold_reason_message


def handle_hold_event(event):
    j = get_base_json(event)

    cluster_id = j["cluster"]
    if int(event["HoldReasonCode"]) != 16:
        print(f"JSON for job id hold event: {j} {event}")
        try:
            job_record = ee2.handle_held_job(cluster_id=str(cluster_id))
            calculated_hold_reason = calculate_hold_reason(job_record)
            slack_client.ee2_reaper_success(
                job_id=cluster_id,
                batch_name=job_record.get("_id"),
                status=job_record.get("status"),
                calculated_hold_reason=calculated_hold_reason,
                hold_reason_code=event["HoldReasonCode"],
                hold_reason=event["HoldReason"],
            )
        except Exception:
            slack_client.ee2_reaper_failure(endpoint=ee2_endpoint, job_id=cluster_id)


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    event_log_fp = Path("/usr/local/condor/log/condor/event_log")
    N = 5
    last_timestamp = (datetime.now() - timedelta(days=N)).timestamp()
    while True:
        # Maybe the job gets put on hold,
        # but still has time to run a bit and cancel itself so lets give it a chance
        time.sleep(15)
        try:
            last_timestamp = process_events(
                events=read_events((event_log_fp)),
                callbacks={htcondor.JobEventType.JOB_HELD: handle_hold_event},
                skip_through=last_timestamp,
            )
            time.sleep(5)
        except Exception as e:
            slack_client.ee2_reaper_failure(endpoint=ee2_endpoint)
            sys.exit(f"{e}")
