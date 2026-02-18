import json
import sqlite3
import time
import uuid
import logging
import os
import pika
from flask import Flask, request, jsonify

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

app = Flask(__name__)
RABBIT_HOST = os.environ.get("RABBITMQ_HOST", "rabbitmq")
ORDERS_EXCHANGE = "orders"
ORDERS_ROUTING_KEY = "order.placed"
DB_PATH = "/data/orders.db"

os.makedirs("/data", exist_ok=True)

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS orders (
        order_id TEXT PRIMARY KEY,
        request_id TEXT,
        item TEXT,
        qty INTEGER,
        status TEXT,
        created_at REAL
    )
    """)
    conn.commit()
    conn.close()

init_db()

def publish_order(message: dict):
    params = pika.ConnectionParameters(host=RABBIT_HOST)
    conn = pika.BlockingConnection(params)
    ch = conn.channel()
    ch.exchange_declare(exchange=ORDERS_EXCHANGE, exchange_type='direct', durable=True)
    body = json.dumps(message)
    ch.basic_publish(
        exchange=ORDERS_EXCHANGE,
        routing_key=ORDERS_ROUTING_KEY,
        body=body,
        properties=pika.BasicProperties(delivery_mode=2, content_type='application/json')
    )
    conn.close()


@app.route('/order', methods=['POST'])
def create_order():
    data = request.get_json(force=True)
    item = data.get('item', '').lower()
    qty = int(data.get('qty', 1))

    order_id = f"ORD-{uuid.uuid4().hex[:12].upper()}"
    request_id = str(uuid.uuid4())
    created = time.time()

    order = {
        'order_id': order_id,
        'request_id': request_id,
        'item': item,
        'qty': qty,
        'status': 'placed',
        'created_at': created
    }

    
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("INSERT INTO orders (order_id, request_id, item, qty, status, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (order_id, request_id, item, qty, 'placed', created))
    conn.commit()
    conn.close()

    publish_order(order)
    logger.info(f"Published OrderPlaced order_id={order_id} item={item} qty={qty}")

    return jsonify(order), 201


@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'healthy', 'service': 'async-order-service'}), 200


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
