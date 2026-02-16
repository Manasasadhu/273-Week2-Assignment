"""
Inventory Service — Manages in-memory food inventory and reservations.

Endpoints:
  POST /reserve     — Reserve inventory for an order
  POST /configure   — Runtime failure injection switch
  GET  /health      — Health check
"""

import time
import random
import logging
from flask import Flask, request, jsonify

app = Flask(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

# ── In-memory inventory ──────────────────────────────────────────────
inventory = {
    "burger": 100,
    "pizza": 100,
    "sushi": 100,
    "taco": 100,
    "salad": 100,
}

# Track reservations to avoid double-processing
reservations = {}

# ── Runtime failure injection config ─────────────────────────────────
fault_config = {
    "delay": 0.0,       # seconds to sleep before processing
    "failure_rate": 0.0  # probability of returning 500 (0.0 – 1.0)
}


@app.route("/reserve", methods=["POST"])
def reserve():
    data = request.get_json(force=True)
    order_id = data.get("order_id", "unknown")
    request_id = data.get("request_id", "unknown")
    item = data.get("item", "").lower()
    qty = data.get("qty", 1)

    logger.info(f"[{request_id}] Reserve request: order={order_id}, item={item}, qty={qty}")

    # ── Fault injection ──────────────────────────────────────────
    if fault_config["delay"] > 0:
        logger.warning(f"[{request_id}] Injecting {fault_config['delay']}s delay")
        time.sleep(fault_config["delay"])

    if fault_config["failure_rate"] > 0 and random.random() < fault_config["failure_rate"]:
        logger.error(f"[{request_id}] Injected failure for order={order_id}")
        return jsonify({"error": "Injected failure", "request_id": request_id}), 500

    # ── Business logic ───────────────────────────────────────────
    if item not in inventory:
        logger.warning(f"[{request_id}] Item not found: {item}")
        return jsonify({"error": f"Item '{item}' not found", "request_id": request_id}), 404

    if inventory[item] < qty:
        logger.warning(f"[{request_id}] Insufficient stock for {item}: have {inventory[item]}, need {qty}")
        return jsonify({
            "error": "Insufficient inventory",
            "item": item,
            "available": inventory[item],
            "request_id": request_id
        }), 409

    inventory[item] -= qty
    reservation_id = f"RES-{order_id}"
    reservations[reservation_id] = {"order_id": order_id, "item": item, "qty": qty}

    logger.info(f"[{request_id}] Reserved {qty}x {item}. Remaining: {inventory[item]}")

    return jsonify({
        "status": "reserved",
        "reservation_id": reservation_id,
        "item": item,
        "qty": qty,
        "remaining": inventory[item],
        "request_id": request_id
    }), 200


@app.route("/configure", methods=["POST"])
def configure():
    """Runtime switch for failure injection — no container restart needed."""
    data = request.get_json(force=True)

    if "delay" in data:
        fault_config["delay"] = float(data["delay"])
    if "failure_rate" in data:
        fault_config["failure_rate"] = float(data["failure_rate"])

    logger.info(f"Fault config updated: {fault_config}")
    return jsonify({"status": "configured", "config": fault_config}), 200


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "healthy", "service": "inventory-service"}), 200


@app.route("/inventory", methods=["GET"])
def get_inventory():
    """Utility endpoint to inspect current inventory levels."""
    return jsonify(inventory), 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001)
