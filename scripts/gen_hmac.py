import hmac, hashlib, time, json, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.core.config import settings

with open("scripts/test_body.json", "r") as f:
    body = f.read().strip()

timestamp = str(int(time.time()))
signature = hmac.new(
    settings.HMAC_SECRET.encode(),
    f"{timestamp}{body}".encode(),
    hashlib.sha256
).hexdigest()

print(f"Timestamp : {timestamp}")
print(f"Signature : {signature}")
print(f"Body      : {body}")