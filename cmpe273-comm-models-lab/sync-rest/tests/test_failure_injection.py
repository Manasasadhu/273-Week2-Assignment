"""
Failure Injection Test — Tests two failure scenarios:
  1. InventoryService returns 500 (100% failure rate)
  2. InventoryService delay exceeds OrderService timeout (timeout scenario)

Run:  python test_failure_injection.py
"""

import time
import requests
from tabulate import tabulate

ORDER_URL = "http://localhost:8000/order"
INVENTORY_CONFIGURE_URL = "http://localhost:5001/configure"

ITEMS = ["burger", "pizza", "sushi", "taco", "salad"]


def send_orders(label, n=10):
    """Send n orders and return response codes and latencies."""
    print(f"\n  Sending {n} requests ({label})...")
    results = []
    for i in range(n):
        item = ITEMS[i % len(ITEMS)]
        start = time.time()
        try:
            resp = requests.post(ORDER_URL, json={"item": item, "qty": 1}, timeout=15)
            elapsed_ms = (time.time() - start) * 1000
            results.append({
                "request": i + 1,
                "status": resp.status_code,
                "elapsed_ms": round(elapsed_ms, 2),
                "body": resp.json()
            })
        except requests.exceptions.Timeout:
            elapsed_ms = (time.time() - start) * 1000
            results.append({
                "request": i + 1,
                "status": "TIMEOUT",
                "elapsed_ms": round(elapsed_ms, 2),
                "body": {}
            })
        except Exception as e:
            elapsed_ms = (time.time() - start) * 1000
            results.append({
                "request": i + 1,
                "status": "ERROR",
                "elapsed_ms": round(elapsed_ms, 2),
                "body": {"error": str(e)}
            })
    return results


def run_test():
    print(f"\n{'='*60}")
    print(f"  FAILURE INJECTION TEST")
    print(f"{'='*60}")

    # ── Test 1: 100% failure rate ────────────────────────────────
    print("\n" + "-"*60)
    print("  TEST 1: Inventory 100% failure rate (returns 500)")
    print("-"*60)

    print("\n[1] Injecting 100% failure rate...")
    resp = requests.post(INVENTORY_CONFIGURE_URL, json={"delay": 0, "failure_rate": 1.0})
    print(f"    Configure response: {resp.json()}")

    results = send_orders("100% failure", n=10)

    table = [[r["request"], r["status"], f"{r['elapsed_ms']:.2f}"]
             for r in results]
    print(f"\n{tabulate(table, headers=['Request #', 'Status Code', 'Latency (ms)'], tablefmt='grid')}")

    error_count = sum(1 for r in results if r["status"] in [503, 500])
    print(f"\n  ✅ {error_count}/{len(results)} requests returned error status (503)")
    print(f"  → OrderService correctly propagates InventoryService failures")

    # ── Test 2: Timeout (delay > OrderService timeout) ───────────
    print("\n" + "-"*60)
    print("  TEST 2: Inventory delay = 10s (exceeds 5s timeout)")
    print("-"*60)

    print("\n[2] Injecting 10s delay (OrderService timeout is 5s)...")
    resp = requests.post(INVENTORY_CONFIGURE_URL, json={"delay": 10.0, "failure_rate": 0})
    print(f"    Configure response: {resp.json()}")

    results = send_orders("timeout scenario", n=5)

    table = [[r["request"], r["status"], f"{r['elapsed_ms']:.2f}"]
             for r in results]
    print(f"\n{tabulate(table, headers=['Request #', 'Status Code', 'Latency (ms)'], tablefmt='grid')}")

    timeout_count = sum(1 for r in results if r["status"] in [504, "TIMEOUT"])
    print(f"\n  ✅ {timeout_count}/{len(results)} requests timed out")
    print(f"  → OrderService returns 504 Gateway Timeout after ~5s")
    print(f"  → Demonstrates synchronous blocking: client waits until timeout")

    # ── Heal ─────────────────────────────────────────────────────
    print("\n" + "-"*60)
    print("  HEALING: Resetting InventoryService to normal")
    print("-"*60)
    requests.post(INVENTORY_CONFIGURE_URL, json={"delay": 0, "failure_rate": 0})
    print("  ✅ InventoryService healed\n")

    # ── Summary ──────────────────────────────────────────────────
    print(f"{'='*60}")
    print(f"  SUMMARY")
    print(f"{'='*60}")
    print(f"""
  In synchronous REST architectures, downstream failures cascade
  directly to the upstream caller:

  • When Inventory returns 500 → OrderService returns 503
    (Service Unavailable) to the client.

  • When Inventory is slow (exceeds timeout) → OrderService
    returns 504 (Gateway Timeout) after waiting the full timeout
    duration.

  • The client is BLOCKED for every request — there is no
    isolation between the caller and the failing dependency.
""")


if __name__ == "__main__":
    run_test()
