# Common Utilities

Shared utilities used across all three communication model implementations.

## `ids.py`

Provides UUID-based ID generators:

- `generate_order_id()` — Returns a unique order ID (e.g., `ORD-A1B2C3D4E5F6`)
- `generate_request_id()` — Returns a UUID string for distributed tracing across services
