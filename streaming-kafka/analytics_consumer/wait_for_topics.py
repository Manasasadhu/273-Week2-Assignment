#!/usr/bin/env python3
"""Block startup until required Kafka topics exist."""

from __future__ import annotations

import os
import sys
import time
from typing import Iterable, List

from confluent_kafka.admin import AdminClient


def _env(name: str, default: str | None = None) -> str:
    value = os.getenv(name, default)
    if value is None or value.strip() == "":
        raise RuntimeError(f"Missing required env var: {name}")
    return value.strip()


def _missing_topics(admin: AdminClient, topics: Iterable[str]) -> List[str]:
    metadata = admin.list_topics(timeout=5)
    missing: List[str] = []
    for topic in topics:
        topic_meta = metadata.topics.get(topic)
        if topic_meta is None or (topic_meta.error and topic_meta.error.code() != 0):
            missing.append(topic)
    return missing


def main() -> None:
    bootstrap = _env("BOOTSTRAP_SERVERS")
    order_topic = _env("ORDER_TOPIC")
    inventory_topic = _env("INVENTORY_TOPIC")

    timeout = float(os.getenv("TOPIC_WAIT_TIMEOUT_SEC", "180"))
    interval = max(float(os.getenv("TOPIC_WAIT_INTERVAL_SEC", "2")), 0.5)
    deadline = time.time() + timeout if timeout > 0 else None

    admin = AdminClient({"bootstrap.servers": bootstrap})
    topics = [order_topic, inventory_topic]
    print(
        "Waiting for Kafka topics: {} (timeout={}s)...".format(
            ", ".join(topics), "∞" if deadline is None else int(timeout)
        ),
        flush=True,
    )

    last_error = None
    while True:
        try:
            missing = _missing_topics(admin, topics)
            if not missing:
                print("All topics are available. Continuing startup.", flush=True)
                return
            print(f"Topics missing ({', '.join(missing)}); retrying in {interval}s...", flush=True)
        except Exception as exc:  # pragma: no cover - defensive logging
            last_error = exc
            print(f"Topic check failed: {exc}; retrying in {interval}s...", flush=True)

        if deadline and time.time() >= deadline:
            raise TimeoutError(
                "Timed out waiting for Kafka topics. Last error: {}".format(last_error)
            )
        time.sleep(interval)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # pragma: no cover - surface failure to entrypoint
        print(f"wait_for_topics.py failed: {exc}", file=sys.stderr, flush=True)
        sys.exit(1)
