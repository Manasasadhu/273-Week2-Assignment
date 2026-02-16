"""
Notification Service — Simulated notification sender.

Endpoints:
  POST /send    — Log a notification (simulated)
  GET  /health  — Health check
"""

import logging
from flask import Flask, request, jsonify

app = Flask(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)


@app.route("/send", methods=["POST"])
def send():
    data = request.get_json(force=True)
    order_id = data.get("order_id", "unknown")
    request_id = data.get("request_id", "unknown")
    message = data.get("message", "")

    logger.info(f"[{request_id}] 📧 NOTIFICATION for order={order_id}: {message}")

    return jsonify({
        "status": "sent",
        "order_id": order_id,
        "request_id": request_id
    }), 200


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "healthy", "service": "notification-service"}), 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5002)
