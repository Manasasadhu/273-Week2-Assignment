import time
import requests
import sys

ORDER_URL = 'http://localhost:8001/order'
N = int(sys.argv[1]) if len(sys.argv) > 1 else 100
ITEMS = ['burger', 'pizza', 'sushi', 'taco', 'salad']

for i in range(N):
    item = ITEMS[i % len(ITEMS)]
    try:
        resp = requests.post(ORDER_URL, json={'item': item, 'qty': 1}, timeout=10)
        print(f"{i+1}: {resp.status_code} {resp.json().get('order_id') if resp.status_code==201 else resp.text}")
    except Exception as e:
        print(f"{i+1}: ERROR {e}")
    time.sleep(0.05)
