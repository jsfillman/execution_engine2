# -*- coding: utf-8 -*-
"""Module to test out logging to kafka."""
import os
import unittest

from execution_engine2.utils.KafkaUtils import (
    KafkaClient,
    KafkaStatusChange,
    KafkaCreateJob,
    KafkaStartJob,
    KafkaFinishJob,
)
from test.utils_shared.test_utils import read_config_into_dict, bootstrap

bootstrap()


class ExecutionEngine2SchedulerTest(unittest.TestCase):

    # TODO Integration Test with EE2/KAFKA
    # TODO Test to make sure that the correct messages are being sent from the various methods
    # TODO Create a test for each method.. But they are already being tested in the ee2 sdkmr tests though

    @classmethod
    def setUpClass(cls):
        deploy = os.environ.get("KB_DEPLOYMENT_CONFIG", "test/deploy.cfg")
        config = read_config_into_dict(deploy)
        # Should this just be added into read_config_into_dict function?
        mongo_in_docker = config.get("mongo-in-docker-compose", None)
        if mongo_in_docker is not None:
            config["mongo-host"] = config["mongo-in-docker-compose"]

        cls.kc = KafkaClient(config["kafka-host"])

    def test_status_change(self):

        with self.assertRaisesRegexp(
            expected_exception=TypeError,
            expected_regex=r"__init__\(\) missing 1 required positional argument: 'scheduler_id'",
        ):
            self.kc.send_kafka_message(
                KafkaStatusChange(
                    job_id="123", previous_status="created", new_status="queued"
                )
            )

        with self.assertRaises(Exception) as e:
            self.kc.send_kafka_message(
                KafkaCreateJob(job_id="123", user="123", apple="123")
            )
        self.assertRegexpMatches(
            str(e.exception), ".*got an unexpected keyword argument.*"
        )

        with self.assertRaises(Exception) as e:
            self.kc.send_kafka_message(
                KafkaStartJob(
                    job_id="123",
                    previous_status="running",
                    new_status="queued",
                    scheduler_id=123,
                )
            )
        self.assertRegexpMatches(str(e.exception), ".*Invalid previous status.*")

        with self.assertRaises(Exception) as e:
            self.kc.send_kafka_message(
                KafkaFinishJob(
                    job_id="123",
                    previous_status="running",
                    new_status="queued",
                    scheduler_id=123,
                    error_message="hi",
                    error_code=-1,
                )
            )
        self.assertRegexpMatches(str(e.exception), ".*-1 is not a valid ErrorCode.*")

    # def legacy_produce_and_consume(self):
    #     """
    #     Send a message via the kafka utils
    #     and test that the producer callback function works
    #     :return:
    #     """
    #     data = {"job_id": "123", "previous_status": "running", "new_status": "created"}
    #     data2 = copy.copy(data)
    #     data2["error"] = True
    #
    #     with patch("sys.stdout", new=StringIO()) as fakeOutput:
    #         # send_message_to_kafka(data)
    #         # send_message_to_kafka(data2)
    #         stdout = fakeOutput.getvalue().strip()
    #         self.assertIn(f"Message delivered to topic 'ee2':", stdout)
    #
    #     for k, v in data.items():
    #         self.assertIn(k, stdout)
    #         self.assertIn(v, stdout)
    #
    #     # Is order assured?
    #     last_msg = self._consume_last("ee2", "ee2")
    #     for key in data.keys():
    #         value = data[key]
    #         self.assertIn(key, last_msg)
    #         data_value = last_msg[key]
    #         self.assertEquals(value, data_value)
    #
    #     self.assertIn("error", last_msg)
    #
    #     last_msg2 = self._consume_last("ee2", "ee2")
    #     for key in data2.keys():
    #         value2 = data2[key]
    #         self.assertIn(key, last_msg2)
    #         data_value2 = last_msg2[key]
    #         self.assertEquals(value2, data_value2)
    #
    #     self.assertIn("error", last_msg2)
    #
    # @staticmethod
    # def _consume_last(topic, key, timeout=10):
    #     """Consume the most recent message from the topic stream."""
    #     consumer = Consumer(
    #         {
    #             "bootstrap.servers": "kafka",
    #             "group.id": "test_only",
    #             "auto.offset.reset": "earliest",
    #         }
    #     )
    #     consumer.subscribe([topic])
    #     start_time = time.time()
    #     while True:
    #         # get time elapsed in seconds
    #         elapsed = time.time() - start_time
    #         if elapsed > timeout:
    #             # close consumer before throwing error
    #             consumer.close()
    #             raise TimeoutError(
    #                 f"Error: Consumer waited past timeout of {timeout} seconds"
    #             )
    #         msg = consumer.poll(0.5)
    #         if msg is None:
    #             continue
    #         if msg.error():
    #             if msg.error().code() == KafkaError._PARTITION_EOF:
    #                 print("End of stream.")
    #             else:
    #                 print(f"Error: {msg.error()}")
    #             continue
    #         if msg:
    #             consumer.close()
    #             return json.loads(msg.value())
