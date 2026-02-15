import os
import time

print("Service starting...")
print("BOOTSTRAP_SERVERS =", os.getenv("BOOTSTRAP_SERVERS"))

while True:
    time.sleep(5)
    print("still alive")
