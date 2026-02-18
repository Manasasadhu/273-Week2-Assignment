# Analytics Consumer

This service consumes both `order-events` and `inventory-events` and exposes rolling metrics over HTTP.

## Startup guard

`entrypoint.sh` runs `wait_for_topics.py` before the Flask app starts so we only join the Kafka group once the required topics exist. You can tune the wait logic with:

- `TOPIC_WAIT_TIMEOUT_SEC` (default 300) – max seconds to wait before failing.
- `TOPIC_WAIT_INTERVAL_SEC` (default 2) – delay between checks.
- `TOPIC_WAIT_SKIP=1` – bypass the wait entirely (mainly for local debugging).

## Static group membership

Set `GROUP_INSTANCE_ID` to a non-empty value (e.g. `analytics-1`) to opt into static membership. This prevents unnecessary rebalances if the container restarts quickly. Leave the variable empty to fall back to dynamic membership.

All relevant variables are declared in `analytics.env` so `docker compose` picks them up automatically.
