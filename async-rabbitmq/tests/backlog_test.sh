#!/bin/bash
# Backlog test: Stop inventory, publish orders, restart, show drain

echo "============================================================"
echo "  BACKLOG TEST: Kill InventoryService for 60s, publish orders"
echo "============================================================"

COMPOSE_DIR="/Users/aravindreddy/IdeaProjects/273-Week2-Assignment/cmpe273-comm-models-lab/async-rabbitmq"
cd "$COMPOSE_DIR"

echo ""
echo "[1] Starting fresh stack..."
docker-compose down 2>/dev/null
docker-compose up -d --build
sleep 10
echo "✓ Stack started"

echo ""
echo "[2] Stopping InventoryService..."
docker-compose stop inventory-service
sleep 2
echo "✓ InventoryService stopped"

echo ""
echo "[3] Publishing 200 orders while inventory is down (backlog accumulates)..."
python3 tests/publish_orders.py 200 > /tmp/publish_orders.log 2>&1 &
PUB_PID=$!
wait $PUB_PID
echo "✓ 200 orders published"

echo ""
echo "[4] Checking queue depth via RabbitMQ management API..."
BEFORE=$(docker-compose exec -T rabbitmq rabbitmqctl list_queues name messages | grep orders.reserve | awk '{print $2}')
echo "Queue depth before restart: $BEFORE messages"

echo ""
echo "[5] Waiting 60s..."
sleep 60

echo ""
echo "[6] Starting InventoryService (backlog drain begins)..."
docker-compose start inventory-service
sleep 5

echo ""
echo "[7] Monitoring backlog drain for 30s..."
for i in {1..6}; do
  DEPTH=$(docker-compose exec -T rabbitmq rabbitmqctl list_queues name messages | grep orders.reserve | awk '{print $2}')
  echo "  [$((i*5))s] Queue depth: $DEPTH messages"
  sleep 5
done

AFTER=$(docker-compose exec -T rabbitmq rabbitmqctl list_queues name messages | grep orders.reserve | awk '{print $2}' || echo "0")
echo ""
echo "Queue depth after drain: ${AFTER:-0} messages"

echo ""
echo "[8] Checking InventoryService logs for processing..."
echo "Last 20 log lines from inventory-service:"
docker-compose logs --no-color --tail=20 inventory-service | tail -20

echo ""
echo "============================================================"
echo "  TEST COMPLETE"
echo "============================================================"
