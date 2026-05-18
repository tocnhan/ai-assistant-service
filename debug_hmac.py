import hmac, hashlib
from src.core.config import settings

body = '{"message": "test"}'
ts = '1779095898'
sig = hmac.new(settings.HMAC_SECRET.encode(), f'{ts}{body}'.encode(), hashlib.sha256).hexdigest()
print('HMAC_SECRET:', repr(settings.HMAC_SECRET))
print('Input     :', repr(f'{ts}{body}'))
print('Signature :', sig)