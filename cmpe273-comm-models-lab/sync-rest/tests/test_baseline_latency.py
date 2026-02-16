"""
Baseline Latency Test — Sends N orders and produces a latency summary table.

Run:  python test_baseline_latency.py [N]
Default: N = 100
"""

import sys
import time
import requests
from tabulate import tabulate

ORDER_URL = "http://localhost:8000/order"
N = int(sys.argv[1]) if len(sys.argv) > 1 else 100

ITEMS = ["burger", "pizza", "sushi", "taco", "salad"]


def run_test():
    print(f"\n{'='*60}")
    print(f"  BASELINE LATENCY TEST — {N} requests")
    print(f"{'='*60}\n")

    latencies = []
    successes = 0
    failures = 0

    for i in range(N):
        item = ITEMS[i % len(ITEMS)]
        payload = {"item": item, "qty": 1}

        start = time.time()
        try:
            resp = requests.post(ORDER_URL, json=payload, timeout=10)
            elapsed_ms = (time.time() - start) * 1000
            latencies.append(elapsed_ms)

            if resp.status_code == 201:
                successes += 1
            else:
                failures += 1

            if (i + 1) % 20 == 0:
                print(f"  Progress: {i + 1}/{N} requests sent...")

        except Exception as e:
            elapsed_ms = (time.time() - start) * 1000
            latencies.append(elapsed_ms)
            failures += 1
            print(f"  Request {i + 1} failed: {e}")

    # Compute statistics
    latencies.sort()
    avg = sum(latencies) / len(latencies)
    p50 = latencies[int(len(latencies) * 0.50)]
    p95 = latencies[int(len(latencies) * 0.95)]
    p99 = latencies[int(len(latencies) * 0.99)]

    print(f"\n{'='*60}")
    print(f"  RESULTS")
    print(f"{'='*60}\n")

    table = [
        ["Total Requests", N],
        ["Successes", successes],
        ["Failures", failures],
        ["Min (ms)", f"{latencies[0]:.2f}"],
        ["Avg (ms)", f"{avg:.2f}"],
        ["P50 (ms)", f"{p50:.2f}"],
        ["P95 (ms)", f"{p95:.2f}"],
        ["P99 (ms)", f"{p99:.2f}"],
        ["Max (ms)", f"{latencies[-1]:.2f}"],
    ]
    print(tabulate(table, headers=["Metric", "Value"], tablefmt="grid"))
    print()


if __name__ == "__main__":
    run_test()
