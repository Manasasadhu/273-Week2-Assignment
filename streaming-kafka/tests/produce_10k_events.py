#!/usr/bin/env python3
"""End-to-end test that publishes 10k orders and samples analytics metrics."""

import argparse
import datetime as dt
import json
import subprocess
import time
import urllib.request
from pathlib import Path
from typing import Any, Dict, List

DEFAULT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_COMPOSE = DEFAULT_ROOT / "docker-compose.yml"
DEFAULT_REPORT = Path(__file__).with_name("metrics_report.json")
DEFAULT_METRICS_URL = "http://localhost:8080/metrics"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compose-file", default=str(DEFAULT_COMPOSE), help="Path to streaming-kafka docker-compose file")
    parser.add_argument("--metrics-url", default=DEFAULT_METRICS_URL, help="Analytics consumer metrics endpoint")
    parser.add_argument("--duration", type=int, default=120, help="Seconds to sample /metrics for report generation")
    parser.add_argument("--interval", type=float, default=20.0, help="Seconds between metrics samples")
    parser.add_argument("--total-events", type=int, default=10_000, help="Number of order events to burst produce")
    parser.add_argument("--report-file", default=str(DEFAULT_REPORT), help="Path to write the JSON metrics report")
    parser.add_argument("--metrics-timeout", type=int, default=180, help="Seconds to wait for analytics /metrics readiness")
    parser.add_argument("--build", action="store_true", help="Force docker compose to rebuild images before the test")
    parser.add_argument("--skip-up", action="store_true", help="Skip docker compose up (assume stack already running)")
    parser.add_argument("--skip-producer", action="store_true", help="Skip burst producer trigger (debug only)")
    return parser.parse_args()


def run_cmd(cmd: List[str], *, check: bool = True) -> subprocess.CompletedProcess:
    print(f"[cmd] {' '.join(cmd)}")
    return subprocess.run(cmd, check=check)


def ensure_stack(compose_file: Path, build: bool) -> None:
    cmd = ["docker", "compose", "-f", str(compose_file), "up", "-d"]
    if build:
        cmd.append("--build")
    run_cmd(cmd)


def wait_for_metrics(url: str, timeout: int) -> None:
    deadline = time.time() + max(timeout, 1)
    while time.time() < deadline:
        try:
            fetch_metrics(url)
            print("[wait] analytics metrics endpoint is reachable")
            return
        except Exception as exc:  # noqa: BLE001 - we want a best-effort loop
            print(f"[wait] metrics unavailable yet: {exc}")
            time.sleep(5)
    raise TimeoutError(f"Analytics metrics endpoint {url} did not become ready within {timeout} seconds")


def fetch_metrics(url: str) -> Dict[str, Any]:
    with urllib.request.urlopen(url, timeout=10) as response:  # noqa: S310 - intentional local request
        payload = response.read()
        return json.loads(payload)


def trigger_burst(compose_file: Path, total_events: int) -> None:
    cmd = [
        "docker",
        "compose",
        "-f",
        str(compose_file),
        "exec",
        "-T",
        "-e",
        "MODE=burst",
        "-e",
        f"TOTAL_EVENTS={total_events}",
        "-e",
        "EXIT_AFTER_BURST=1",
        "producer_order",
        "python",
        "-u",
        "main.py",
    ]
    run_cmd(cmd)


def sample_metrics(url: str, duration: int, interval: float) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    end_time = time.time() + max(duration, 1)
    while time.time() < end_time:
        ts = dt.datetime.utcnow().isoformat(timespec="seconds") + "Z"
        try:
            snapshot = fetch_metrics(url)
            results.append({"timestamp": ts, "metrics": snapshot})
            summary = (
                f"orders_per_min={snapshot.get('orders_per_min', 0):.2f} "
                f"inventory_events={snapshot.get('inventory_events', 0)} "
                f"failure_rate_pct={snapshot.get('failure_rate_pct', 0):.2f}"
            )
            print(f"[metrics] {ts} {summary}")
        except Exception as exc:  # noqa: BLE001 - record the failure for report visibility
            results.append({"timestamp": ts, "error": str(exc)})
            print(f"[metrics] {ts} error: {exc}")
        time.sleep(max(interval, 1))
    return results


def write_report(report_path: Path, rows: List[Dict[str, Any]]) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    print(f"[report] wrote {len(rows)} samples to {report_path}")


def main() -> None:
    args = parse_args()
    compose_file = Path(args.compose_file).resolve()
    report_path = Path(args.report_file).resolve()

    if not args.skip_up:
        ensure_stack(compose_file, build=args.build)

    wait_for_metrics(args.metrics_url, timeout=args.metrics_timeout)

    if not args.skip_producer:
        trigger_burst(compose_file, args.total_events)

    rows = sample_metrics(args.metrics_url, args.duration, args.interval)
    write_report(report_path, rows)


if __name__ == "__main__":
    main()
