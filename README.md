## Part B Testing:

Start all services using docker compose - 
<img width="1158" height="893" alt="image" src="https://github.com/user-attachments/assets/af4bb058-b280-43c0-981e-d70d1994d9dc" />

Publis 5 orders for testing using a python script 
<img width="816" height="255" alt="image" src="https://github.com/user-attachments/assets/f84d5c22-6050-4b7f-868a-09e841776456" />

Checking order-service logs - 
<img width="1868" height="611" alt="image" src="https://github.com/user-attachments/assets/c6d61403-7a47-4bfa-986c-56fee6f5052d" />

Checking inventory-service logs 
<img width="1858" height="133" alt="image" src="https://github.com/user-attachments/assets/4c78376c-4798-4eec-9dcb-265b99ab1fb5" />

Checking notification Service logs (with all the 5 published orders0
<img width="1433" height="153" alt="image" src="https://github.com/user-attachments/assets/f9b79fbf-8aeb-44df-8953-415bdc771f11" />

### Verify Backlog and recovery (After 60 seconds)
Kill inventory-service and kept publishing around 150 orders 
<img width="1867" height="584" alt="image" src="https://github.com/user-attachments/assets/1b6ea3de-8567-4d15-b58a-6b153b539342" />

