"""
Order Service — Orchestrator for the campus food ordering workflow.

Endpoints:
  POST /order   — Place a new food order (calls Inventory + Notification synchronously)
  GET  /health  — Health check
"""

import uuid
import time
import logging
import requests as http_client
from flask import Flask, request, jsonify

app = Flask(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

# ── Service URLs ─────────────────────────────────────────────────────
INVENTORY_URL = "http://inventory-service:5001"
NOTIFICATION_URL = "http://notification-service:5002"
DOWNSTREAM_TIMEOUT = 5  # seconds

# ── In-memory order store ────────────────────────────────────────────
orders = {}


@app.route("/order", methods=["POST"])
def create_order():
    data = request.get_json(force=True)
    item = data.get("item", "").lower()
    qty = data.get("qty", 1)

    # Generate IDs
    order_id = f"ORD-{uuid.uuid4().hex[:12].upper()}"
    request_id = str(uuid.uuid4())

    logger.info(f"[{request_id}] New order: id={order_id}, item={item}, qty={qty}")

    start_time = time.time()

    # ── Step 1: Reserve inventory (synchronous, blocking) ────────
    try:
        logger.info(f"[{request_id}] Calling InventoryService POST /reserve ...")
        inv_response = http_client.post(
            f"{INVENTORY_URL}/reserve",
            json={
                "order_id": order_id,
                "request_id": request_id,
                "item": item,
                "qty": qty
            },
            timeout=DOWNSTREAM_TIMEOUT
        )
    except http_client.exceptions.Timeout:
        elapsed = time.time() - start_time
        logger.error(f"[{request_id}] InventoryService TIMEOUT after {elapsed:.2f}s")
        orders[order_id] = {"status": "failed", "reason": "inventory_timeout"}
        return jsonify({
            "error": "Inventory service timed out",
            "order_id": order_id,
            "request_id": request_id,
            "elapsed_ms": round(elapsed * 1000, 2)
        }), 504
    except http_client.exceptions.ConnectionError:
        elapsed = time.time() - start_time
        logger.error(f"[{request_id}] InventoryService CONNECTION ERROR")
        orders[order_id] = {"status": "failed", "reason": "inventory_unavailable"}
        return jsonify({
            "error": "Inventory service unavailable",
            "order_id": order_id,
            "request_id": request_id,
            "elapsed_ms": round(elapsed * 1000, 2)
        }), 503

    if inv_response.status_code != 200:
        elapsed = time.time() - start_time
        logger.warning(f"[{request_id}] InventoryService returned {inv_response.status_code}")
        orders[order_id] = {"status": "failed", "reason": "inventory_error"}

        # Pass through 409 (insufficient stock) vs 500 (injected failure)
        status_code = 409 if inv_response.status_code == 409 else 503
        return jsonify({
            "error": "Inventory reservation failed",
            "order_id": order_id,
            "request_id": request_id,
            "inventory_response": inv_response.json(),
            "elapsed_ms": round(elapsed * 1000, 2)
        }), status_code

    inv_data = inv_response.json()
    logger.info(f"[{request_id}] Inventory reserved: {inv_data.get('reservation_id')}")

    # ── Step 2: Send notification (synchronous, blocking) ────────
    try:
        logger.info(f"[{request_id}] Calling NotificationService POST /send ...")
        notif_response = http_client.post(
            f"{NOTIFICATION_URL}/send",
            json={
                "order_id": order_id,
                "request_id": request_id,
                "message": f"Order {order_id} confirmed: {qty}x {item}"
            },
            timeout=DOWNSTREAM_TIMEOUT
        )
        logger.info(f"[{request_id}] Notification sent: {notif_response.status_code}")
    except Exception as e:
        # Notification failure is non-critical — log but don't fail the order
        logger.warning(f"[{request_id}] Notification failed (non-critical): {e}")

    elapsed = time.time() - start_time

    # ── Store and return order ───────────────────────────────────
    order = {
        "order_id": order_id,
        "request_id": request_id,
        "item": item,
        "qty": qty,
        "status": "confirmed",
        "reservation_id": inv_data.get("reservation_id"),
        "elapsed_ms": round(elapsed * 1000, 2)
    }
    orders[order_id] = order

    logger.info(f"[{request_id}] Order confirmed in {elapsed * 1000:.2f}ms")

    return jsonify(order), 201


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "healthy", "service": "order-service"}), 200


@app.route("/orders", methods=["GET"])
def list_orders():
    """Utility endpoint to inspect all orders."""
    return jsonify(list(orders.values())), 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
