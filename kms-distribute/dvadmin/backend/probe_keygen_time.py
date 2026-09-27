import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'application.settings')
import django; django.setup()
from pqkds.real_crypto_with_fallback import RealKyberKEM, RealFalconSignature

kyber = RealKyberKEM(512)
falcon = RealFalconSignature(512)

times = []
for _ in range(20):
    t0 = time.time()
    kyber.keygen()
    falcon.keygen()
    times.append(time.time() - t0)

print(f"avg={sum(times)/len(times):.4f} min={min(times):.4f} max={max(times):.4f}")

