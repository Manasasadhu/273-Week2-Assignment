"""
Delay Injection Test — Injects a 2s delay into InventoryService at runtime,
measures latency impact, then heals the service.

Run:  python test_delay_injection.py [N]
Default: N = 100
"""

import sys
import time
import requests
from tabulate import tabulate

ORDER_URL = "http://localhost:8000/order"
INVENTORY_CONFIGURE_URL = "http://localhost:5001/configure"
N = int(sys.argv[1]) if len(sys.argv) > 1 else 100
INJECT_DELAY = 2.0  # seconds

ITEMS = ["burger", "pizza", "sushi", "taco", "salad"]


def measure_latencies(label, n):
    """Send n orders and return list of latencies in ms."""
    print(f"\n  Sending {n} requests ({label})...")
    latencies = []
    for i in range(n):
        item = ITEMS[i % len(ITEMS)]
        start = time.time()
        try:
            resp = requests.post(ORDER_URL, json={"item": item, "qty": 1}, timeout=15)
            elapsed_ms = (time.time() - start) * 1000
            latencies.append(elapsed_ms)
        except Exception as e:
            elapsed_ms = (time.time() - start) * 1000
            latencies.append(elapsed_ms)
            print(f"    Request {i+1} failed: {e}")

        if (i + 1) % 20 == 0:
            print(f"    Progress: {i + 1}/{n}")

    return latencies


def stats(latencies):
    """Compute summary statistics."""
    latencies.sort()
    return {
        "min": latencies[0],
        "avg": sum(latencies) / len(latencies),
        "p95": latencies[int(len(latencies) * 0.95)],
        "max": latencies[-1],
    }


def run_test():
    print(f"\n{'='*60}")
    print(f"  DELAY INJECTION TEST — {INJECT_DELAY}s delay, {N} requests")
    print(f"{'='*60}")

    # Step 1: Baseline (ensure clean state)
    print("\n[1/4] Resetting InventoryService to normal...")
    requests.post(INVENTORY_CONFIGURE_URL, json={"delay": 0, "failure_rate": 0})

    baseline = measure_latencies("baseline", N)
    baseline_stats = stats(baseline)

    # Step 2: Inject delay
    print(f"\n[2/4] Injecting {INJECT_DELAY}s delay into InventoryService...")
    resp = requests.post(INVENTORY_CONFIGURE_URL, json={"delay": INJECT_DELAY})
    print(f"    Configure response: {resp.json()}")

    delayed = measure_latencies("with delay", N)
    delayed_stats = stats(delayed)

    # Step 3: Heal
    print("\n[3/4] Healing InventoryService (removing delay)...")
    requests.post(INVENTORY_CONFIGURE_URL, json={"delay": 0})

    # Step 4: Results
    print(f"\n{'='*60}")
    print(f"  COMPARISON TABLE")
    print(f"{'='*60}\n")

    table = [
        ["Baseline", f"{baseline_stats['min']:.2f}", f"{baseline_stats['avg']:.2f}",
         f"{baseline_stats['p95']:.2f}", f"{baseline_stats['max']:.2f}"],
        [f"{INJECT_DELAY}s Delay", f"{delayed_stats['min']:.2f}", f"{delayed_stats['avg']:.2f}",
         f"{delayed_stats['p95']:.2f}", f"{delayed_stats['max']:.2f}"],
    ]
    print(tabulate(table, headers=["Scenario", "Min (ms)", "Avg (ms)", "P95 (ms)", "Max (ms)"],
                   tablefmt="grid"))

    delta = delayed_stats["avg"] - baseline_stats["avg"]
    print(f"\n  Average latency increase: {delta:.2f} ms (~{delta/1000:.1f}s)")
    print(f"\n  EXPLANATION: Because OrderService calls InventoryService")
    print(f"  synchronously, the {INJECT_DELAY}s delay adds directly to every")
    print(f"  order's total latency. The client is blocked for the full duration.\n")


if __name__ == "__main__":
    run_test()
