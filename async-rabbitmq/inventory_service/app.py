import json
import sqlite3
import threading
import time
import logging
import os
import random
import pika
from flask import Flask, request, jsonify

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

app = Flask(__name__)
RABBIT_HOST = os.environ.get('RABBITMQ_HOST', 'rabbitmq')
ORDERS_EXCHANGE = 'orders'
ORDERS_ROUTING_KEY = 'order.placed'
ORDERS_QUEUE = 'orders.reserve'
DLX_EXCHANGE = 'orders.dlx'
INVENTORY_EXCHANGE = 'inventory'
INVENTORY_ROUTING_RESERVED = 'inventory.reserved'
INVENTORY_ROUTING_FAILED = 'inventory.failed'
DB_PATH = os.environ.get('INVENTORY_DB', '/data/inventory.db')

os.makedirs('/data', exist_ok=True)

# fault injection
fault = {
    'delay': 0.0,
    'failure_rate': 0.0
}

# initialize DB
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute('''
    CREATE TABLE IF NOT EXISTS inventory (
        item TEXT PRIMARY KEY,
        qty INTEGER
    )
    ''')
    cur.execute('''
    CREATE TABLE IF NOT EXISTS processed_orders (
        order_id TEXT PRIMARY KEY,
        reservation_id TEXT,
        status TEXT,
        created_at REAL
    )
    ''')
    # Seed inventory if empty
    cur.execute('SELECT COUNT(1) FROM inventory')
    if cur.fetchone()[0] == 0:
        items = [('burger', 100), ('pizza', 100), ('sushi', 100), ('taco', 100), ('salad', 100)]
        cur.executemany('INSERT INTO inventory (item, qty) VALUES (?, ?)', items)
    conn.commit()
    conn.close()

init_db()

# Rabbit connection & consumer

def start_consumer():
    max_retries = 10
    retry_delay = 2
    for attempt in range(max_retries):
        try:
            logger.info(f"Attempting to connect to RabbitMQ (attempt {attempt + 1}/{max_retries})...")
            params = pika.ConnectionParameters(host=RABBIT_HOST, connection_attempts=3, retry_delay=2)
            conn = pika.BlockingConnection(params)
            ch = conn.channel()
            logger.info("Connected to RabbitMQ successfully!")
            break
        except Exception as e:
            logger.warning(f"Connection failed: {e}. Retrying in {retry_delay}s...")
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
            else:
                logger.error("Failed to connect to RabbitMQ after max retries")
                return

    # exchanges & queues
    ch.exchange_declare(exchange=ORDERS_EXCHANGE, exchange_type='direct', durable=True)
    ch.exchange_declare(exchange=DLX_EXCHANGE, exchange_type='direct', durable=True)
    ch.exchange_declare(exchange=INVENTORY_EXCHANGE, exchange_type='direct', durable=True)

    args = {
        'x-dead-letter-exchange': DLX_EXCHANGE
    }
    ch.queue_declare(queue=ORDERS_QUEUE, durable=True, arguments=args)
    ch.queue_bind(queue=ORDERS_QUEUE, exchange=ORDERS_EXCHANGE, routing_key=ORDERS_ROUTING_KEY)
    
    # Create DLQ queue and bind to DLX exchange
    ch.queue_declare(queue='orders.dlq', durable=True)
    ch.queue_bind(queue='orders.dlq', exchange=DLX_EXCHANGE, routing_key=ORDERS_ROUTING_KEY)

    def callback(ch, method, properties, body):
        try:
            payload = json.loads(body)
        except Exception:
            logger.error('Malformed message — rejecting to DLQ')
            ch.basic_reject(delivery_tag=method.delivery_tag, requeue=False)
            return

        order_id = payload.get('order_id')
        request_id = payload.get('request_id')
        item = payload.get('item')
        qty = int(payload.get('qty', 1))

        if not order_id or not item:
            logger.error('Invalid payload fields — rejecting to DLQ')
            ch.basic_reject(delivery_tag=method.delivery_tag, requeue=False)
            return

        logger.info(f"Received OrderPlaced order_id={order_id} item={item} qty={qty}")

        # fault injection
        if fault['delay'] > 0:
            logger.warning(f"Injecting delay {fault['delay']}s")
            time.sleep(fault['delay'])
        if fault['failure_rate'] > 0 and random.random() < fault['failure_rate']:
            logger.error('Injected random failure — NACK with requeue=True')
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)
            return

        # idempotency check
        conn_db = sqlite3.connect(DB_PATH)
        cur = conn_db.cursor()
        cur.execute('SELECT order_id FROM processed_orders WHERE order_id = ?', (order_id,))
        if cur.fetchone():
            logger.info(f"Duplicate OrderPlaced detected order_id={order_id}, acking and skipping")
            conn_db.close()
            ch.basic_ack(delivery_tag=method.delivery_tag)
            return

        # check inventory
        cur.execute('SELECT qty FROM inventory WHERE item = ?', (item,))
        row = cur.fetchone()
        if not row:
            logger.warning(f"Item not found: {item}")
            # record failed
            cur.execute('INSERT INTO processed_orders (order_id, reservation_id, status, created_at) VALUES (?, ?, ?, ?)',
                        (order_id, None, 'failed_item_not_found', time.time()))
            conn_db.commit()
            conn_db.close()
            publish_inventory_failed(order_id, 'item_not_found', request_id)
            ch.basic_ack(delivery_tag=method.delivery_tag)
            return

        available = row[0]
        if available < qty:
            logger.warning(f"Insufficient stock for {item}: have {available}, need {qty}")
            cur.execute('INSERT INTO processed_orders (order_id, reservation_id, status, created_at) VALUES (?, ?, ?, ?)',
                        (order_id, None, 'failed_insufficient', time.time()))
            conn_db.commit()
            conn_db.close()
            publish_inventory_failed(order_id, 'insufficient_stock', request_id)
            ch.basic_ack(delivery_tag=method.delivery_tag)
            return

        # reserve
        new_qty = available - qty
        cur.execute('UPDATE inventory SET qty = ? WHERE item = ?', (new_qty, item))
        reservation_id = f"RES-{order_id}"
        cur.execute('INSERT INTO processed_orders (order_id, reservation_id, status, created_at) VALUES (?, ?, ?, ?)',
                    (order_id, reservation_id, 'reserved', time.time()))
        conn_db.commit()
        conn_db.close()

        logger.info(f"Reserved {qty}x {item} for order_id={order_id}. Remaining={new_qty}")
        publish_inventory_reserved(order_id, reservation_id, item, qty, new_qty, request_id)

        ch.basic_ack(delivery_tag=method.delivery_tag)

    ch.basic_qos(prefetch_count=1)
    ch.basic_consume(queue=ORDERS_QUEUE, on_message_callback=callback)
    logger.info('InventoryService consumer started, waiting for messages...')
    try:
        ch.start_consuming()
    except KeyboardInterrupt:
        ch.stop_consuming()
    conn.close()


# publishers
def publish_inventory_reserved(order_id, reservation_id, item, qty, remaining, request_id):
    params = pika.ConnectionParameters(host=RABBIT_HOST)
    conn = pika.BlockingConnection(params)
    ch = conn.channel()
    ch.exchange_declare(exchange=INVENTORY_EXCHANGE, exchange_type='direct', durable=True)
    payload = {
        'order_id': order_id,
        'reservation_id': reservation_id,
        'item': item,
        'qty': qty,
        'remaining': remaining,
        'request_id': request_id,
        'created_at': time.time()
    }
    ch.basic_publish(exchange=INVENTORY_EXCHANGE, routing_key=INVENTORY_ROUTING_RESERVED,
                     body=json.dumps(payload), properties=pika.BasicProperties(delivery_mode=2, content_type='application/json'))
    conn.close()


def publish_inventory_failed(order_id, reason, request_id):
    params = pika.ConnectionParameters(host=RABBIT_HOST)
    conn = pika.BlockingConnection(params)
    ch = conn.channel()
    ch.exchange_declare(exchange=INVENTORY_EXCHANGE, exchange_type='direct', durable=True)
    payload = {
        'order_id': order_id,
        'reason': reason,
        'request_id': request_id,
        'created_at': time.time()
    }
    ch.basic_publish(exchange=INVENTORY_EXCHANGE, routing_key=INVENTORY_ROUTING_FAILED,
                     body=json.dumps(payload), properties=pika.BasicProperties(delivery_mode=2, content_type='application/json'))
    conn.close()


# Flask endpoints for health and runtime configure
@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'healthy', 'service': 'async-inventory-service'}), 200


@app.route('/configure', methods=['POST'])
def configure():
    data = request.get_json(force=True)
    if 'delay' in data:
        fault['delay'] = float(data['delay'])
    if 'failure_rate' in data:
        fault['failure_rate'] = float(data['failure_rate'])
    logger.info(f"Fault config updated: {fault}")
    return jsonify({'status': 'configured', 'config': fault}), 200


if __name__ == '__main__':
    # run consumer in separate thread
    t = threading.Thread(target=start_consumer, daemon=True)
    t.start()
    app.run(host='0.0.0.0', port=5003)
