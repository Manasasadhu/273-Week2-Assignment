# Sync-REST Tests

## Prerequisites

- Docker & Docker Compose running all services (`docker compose up --build`)
- Python 3.x on the host

## Setup

```bash
pip install -r requirements.txt
```

## Run Tests

All tests hit `localhost:5000` (OrderService) and `localhost:5001` (InventoryService /configure).

### 1. Baseline Latency

Sends 100 orders and prints a latency summary table.

```bash
python test_baseline_latency.py        # default N=100
python test_baseline_latency.py 200    # custom N
```

### 2. Delay Injection

Injects a 2s delay into InventoryService at runtime, runs baseline + delayed comparison, then heals.

```bash
python test_delay_injection.py
```

### 3. Failure Injection

Tests two failure scenarios:
- **100% failure rate**: Inventory returns 500 → OrderService returns 503
- **Timeout**: Inventory delay (10s) exceeds OrderService timeout (5s) → 504

```bash
python test_failure_injection.py
```
