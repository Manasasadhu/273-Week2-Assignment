## Part B Testing:

### Baseline testing of all services
Start all services using docker compose - 
<img width="1110" height="153" alt="image" src="https://github.com/user-attachments/assets/caf4af8d-05f1-4066-ac14-a00c3f064503" />

Publis 5 orders for testing using a python script 
<img width="1109" height="137" alt="image" src="https://github.com/user-attachments/assets/f5994a45-0bc5-4f18-b8ef-4d2073ba4375" />

Checking order-service logs - 
<img width="1868" height="611" alt="image" src="https://github.com/user-attachments/assets/c6d61403-7a47-4bfa-986c-56fee6f5052d" />

Checking inventory-service logs 
<img width="1858" height="133" alt="image" src="https://github.com/user-attachments/assets/4c78376c-4798-4eec-9dcb-265b99ab1fb5" />

Checking notification Service logs (with all the 5 published orders0
<img width="1433" height="153" alt="image" src="https://github.com/user-attachments/assets/f9b79fbf-8aeb-44df-8953-415bdc771f11" />

### Verify Backlog and recovery (After 60 seconds)
Kill inventory-service and kept publishing around 50 orders 
<img width="1662" height="981" alt="image" src="https://github.com/user-attachments/assets/b866a8a1-0175-46f0-ba1f-70449a3794f3" />

Backlog drain 
After the inventory-service was restarted, the queued 50 orders are processed by inventory service and queue is emptied as shown in below picture.
<img width="1689" height="314" alt="image" src="https://github.com/user-attachments/assets/0d912615-239f-4aac-ac37-f23ac06bb138" />

### Demonstrate idempotency (duplicate message handling)
Created an order 
<img width="687" height="403" alt="image" src="https://github.com/user-attachments/assets/5e44aa32-4256-43e1-a9e3-f4d32a761bf6" />

Checking the rows in DB against this order-id - 
<img width="1680" height="148" alt="image" src="https://github.com/user-attachments/assets/84458f47-c1f0-4b9d-8193-c47c8e565e8c" />

Re-published same order (with same id) again using RabbitMQ UI
<img width="1422" height="732" alt="image" src="https://github.com/user-attachments/assets/80b950a3-a21d-4d5f-b340-981b0b371003" />

Checking the rows in DB and inventory reserved against this order-id (after re-publishing the same order) - It still has only one row against the order id as it doe not double reserve the order in inventory.
<img width="1673" height="148" alt="image" src="https://github.com/user-attachments/assets/79547ae1-5880-4668-a3d3-806b85c14e69" />

### Test DLQ or poison message handling for a malformed event

Placing an order with a malformed request (the request has missing order_id)
<img width="1019" height="736" alt="image" src="https://github.com/user-attachments/assets/54406900-de06-45db-a71f-2015ee48ee2e" />

After placing a malformed order, the request is rejected and added to a Dead Letter Queue (DLQ) 
<img width="1166" height="169" alt="image" src="https://github.com/user-attachments/assets/4f8720e1-72f0-4a10-bd1b-f9862b94b139" />






