import os
import json
import time
import random

from confluent_kafka import Producer

print("Service starting...")
print("BOOTSTRAP_SERVERS =", os.getenv("BOOTSTRAP_SERVERS"))

bootstrap_servers = os.getenv("BOOTSTRAP_SERVERS")
order_topic = os.getenv("ORDER_TOPIC")
item_count = int(os.getenv("ITEM_COUNT", "50"))
max_qty = int(os.getenv("MAX_QTY", "5"))
mode = os.getenv("MODE", "idle").lower()
total_events = int(os.getenv("TOTAL_EVENTS", "10000"))
print_every = int(os.getenv("PRINT_EVERY", "1000"))
sleep_ms = int(os.getenv("SLEEP_MS", "0"))

producer = Producer({
    "bootstrap.servers": bootstrap_servers
})

def make_payload(i):
    order_str = f"order-{i}"
    item_str = f"item-{random.randint(1,item_count)}"
    qty_val = random.randint(1,max_qty)
    payload = {'order_id': order_str, 'item_id': item_str, 'qty': qty_val, 'ts': time.time()}
    return payload

def produce_one(i):
    payload = make_payload(i)
    key_bytes = payload["order_id"].encode("utf-8")
    payload_bytes = json.dumps(payload).encode("utf-8")
    producer.produce(order_topic, key=key_bytes, value=payload_bytes)
    producer.poll(0)

def produce_burst(n):
    for i in range(1, n+1): 
        if i%print_every==0: print(f"PRODUCED EVENTS: {i}/{n}")
        produce_one(i)

if mode=="idle": print("MODE=idle (no events)")
elif mode=="once": 
    print("MODE=once")
    produce_one(1)
elif mode=="burst":
    print("MODE=burst")
    produce_burst(total_events)
else:
    print("Unknown mode defaulting to mode=idle")

producer.flush()
sleep_sec=max(sleep_ms, 1000)/1000
while True: time.sleep(sleep_sec)