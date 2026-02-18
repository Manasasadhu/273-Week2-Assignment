# Streaming Kafka Test Scenarios

This guide captures the three validation exercises we ran on the `streaming-kafka` stack. Each section lists the goal, setup, execution steps, expected metrics, and a placeholder for the video/screenshot evidence you plan to attach later.

## Shared prerequisites

- Docker Desktop/Engine with Compose v2 (same as `README.md`).
- Stack launched from the repo root:
  ```bash
  cd streaming-kafka
  docker compose up --build
  ```
- Analytics consumer HTTP endpoint reachable at `http://localhost:8080/metrics`.

---

## 1. Producing 10k events

**Goal**: Stress the pipeline with a deterministic burst so we can capture baseline throughput and error rates.

1. Ensure the stack is running (start command above).
2. Trigger a one-off burst directly inside the producer container:
   ```bash
   cd streaming-kafka
   docker compose exec -T \
     -e MODE=burst \
     -e TOTAL_EVENTS=10000 \
     -e PRINT_EVERY=1000 \
     producer_order python -u main.py
   ```
3. Sample analytics metrics while the burst runs (repeat a few times during/after the burst):
   ```bash
   curl http://localhost:8080/metrics
   ```
4. Capture artifacts:
   - **Video placeholder**: _10k-burst-run.mp4_
   - Published 10k events and calculated metrics 
   - ![img_1.png](img_1.png)

**Expected observations**
- `orders_per_min` spikes during the burst then decays as the inventory consumer drains the backlog.
- `failure_rate_pct` tracks the `FAIL_RATE` defined in `inventory_consumer/inventory.env` (default 5%).

---

## 2. Introducing throttle in analytics consumer

**Goal**: Demonstrate how artificial processing delay surfaces as consumer lag and slower metric refreshes.

1. Edit `analytics_consumer/analytics.env` and set a noticeable throttle, e.g. `THROTTLE_MS=1`.
2. Recreate only the analytics service so other offsets remain intact:
   ```bash
   cd streaming-kafka
   docker compose up --build analytics_consumer
   ```
3. Re-run the burst (or a smaller one) to generate load:
   ```bash
   docker compose exec -T producer_order python -u main.py
   ```
   - Optionally override `TOTAL_EVENTS`, `MODE`, etc., via env vars as shown in the README.
4. Monitor analytics metrics and Kafka lag:
   ```bash
   curl http://localhost:8080/metrics
   docker compose exec kafka kafka-consumer-groups --bootstrap-server kafka:9092 --describe --group analytics-consumer
   ```
5. Capture artifacts:
   - **Video placeholder**: _analytics-throttle-lag.mp4_
   - Consumer lag for analytics-consumer group 
   - ![img.png](img.png)

**Expected observations**
- `/metrics` updates every `REPORT_INTERVAL_SEC`, but values lag behind real-time because each event sleeps `THROTTLE_MS`.
- Kafka `Lag` column for `analytics-consumer` increases during the burst and drains slowly afterward.
- Inventory consumer remains healthy, so the backlog accumulates only on the analytics side.

**Reset**: Restore `THROTTLE_MS=0`, then restart analytics to return to baseline behavior.

---

## 3. Resetting offsets, replaying events, and comparing metrics

**Goal**: Verify deterministic replay behavior by rewinding the analytics consumer to reprocess historical events.

1. Stop the analytics consumer to avoid races (optional but cleaner):
   ```bash
   cd streaming-kafka
   docker compose stop analytics_consumer
   ```
2. Reset offsets for both topics consumed by the analytics group:
   ```bash
   docker compose exec kafka kafka-consumer-groups \
     --bootstrap-server kafka:9092 \
     --group analytics-consumer \
     --topic order-events \
     --topic inventory-events \
     --reset-offsets --to-earliest --execute
   ```
3. Restart analytics and ensure it rejoins:
   ```bash
   docker compose start analytics_consumer
   ```
4. Replay the workload by re-running the same burst command from test #1 (adjust `TOTAL_EVENTS` as needed) and sample metrics again for comparison.
5. Capture artifacts:
   - **Video placeholder**: _offset-reset-replay.mp4_
   - Consumer offset reset before and after
   - ![img_2.png](img_2.png)
   - Metrics calculated after replay - slight different due to 20k orders 
   - ![img_3.png](img_3.png)

**Why metrics may match or differ**
- In the demo, bcz replay happened after 20k offsets/events, the numbers are slight different
- Deterministic aggregations (total orders processed, cumulative failure counts) will return to the same values after replay if the consumers are idempotent.
- Rate-based metrics (`orders_per_min`, throughput windows) depend on wall-clock sampling, so they can diverge because replay timing rarely matches the original run.
- If `FAIL_RATE` injects randomness, the replayed inventory outcomes can diverge. To guarantee identical totals, set `FAIL_RATE=0` or seed the randomness deterministically before rerunning.
