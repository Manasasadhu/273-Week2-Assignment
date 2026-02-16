"""Shared ID generation utilities for the campus food ordering system."""

import uuid


def generate_order_id() -> str:
    """Generate a unique order ID."""
    return f"ORD-{uuid.uuid4().hex[:12].upper()}"


def generate_request_id() -> str:
    """Generate a unique request ID for distributed tracing."""
    return str(uuid.uuid4())
