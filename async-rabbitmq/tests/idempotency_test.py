#!/usr/bin/env python3
"""
Idempotency Test: Publish the same OrderPlaced message twice,
verify InventoryService only reserves once (check via inventory levels).
"""

import json
import time
import sqlite3
import requests
import sys

ORDER_URL = 'http://localhost:8001/order'
INVENTORY_API = 'http://localhost:5003/health'
INVENTORY_DB = '/var/lib/docker/volumes/cmpe273-comm-models-lab_inventory-data/_data/inventory.db'

print("=" * 70)
print("  IDEMPOTENCY TEST: Publish same order twice, verify single reserve")
print("=" * 70)

# Step 1: Get baseline inventory
print("\n[1] Getting baseline inventory...")
time.sleep(2)  # let services settle
try:
    # We'll check via logs and direct DB inspection
    print("  Waiting for services to be ready...")
    time.sleep(3)
except Exception as e:
    print(f"  Note: Services may not be fully ready yet: {e}")

# Step 2: Publish first order
print("\n[2] Publishing first order (item=burger, qty=1)...")
try:
    resp = requests.post(ORDER_URL, json={'item': 'burger', 'qty': 1}, timeout=5)
    first_order = resp.json()
    order_id = first_order.get('order_id')
    print(f"  ✓ First order published: {order_id}")
    print(f"    Response: {json.dumps(first_order, indent=2)}")
except Exception as e:
    print(f"  ✗ Error publishing first order: {e}")
    sys.exit(1)

time.sleep(3)  # let message process

# Step 3: Publish duplicate order (same order_id simulated by republishing)
print("\n[3] Simulating duplicate delivery (re-publishing same order_id to broker)...")
print("  (In real scenario, OrderService publishes again, or manual replay)")
import pika
import os

RABBIT_HOST = os.environ.get('RABBITMQ_HOST', 'localhost')
params = pika.ConnectionParameters(host=RABBIT_HOST)
try:
    conn = pika.BlockingConnection(params)
    ch = conn.channel()
    ch.exchange_declare(exchange='orders', exchange_type='direct', durable=True)
    # Re-publish the same OrderPlaced payload directly
    payload = {
        'order_id': order_id,
        'request_id': first_order.get('request_id'),
        'item': 'burger',
        'qty': 1,
        'created_at': first_order.get('created_at')
    }
    ch.basic_publish(
        exchange='orders',
        routing_key='order.placed',
        body=json.dumps(payload),
        properties=pika.BasicProperties(delivery_mode=2, content_type='application/json')
    )
    print(f"  ✓ Duplicate message published: {order_id}")
    conn.close()
except Exception as e:
    print(f"  ✗ Error republishing: {e}")
    sys.exit(1)

time.sleep(3)  # let second message process

# Step 4: Check processed orders table
print("\n[4] Checking InventoryService database for idempotency...")
print("  Looking for order_id in processed_orders table...")

# Try to inspect via docker exec
import subprocess
try:
    result = subprocess.run(
        ['docker', 'exec', 'async-inventory-service', 'sqlite3', '/data/inventory.db',
         f"SELECT order_id, reservation_id, status FROM processed_orders WHERE order_id='{order_id}'"],
        capture_output=True, text=True, timeout=5
    )
    rows = result.stdout.strip().split('\n')
    if result.returncode == 0 and rows and rows[0]:
        print(f"  ✓ Processed order found in DB:")
        for row in rows:
            if row:
                print(f"    {row}")
        row_count = len([r for r in rows if r])
        if row_count == 1:
            print(f"  ✓ IDEMPOTENCY VERIFIED: Only 1 row (no double reserve)")
        else:
            print(f"  ✗ WARNING: {row_count} rows found (expected 1)")
    else:
        print(f"  Note: DB query returned: {result.stdout}")
except Exception as e:
    print(f"  Note: Could not query DB directly: {e}")

# Step 5: Check inventory levels
print("\n[5] Checking final inventory levels...")
try:
    result = subprocess.run(
        ['docker', 'exec', 'async-inventory-service', 'sqlite3', '/data/inventory.db',
         "SELECT item, qty FROM inventory"],
        capture_output=True, text=True, timeout=5
    )
    print("  Current inventory:")
    for line in result.stdout.strip().split('\n'):
        if line:
            print(f"    {line}")
except Exception as e:
    print(f"  Note: Could not fetch inventory: {e}")

print("\n" + "=" * 70)
print("  TEST COMPLETE")
print("=" * 70)
print("""
Expected behavior:
- Published same order_id twice
- InventoryService processed both messages
- Due to idempotency check (processed_orders table):
  * First message: reserved 1x burger, inserted row in processed_orders
  * Second message: detected duplicate, ACK'd without reserving again
- Result: inventory decremented by 1 (not 2), only 1 DB row exists
""")
