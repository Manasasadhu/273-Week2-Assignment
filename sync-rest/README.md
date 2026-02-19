# Synchronous REST — Campus Food Ordering (Part A)

## Overview

- **OrderService** (port 8000): Orchestrator — receives `POST /order`, calls Inventory and Notification synchronously, returns the final result to the client.
- **InventoryService** (port 5001): Manages in-memory food inventory, supports runtime fault injection (`POST /configure`).
- **NotificationService** (port 5002): Logs order confirmation notifications.

All three services are Flask microservices communicating over synchronous HTTP REST calls. The client is **blocked** until every downstream call completes — this is the key characteristic being demonstrated.

## Quick Start

### 1. Build & Start Services

```bash
cd sync-rest/
docker compose up --build -d
```

### 2. Place a Test Order

```bash
curl -X POST http://localhost:8000/order \
  -H "Content-Type: application/json" \
  -d '{"item": "burger", "qty": 1}'
```

### 3. Endpoints

| Endpoint | Service | Method | Purpose |
|----------|---------|--------|---------|
| `POST /order` | OrderService | POST | Place order → calls Inventory + Notification synchronously |
| `GET /orders` | OrderService | GET | List all orders |
| `POST /reserve` | InventoryService | POST | Reserve inventory for an order |
| `POST /configure` | InventoryService | POST | Runtime fault injection: `{ "delay": 2.0, "failure_rate": 0.5 }` |
| `GET /inventory` | InventoryService | GET | View current inventory levels |
| `GET /health` | All services | GET | Health check |

## Tests

Install test dependencies:

```bash
pip3 install -r tests/requirements.txt
```

### Test 1: Baseline Latency

Sends 100 orders and prints a latency summary (Min, Avg, P50, P95, P99, Max).

```bash
python3 tests/test_baseline_latency.py        # default N=100
python3 tests/test_baseline_latency.py 200     # custom N
```

### Test 2: Delay Injection

Injects a 2s delay into InventoryService, runs 100 baseline + 100 delayed requests, then compares latencies side-by-side.

```bash
python3 tests/test_delay_injection.py
```

### Test 3: Failure Injection

Two failure scenarios:
- **100% failure rate**: Inventory returns 500 → OrderService returns 503 (Service Unavailable)
- **Timeout**: Inventory delay (10s) exceeds OrderService timeout (5s) → OrderService returns 504 (Gateway Timeout)

```bash
python3 tests/test_failure_injection.py
```

## Failure Injection (Runtime)

Test resilience without restarting containers:

```bash
# Add 2-second delay
curl -X POST http://localhost:5001/configure \
  -H "Content-Type: application/json" \
  -d '{"delay": 2.0}'

# Set 50% failure rate
curl -X POST http://localhost:5001/configure \
  -H "Content-Type: application/json" \
  -d '{"failure_rate": 0.5}'

# Reset to normal
curl -X POST http://localhost:5001/configure \
  -H "Content-Type: application/json" \
  -d '{"delay": 0, "failure_rate": 0}'
```
