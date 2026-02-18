# broker/connection.py
import os
import time
import pika


def _rabbitmq_url() -> str:
    url = os.getenv("RABBITMQ_URL")
    if url:
        return url

    host = os.getenv("RABBITMQ_HOST", "rabbitmq")
    port = int(os.getenv("RABBITMQ_PORT", "5672"))
    user = os.getenv("RABBITMQ_USER", "guest")
    pw = os.getenv("RABBITMQ_PASS", "guest")
    vhost = os.getenv("RABBITMQ_VHOST", "/")

    vhost_enc = vhost.replace("/", "%2F") if vhost == "/" else vhost
    return f"amqp://{user}:{pw}@{host}:{port}/{vhost_enc}"


def connect_with_retry(max_attempts: int = 30, base_sleep_s: float = 1.0) -> pika.BlockingConnection:
    """
    Connect to RabbitMQ with simple exponential backoff retry.
    Suitable for docker-compose startup ordering.
    """
    params = pika.URLParameters(_rabbitmq_url())
    params.heartbeat = int(os.getenv("RABBITMQ_HEARTBEAT", "60"))
    params.blocked_connection_timeout = int(os.getenv("RABBITMQ_BLOCKED_TIMEOUT", "60"))

    attempt = 0
    while True:
        attempt += 1
        try:
            return pika.BlockingConnection(params)
        except Exception as e:
            if attempt >= max_attempts:
                raise RuntimeError(f"Failed to connect to RabbitMQ after {attempt} attempts: {e}") from e
            sleep_s = min(base_sleep_s * (2 ** (attempt - 1)), 10.0)
            time.sleep(sleep_s)