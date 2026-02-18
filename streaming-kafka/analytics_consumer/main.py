import json
import os
import signal
import sys
import threading
import time
from collections import deque
from hashlib import sha1
from typing import Deque, Dict, Optional, Tuple

from confluent_kafka import Consumer, KafkaError, KafkaException
from flask import Flask, jsonify

STOP_EVENT = threading.Event()


class DuplicateFilter:
    def __init__(self, ttl_seconds: float) -> None:
        self.ttl = max(ttl_seconds, 1)
        self._seen: Dict[str, float] = {}
        self._order: Deque[Tuple[float, str]] = deque()
        self._lock = threading.Lock()

    def register(self, event_id: str) -> bool:
        now = time.time()
        with self._lock:
            self._evict(now)
            if event_id in self._seen:
                return True
            self._seen[event_id] = now
            self._order.append((now, event_id))
            return False

    def _evict(self, now: float) -> None:
        cutoff = now - self.ttl
        while self._order and self._order[0][0] < cutoff:
            _, event_id = self._order.popleft()
            self._seen.pop(event_id, None)


class UniqueOrderWindow:
    def __init__(self, window_seconds: float) -> None:
        self.window = max(window_seconds, 1)
        self._entries: Dict[str, float] = {}
        self._order: Deque[Tuple[float, str]] = deque()

    def track(self, order_id: Optional[str]) -> None:
        if not order_id:
            return
        now = time.time()
        self._entries[order_id] = now
        self._order.append((now, order_id))
        self._evict(now)

    def per_minute(self) -> float:
        self._evict(time.time())
        count = len(self._entries)
        return (count * 60.0) / self.window

    def active_orders(self) -> int:
        self._evict(time.time())
        return len(self._entries)

    def _evict(self, now: float) -> None:
        cutoff = now - self.window
        while self._order and self._order[0][0] < cutoff:
            ts, order_id = self._order.popleft()
            if self._entries.get(order_id) == ts:
                self._entries.pop(order_id, None)


class FailureWindow:
    def __init__(self, window_seconds: float) -> None:
        self.window = max(window_seconds, 1)
        self._events: Deque[Tuple[float, bool]] = deque()
        self._failures = 0

    def track(self, is_failure: bool) -> None:
        now = time.time()
        self._events.append((now, is_failure))
        if is_failure:
            self._failures += 1
        self._evict(now)

    def totals(self) -> Tuple[int, int]:
        self._evict(time.time())
        return len(self._events), self._failures

    def failure_rate_pct(self) -> float:
        total, failures = self.totals()
        print("Total and failures: ", total, "---", failures)
        return (failures / total * 100) if total else 0.0

    def _evict(self, now: float) -> None:
        cutoff = now - self.window
        while self._events and self._events[0][0] < cutoff:
            _, is_failure = self._events.popleft()
            if is_failure:
                self._failures = max(self._failures - 1, 0)


class MetricsAggregator:
    def __init__(self, window_seconds: float) -> None:
        self.order_window = UniqueOrderWindow(window_seconds)
        self.failure_window = FailureWindow(window_seconds)
        self.window_seconds = int(window_seconds)
        self.stats: Dict[str, int] = {"orders": 0, "inventory": 0, "duplicates": 0}
        self._lock = threading.RLock()

    def record_order(self, order_id: Optional[str]) -> None:
        with self._lock:
            self.stats["orders"] += 1
            self.order_window.track(order_id)

    def record_inventory(self, is_failure: bool) -> None:
        with self._lock:
            self.stats["inventory"] += 1
            self.failure_window.track(is_failure)

    def record_duplicate(self) -> None:
        with self._lock:
            self.stats["duplicates"] += 1

    def snapshot(self) -> Dict[str, object]:
        with self._lock:
            inventory_events, failures = self.failure_window.totals()
            return {
                "orders_per_min": self.order_window.per_minute(),
                "inventory_events": inventory_events,
                "failures": failures,
                "failure_rate_pct": self.failure_window.failure_rate_pct(),
                "window_seconds": self.window_seconds,
                "generated_at": time.time(),
            }


class KafkaAnalyticsWorker(threading.Thread):
    def __init__(self, env: Dict[str, object], metrics: MetricsAggregator) -> None:
        super().__init__(daemon=True)
        self.env = env
        self.metrics = metrics
        self._stop = threading.Event()
        self._consumer: Optional[Consumer] = None
        self.deduper = DuplicateFilter(env["WINDOW_SEC"])
        self.throttle = env["THROTTLE_MS"] / 1000.0
        self._group_instance_id = env.get("GROUP_INSTANCE_ID")

    def run(self) -> None:
        self._consumer = self._build_consumer()
        try:
            while not self._stop.is_set():
                msg = self._consumer.poll(0.5)
                if msg is None:
                    continue
                if msg.error():
                    code = msg.error().code()
                    if code == KafkaError._PARTITION_EOF:
                        continue
                    if code == KafkaError.UNKNOWN_TOPIC_OR_PART:
                        print("Kafka topic missing; waiting before retry...")
                        time.sleep(1.0)
                        continue
                    raise KafkaException(msg.error())
                self._handle_message(msg.topic(), msg.key(), msg.value())
                self._consumer.commit(message=msg, asynchronous=False)
                if self.throttle:
                    time.sleep(self.throttle)
        finally:
            if self._consumer:
                self._consumer.close()

    def stop(self) -> None:
        self._stop.set()
        if self._consumer:
            self._consumer.wakeup()

    def _build_consumer(self) -> Consumer:
        conf = {
            "bootstrap.servers": self.env["BOOTSTRAP_SERVERS"],
            "group.id": self.env["GROUP_ID"],
            "auto.offset.reset": self.env["AUTO_OFFSET_RESET"],
            "enable.auto.commit": False,
        }
        if self._group_instance_id:
            conf["group.instance.id"] = self._group_instance_id
        consumer = Consumer(conf)
        consumer.subscribe([self.env["ORDER_TOPIC"], self.env["INVENTORY_TOPIC"]])
        return consumer

    def _handle_message(self, topic: str, key: Optional[bytes], value: Optional[bytes]) -> None:
        try:
            payload = _decode_payload(value)
        except ValueError as exc:
            print(f"Skipping corrupt message on {topic}: {exc}")
            return

        event_id = _event_id(topic, key, payload)
        if self.deduper.register(event_id):
            self.metrics.record_duplicate()
            return

        if topic == self.env["ORDER_TOPIC"]:
            self.metrics.record_order(_resolve_order_id(key, payload))
        elif topic == self.env["INVENTORY_TOPIC"]:
            status = str(payload.get("status", "")).lower()
            self.metrics.record_inventory(status == "failure")
        else:
            print(f"Ignoring unexpected topic {topic}")


class PeriodicReporter(threading.Thread):
    def __init__(self, metrics: MetricsAggregator, interval_sec: float) -> None:
        super().__init__(daemon=True)
        self.metrics = metrics
        self.interval = max(interval_sec, 1.0)
        self._stop = threading.Event()

    def stop(self) -> None:
        self._stop.set()

    def run(self) -> None:
        while not self._stop.wait(self.interval):
            snapshot = self.metrics.snapshot()
            print(
                "[Analytics] orders_per_min={:.2f} failure_rate={:.2f}% inventory_events={} window={}s".format(
                    snapshot["orders_per_min"],
                    snapshot["failure_rate_pct"],
                    snapshot["inventory_events"],
                    snapshot["window_seconds"],
                )
            )


class HttpMetricsServer(threading.Thread):
    def __init__(self, metrics: MetricsAggregator, host: str, port: int) -> None:
        super().__init__(daemon=True)
        self.metrics = metrics
        self.host = host
        self.port = port
        self.app = Flask(__name__)
        self._configure_routes()

    def _configure_routes(self) -> None:
        @self.app.route("/metrics", methods=["GET"])
        def metrics_endpoint():
            return jsonify(self.metrics.snapshot())

    def run(self) -> None:
        self.app.run(host=self.host, port=self.port, use_reloader=False, threaded=True)


def _decode_payload(raw_value: Optional[bytes]) -> Dict:
    if raw_value is None:
        return {}
    try:
        return json.loads(raw_value.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Invalid JSON payload: {exc}") from exc


def _resolve_order_id(message_key: Optional[bytes], payload: Dict) -> Optional[str]:
    if "order_id" in payload:
        return str(payload["order_id"])
    if message_key is not None:
        return message_key.decode("utf-8", errors="ignore") or None
    return None


def _event_id(topic: str, message_key: Optional[bytes], payload: Dict) -> str:
    identifier = payload.get("order_id")
    if identifier is None and message_key is not None:
        identifier = message_key.decode("utf-8", errors="ignore")
    digest = sha1(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()
    return f"{topic}:{identifier or 'na'}:{digest}"


def _load_env() -> Dict[str, object]:
    required = ["BOOTSTRAP_SERVERS", "ORDER_TOPIC", "INVENTORY_TOPIC", "GROUP_ID"]
    env = {key: os.getenv(key) for key in required}
    missing = [key for key, val in env.items() if not val]
    if missing:
        raise RuntimeError(f"Missing required env vars: {', '.join(missing)}")

    return {
        "BOOTSTRAP_SERVERS": env["BOOTSTRAP_SERVERS"],
        "ORDER_TOPIC": env["ORDER_TOPIC"],
        "INVENTORY_TOPIC": env["INVENTORY_TOPIC"],
        "GROUP_ID": env["GROUP_ID"],
        "AUTO_OFFSET_RESET": os.getenv("AUTO_OFFSET_RESET", "earliest"),
        "WINDOW_SEC": float(os.getenv("WINDOW_SEC", "60")),
        "THROTTLE_MS": int(os.getenv("THROTTLE_MS", "0")),
        "HTTP_HOST": os.getenv("HTTP_HOST", "0.0.0.0"),
        "HTTP_PORT": int(os.getenv("HTTP_PORT", "8080")),
        "REPORT_INTERVAL_SEC": float(os.getenv("REPORT_INTERVAL_SEC", "0")),
        "GROUP_INSTANCE_ID": os.getenv("GROUP_INSTANCE_ID", "").strip() or None,
    }


def _handle_signal(signum, _frame) -> None:
    print(f"Received signal {signum}; shutting down analytics stack...")
    STOP_EVENT.set()


def main() -> None:
    env = _load_env()
    metrics = MetricsAggregator(env["WINDOW_SEC"])

    worker = KafkaAnalyticsWorker(env, metrics)
    worker.start()

    http_server = HttpMetricsServer(metrics, env["HTTP_HOST"], env["HTTP_PORT"])
    http_server.start()

    reporter: Optional[PeriodicReporter] = None
    if env["REPORT_INTERVAL_SEC"] > 0:
        reporter = PeriodicReporter(metrics, env["REPORT_INTERVAL_SEC"])
        reporter.start()

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    print(
        "Analytics consumer online. Kafka topics=({}, {}) HTTP={}://{}:{} window={}s static_member={}".format(
            env["ORDER_TOPIC"],
            env["INVENTORY_TOPIC"],
            "http",
            env["HTTP_HOST"],
            env["HTTP_PORT"],
            int(env["WINDOW_SEC"]),
            env["GROUP_INSTANCE_ID"] or "disabled",
        )
    )

    try:
        while not STOP_EVENT.is_set():
            time.sleep(0.5)
    finally:
        worker.stop()
        worker.join()
        if reporter:
            reporter.stop()
            reporter.join()
        print("Analytics consumer stopped.")



if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Fatal analytics error: {exc}")
        sys.exit(1)
