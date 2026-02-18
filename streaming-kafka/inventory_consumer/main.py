import json
import os
import random
import signal
import sys
import time
from typing import Dict

from confluent_kafka import Consumer, KafkaError, KafkaException, Producer


# Initialized in main()
RUNNING = True


def _handle_signal(signum, _frame):
    global RUNNING
    RUNNING = False
    print(f"Received signal {signum}; shutting down...")


def _load_env() -> Dict[str, str]:
    required = ["BOOTSTRAP_SERVERS", "ORDER_TOPIC", "INVENTORY_TOPIC", "GROUP_ID"]
    env = {key: os.getenv(key) for key in required}
    missing = [key for key, val in env.items() if not val]
    if missing:
        raise RuntimeError(f"Missing required env vars: {', '.join(missing)}")
    env["AUTO_OFFSET_RESET"] = os.getenv("AUTO_OFFSET_RESET", "earliest")
    env["FAIL_RATE"] = float(os.getenv("FAIL_RATE", "0.05"))
    env["THROTTLE_MS"] = int(os.getenv("THROTTLE_MS", "0"))
    return env


def _random_status(fail_rate: float) -> str:
    return "Failure" if random.random() < max(0.0, min(fail_rate, 1.0)) else "Success"


def _build_consumer(env: Dict[str, str]) -> Consumer:
    conf = {
        "bootstrap.servers": env["BOOTSTRAP_SERVERS"],
        "group.id": env["GROUP_ID"],
        "auto.offset.reset": env["AUTO_OFFSET_RESET"],
        "enable.auto.commit": False,
    }
    consumer = Consumer(conf)
    consumer.subscribe([env["ORDER_TOPIC"]])
    return consumer


def _build_producer(env: Dict[str, str]) -> Producer:
    return Producer({"bootstrap.servers": env["BOOTSTRAP_SERVERS"]})


def _process_loop(env: Dict[str, str]) -> None:
    consumer = _build_consumer(env)
    producer = _build_producer(env)
    stats = {"consumed": 0, "produced": 0, "failures": 0}
    throttle = max(env["THROTTLE_MS"], 0) / 1000

    try:
        while RUNNING:
            msg = consumer.poll(1.0)
            if msg is None:
                continue
            if msg.error():
                if msg.error().code() == KafkaError._PARTITION_EOF:
                    continue
                raise KafkaException(msg.error())

            stats["consumed"] += 1
            try:
                payload = json.loads(msg.value())
            except json.JSONDecodeError as exc:
                print(f"Skipping invalid JSON payload: {exc}")
                consumer.commit(message=msg, asynchronous=False)
                continue

            status = _random_status(env["FAIL_RATE"])
            payload["status"] = status
            if status == "Failure":
                stats["failures"] += 1

            producer.produce(
                env["INVENTORY_TOPIC"],
                key=msg.key(),
                value=json.dumps(payload).encode("utf-8"),
            )
            producer.poll(0)
            consumer.commit(message=msg, asynchronous=False)
            stats["produced"] += 1

            if stats["consumed"] % 10 == 0:
                print(
                    f"Consumed={stats['consumed']} Produced={stats['produced']} "
                    f"Failures={stats['failures']}"
                )

            if throttle:
                time.sleep(throttle)
    finally:
        consumer.close()
        producer.flush()
        print(
            "Inventory consumer stopped: "
            f"consumed={stats['consumed']} produced={stats['produced']} failures={stats['failures']}"
        )


def main():
    env = _load_env()
    print("Service starting...")
    print(
        f"BOOTSTRAP_SERVERS={env['BOOTSTRAP_SERVERS']} ORDER_TOPIC={env['ORDER_TOPIC']} "
        f"INVENTORY_TOPIC={env['INVENTORY_TOPIC']} FAIL_RATE={env['FAIL_RATE']}"
    )

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    _process_loop(env)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Fatal error: {exc}")
        sys.exit(1)
