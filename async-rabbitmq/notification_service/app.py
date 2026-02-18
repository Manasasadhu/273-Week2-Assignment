import json
import threading
import time
import logging
import os
import pika
from flask import Flask, jsonify

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

app = Flask(__name__)
RABBIT_HOST = os.environ.get('RABBITMQ_HOST', 'rabbitmq')
INVENTORY_EXCHANGE = 'inventory'
INVENTORY_ROUTING_RESERVED = 'inventory.reserved'
QUEUE_NAME = 'inventory.notify'


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
    ch.exchange_declare(exchange=INVENTORY_EXCHANGE, exchange_type='direct', durable=True)
    ch.queue_declare(queue=QUEUE_NAME, durable=True)
    ch.queue_bind(queue=QUEUE_NAME, exchange=INVENTORY_EXCHANGE, routing_key=INVENTORY_ROUTING_RESERVED)

    def callback(ch, method, properties, body):
        try:
            payload = json.loads(body)
        except Exception:
            logger.error('Malformed inventory message — acking to remove')
            ch.basic_ack(delivery_tag=method.delivery_tag)
            return

        order_id = payload.get('order_id')
        reservation_id = payload.get('reservation_id')
        item = payload.get('item')
        qty = payload.get('qty')
        logger.info(f"📧 Notification: order_id={order_id} reserved {qty}x {item} (reservation={reservation_id})")
        ch.basic_ack(delivery_tag=method.delivery_tag)

    ch.basic_qos(prefetch_count=1)
    ch.basic_consume(queue=QUEUE_NAME, on_message_callback=callback)
    logger.info('NotificationService consumer started, waiting for messages...')
    try:
        ch.start_consuming()
    except KeyboardInterrupt:
        ch.stop_consuming()
    conn.close()


@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'healthy', 'service': 'async-notification-service'}), 200


if __name__ == '__main__':
    t = threading.Thread(target=start_consumer, daemon=True)
    t.start()
    app.run(host='0.0.0.0', port=5000)
