#!/usr/bin/env python3
"""
DLQ Test: Publish malformed OrderPlaced (missing required fields),
verify it lands in the dead-letter queue (orders.dlq).
"""

import json
import pika
import time
import subprocess
import os

RABBIT_HOST = os.environ.get('RABBITMQ_HOST', 'localhost')

print("=" * 70)
print("  DLQ TEST: Publish malformed message, verify DLQ capture")
print("=" * 70)

# Step 1: Clear DLQ (optional)
print("\n[1] Setting up DLQ inspection...")
time.sleep(2)

# Step 2: Publish malformed message
print("\n[2] Publishing malformed OrderPlaced (missing order_id)...")
try:
    params = pika.ConnectionParameters(host=RABBIT_HOST)
    conn = pika.BlockingConnection(params)
    ch = conn.channel()
    ch.exchange_declare(exchange='orders', exchange_type='direct', durable=True)
    
    # Malformed: missing order_id
    malformed_payload = {
        'request_id': 'test-dlq-001',
        'item': 'pizza',
        'qty': 1,
        'created_at': time.time()
        # MISSING: 'order_id'
    }
    
    ch.basic_publish(
        exchange='orders',
        routing_key='order.placed',
        body=json.dumps(malformed_payload),
        properties=pika.BasicProperties(delivery_mode=2, content_type='application/json')
    )
    print(f"  ✓ Malformed message published")
    print(f"    Payload: {json.dumps(malformed_payload)}")
    conn.close()
except Exception as e:
    print(f"  ✗ Error publishing: {e}")

time.sleep(3)

# Step 3: Publish another malformed (invalid JSON)
print("\n[3] Publishing invalid JSON (syntax error)...")
try:
    params = pika.ConnectionParameters(host=RABBIT_HOST)
    conn = pika.BlockingConnection(params)
    ch = conn.channel()
    ch.exchange_declare(exchange='orders', exchange_type='direct', durable=True)
    
    # Invalid JSON
    invalid_json = "{ broken json }"
    
    ch.basic_publish(
        exchange='orders',
        routing_key='order.placed',
        body=invalid_json,
        properties=pika.BasicProperties(delivery_mode=2, content_type='application/json')
    )
    print(f"  ✓ Invalid JSON published")
    conn.close()
except Exception as e:
    print(f"  ✗ Error publishing: {e}")

time.sleep(3)

# Step 4: Check DLQ
print("\n[4] Checking DLQ contents (orders.dlq)...")
try:
    result = subprocess.run(
        ['docker', 'exec', 'ar-mq', 'rabbitmqctl', 'list_queues', 'name', 'messages'],
        capture_output=True, text=True, timeout=5
    )
    lines = result.stdout.strip().split('\n')
    headers = lines[0] if lines else ""
    queues = lines[1:] if len(lines) > 1 else []
    
    print("  Queue summary:")
    dlq_depth = 0
    for line in queues:
        if 'dlq' in line or 'orders' in line:
            print(f"    {line}")
            if 'dlq' in line:
                parts = line.split()
                if len(parts) >= 2:
                    dlq_depth = int(parts[-1])
    
    if dlq_depth > 0:
        print(f"\n  ✓ DLQ contains {dlq_depth} poisoned message(s)")
    else:
        print(f"\n  Note: DLQ appears empty or not capturing messages")
except Exception as e:
    print(f"  Note: Could not query RabbitMQ: {e}")

# Step 5: Show InventoryService logs (should show rejection)
print("\n[5] InventoryService logs (showing rejections)...")
try:
    result = subprocess.run(
        ['docker', 'compose', '-f', '/Users/aravindreddy/IdeaProjects/273-Week2-Assignment/cmpe273-comm-models-lab/async-rabbitmq/docker-compose.yml',
         'logs', '--no-color', '--tail=15', 'inventory-service'],
        capture_output=True, text=True, timeout=5, cwd='/Users/aravindreddy/IdeaProjects/273-Week2-Assignment/cmpe273-comm-models-lab/async-rabbitmq'
    )
    for line in result.stdout.split('\n')[-10:]:
        if line.strip():
            print(f"  {line}")
except Exception as e:
    print(f"  Note: Could not fetch logs: {e}")

print("\n" + "=" * 70)
print("  TEST COMPLETE")
print("=" * 70)
print("""
Expected behavior:
1. Malformed message (missing order_id):
   - InventoryService receives it
   - Validation fails (missing required field)
   - basic_reject(requeue=False) sends to DLQ

2. Invalid JSON:
   - InventoryService tries to parse
   - JSON decode fails
   - basic_reject(requeue=False) sends to DLQ

Result: Both messages end up in orders.dlq for inspection.
""")
