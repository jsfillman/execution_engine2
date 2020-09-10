# -*- coding: utf-8 -*-
"""Module to provide kafka handlers for internal logging facility."""
import json
import logging
from dataclasses import dataclass
from typing import Optional, Type

from confluent_kafka import Producer

from lib.execution_engine2.db.models.models import Status, ErrorCode

logger = logging.getLogger("ee2")
STATUS_EVENT_TYPE = "job_status_update"
CONDOR_EVENT_TYPE = "condor_request"


VALID_CONDOR_COMMANDS = [
    "condor_q",
    "condor_rm",
    "condor_qedit",
    "condor_status",
    "condor",
    "condor_userprio",
    "condor_prio",
    "condor_hold",
]

EVENT_TYPES = [STATUS_EVENT_TYPE, CONDOR_EVENT_TYPE]
DEFAULT_TOPIC = "ee2"
TOPICS = [DEFAULT_TOPIC]


@dataclass
class StatusRequired:
    job_id: str
    previous_status: str
    new_status: str
    scheduler_id: int

    def __post_init__(self):
        # All state transitions need a previous status, except the created one
        if self.previous_status is None:
            if self.new_status != Status.created.value:
                raise Exception("Need to provide a previous_status")

        # A created job may not have been able to have been submitted to condor, so it may not have a scheduler_id
        if self.new_status not in [Status.created.value, Status.terminated.value]:
            if self.scheduler_id is None:
                message = f"You must pass a scheduler id once the job has been created already. Job status is {self.new_status}"
                logger.error(message)
                raise Exception(message)


@dataclass
class StatusOptional:
    topic: str = DEFAULT_TOPIC
    event_type: str = STATUS_EVENT_TYPE
    error: bool = False

    def __post_init__(self):
        if self.topic not in TOPICS:
            raise Exception(f"Invalid topic {self.topic}")

        if self.event_type not in EVENT_TYPES:
            raise Exception(f"Invalid kafka event_type {self.event_type}")

        if not isinstance(self.error, bool):
            raise TypeError("error must be a bool")


@dataclass
class ErrorOptional:
    error_code: Optional[int]
    error_message: Optional[str]

    def check_for_error(self, new_status):
        if self.error_message is None:
            raise Exception(
                f"Need to provide error_msg for unsuccessful jobs (Status is {new_status})"
            )
        ErrorCode(self.error_code)


@dataclass
class KafkaFinishJob(StatusOptional, ErrorOptional, StatusRequired):
    # A job can end with an error or with 'complete'

    def __post_init__(self):
        # Error is required if the job isn't complete
        if self.new_status is not Status.completed.value:
            self.check_for_error(self.new_status)


@dataclass
class CondorRequired:
    condor_command: str
    job_id: str
    scheduler_id: float

    def __post_init__(self):
        if self.condor_command not in VALID_CONDOR_COMMANDS:
            raise Exception(f"{self.condor_command} not in {VALID_CONDOR_COMMANDS}")


@dataclass
class CondorOptional:
    event_type: str = CONDOR_EVENT_TYPE


@dataclass
class CancelJobRequired:
    terminated_code: int


@dataclass
class KafkaCancelJob(StatusOptional, StatusRequired, CancelJobRequired):
    def __post_init__(self):
        self.status_change = Status.terminated.value

    pass


@dataclass
class KafkaStatusChange(StatusOptional, StatusRequired):
    # Message for generic status changes
    pass


@dataclass
class KafkaQueueChange(StatusOptional, StatusRequired):
    def __post_init__(self):
        self.status_change = Status.queued.value


@dataclass
class KafkaCondorCommand(CondorOptional, CondorRequired):
    # Message when issuing condor commands
    pass


@dataclass
class UserRequired:
    user: str


@dataclass
class KafkaCreateJob(UserRequired):
    job_id: str

    def __post_init__(self):
        self.status_change = Status.created.value


@dataclass
class KafkaStartJob(StatusOptional, StatusRequired):
    # Message for starting job
    def __post_init__(self):
        allowed_states = [
            Status.created.value,
            Status.queued.value,
            Status.estimating.value,
        ]
        if self.previous_status not in allowed_states:
            raise Exception(
                f"Invalid previous status ({self.previous_status}), it should have been in {allowed_states}.  "
            )

        if self.new_status not in [
            Status.queued.value,
            Status.estimating.value,
            Status.running.value,
            Status.created.value,
        ]:
            raise Exception(f"Invalid new state {self.new_status}")

        if self.previous_status == self.new_status:
            if self.previous_status != Status.created.value:
                raise Exception(
                    f"State not updated prev:{self.previous_status} new:{self.new_status}"
                )


def _delivery_report(err, msg):
    if err is not None:
        logger.error(msg)
        msg = "Message delivery failed:", err
        logger.error(msg)


class KafkaClient:
    """
    Convenience class to send a kafka message to our kafka instance.
    You must provide kafka configuration for server_address via hostname:port
    """

    def __init__(self, server_address):
        if server_address is None:
            raise Exception(
                "You must provide a Kafka Server address in deploy.cfg of format hostname:port"
            )
        self.server_address = server_address

    def send_kafka_message(self, message: Type, topic: str = DEFAULT_TOPIC):
        """
        :param message: The message to send to the queue, which likely has been passed thru the dataclass
        :param topic: The kafka topic, default is likely be ee2
        :return:
        """
        try:
            producer = Producer({"bootstrap.servers": self.server_address})
            producer.produce(
                topic, json.dumps(message.__dict__), callback=_delivery_report
            )
            # TODO Remove POLL?
            producer.poll(2)
            logger.debug(
                f"Successfully sent message to kafka at topic={topic} message={json.dumps(message.__dict__)} server_address={self.server_address}"
            )
        except Exception as e:
            logger.debug(
                f"Failed to send message to kafka at topic={topic} message={json.dumps(message.__dict__)} server_address={self.server_address}"
            )
            raise Exception(e)
