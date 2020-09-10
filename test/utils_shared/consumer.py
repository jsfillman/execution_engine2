from confluent_kafka import Consumer, KafkaError


def _test_sample_consumer():
    """
     This is for testing
     :return:
     """
    consumer = Consumer(
        {
            "bootstrap.servers": "ci-kafka:9096",
            "group.id": "n/a",
            "auto.offset.reset": "earliest",
        }
    )
    topics = ["ee2"]
    consumer.subscribe(topics)
    print("Consuming from", topics)
    while True:
        msg = consumer.poll(0.5)
        if msg is None:
            continue
        if msg.error():
            if msg.error().code() == KafkaError._PARTITION_EOF:
                print("Reached end of the stream.")
            else:
                print(f"Error: {msg.error()}")
                continue
        print(f"New message: {msg.value().decode('utf-8')}")
    consumer.close()


_test_sample_consumer()
