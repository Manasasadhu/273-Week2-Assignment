# Streaming Kafka Stack

This package provisions a full Kafka playground with three custom services:

- **producer_order** – bursts configurable order events into Kafka.
- **inventory_consumer** – consumes orders, simulates inventory updates, and emits inventory events.
- **analytics_consumer** – consumes both topics, maintains rolling metrics, and exposes them via HTTP on port 8080.

Everything runs through `docker compose`, including Kafka and ZooKeeper, so nothing needs to be installed locally beyond Docker.

## Prerequisites

- Docker Desktop (or compatible Docker Engine) with Compose V2.
- At least 4 vCPUs / 4 GB RAM available for the containers.

## How to run

```bash
cd streaming-kafka
docker compose up --build
```

The first startup will:

1. Launch ZooKeeper and Kafka.
2. Run the `kafka-init` one-shot container to create the `order-events` and `inventory-events` topics.
3. Build and start the producer, inventory consumer, and analytics consumer containers in that order.

You can follow service logs with `docker compose logs -f <service>`. Stop everything with `Ctrl+C` or `docker compose down`.

## Environment configuration

Each service reads its own `.env` file that is already referenced by `docker-compose.yml`:

- `producer_order/producer.env`
  - `BOOTSTRAP_SERVERS` – Kafka bootstrap string (default `kafka:9092`).
  - `ORDER_TOPIC` – topic receiving new orders. Created by `kafka-init`.
  - `MODE`, `TOTAL_EVENTS`, `SLEEP_MS` etc. let you tune event volume and pacing.
- `inventory_consumer/inventory.env`
  - `GROUP_ID` / `AUTO_OFFSET_RESET` control consumer group behavior.
  - `FAIL_RATE` and `THROTTLE_MS` simulate downstream failures or slowness.
  - `INVENTORY_TOPIC` is where derived inventory events are written.
- `analytics_consumer/analytics.env`
  - `GROUP_INSTANCE_ID` enables static group membership for steadier assignments.
  - `WINDOW_SEC`, `REPORT_INTERVAL_SEC` adjust rolling-metric windows.
  - `HTTP_HOST`/`HTTP_PORT` define the Flask metrics endpoint (`http://localhost:8080/metrics`).
  - `TOPIC_WAIT_*` guard the app so it only starts once topics exist; set `TOPIC_WAIT_SKIP=1` to bypass during local debugging.

Update these files before (re)starting the stack; Compose automatically injects them.

## Data flow

1. **producer_order** publishes JSON payloads into the `order-events` topic. Orders contain item IDs, quantities, and status metadata.
2. **inventory_consumer** subscribes to `order-events`, applies simple business rules (e.g., reserve/fulfill), and emits derived events to `inventory-events` while also acknowledging the original orders.
3. **analytics_consumer** listens to both `order-events` and `inventory-events`, keeps rolling aggregates (window controlled by `WINDOW_SEC`), and surfaces the metrics through its HTTP API. The container waits for both topics before joining the consumer group to avoid rebalance churn.

As a result, you can stress the pipeline by adjusting the producer rate and observe how it ripples through inventory handling and analytics metrics.

## Inspecting metrics

After the stack is up, hit the analytics endpoint:

```bash
curl http://localhost:8080/metrics
```

You should see JSON counters such as processed order count, throughput, and inventory success/failure rates updating every `REPORT_INTERVAL_SEC` seconds.

## Cleaning up

To stop and remove containers, networks, and cached topics:

```bash
cd streaming-kafka
docker compose down -v
```

Use `docker system prune` if you also want to remove dangling images or volumes.
