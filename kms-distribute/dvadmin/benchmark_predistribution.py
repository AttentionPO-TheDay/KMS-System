# -*- coding: utf-8 -*-
"""
PQKDS - Lattice-Based Key Pre-Distribution Performance Benchmark
Tests both Kyber KEM and Falcon lattice encryption schemes.
Target: >= 50 keys/sec per scheme.
"""
import os, sys, time, statistics, json, base64, hashlib, logging
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'application.settings')
import django; django.setup()

from Crypto.Cipher import AES
from pqkds.crypto_utils import KyberCrypto


def banner(text):
    print(f"\n{'='*60}\n  {text}\n{'='*60}")


# ================================================================
#  Kyber KEM Benchmark
# ================================================================
def bench_kyber(variant, num_keys, warmup=5):
    banner(f"Kyber-{variant} KEM Pre-Distribution ({num_keys} keys)")
    kyber = KyberCrypto(variant)
    pk, sk = kyber.generate_keypair()
    print(f"  PK: {len(pk)} bytes, SK: {len(sk)} bytes")

    # warmup
    for _ in range(warmup):
        aes_key = os.urandom(32)
        ct, ss = kyber.encrypt(pk)
        cipher = AES.new(ss[:32], AES.MODE_GCM)
        enc_key, tag = cipher.encrypt_and_digest(aes_key)
        ss2 = kyber.decrypt(ct, sk)
        dec = AES.new(ss2[:32], AES.MODE_GCM, nonce=cipher.nonce)
        dec.decrypt_and_verify(enc_key, tag)

    latencies = []
    t_start = time.perf_counter()
    for _ in range(num_keys):
        t0 = time.perf_counter()
        aes_key = os.urandom(32)
        ct, ss = kyber.encrypt(pk)
        cipher = AES.new(ss[:32], AES.MODE_GCM)
        enc_key, tag = cipher.encrypt_and_digest(aes_key)
        nonce = cipher.nonce
        ss2 = kyber.decrypt(ct, sk)
        dec = AES.new(ss2[:32], AES.MODE_GCM, nonce=nonce)
        recovered = dec.decrypt_and_verify(enc_key, tag)
        assert recovered == aes_key
        latencies.append((time.perf_counter() - t0) * 1000)
    total = time.perf_counter() - t_start
    return _report(f"Kyber-{variant} KEM", num_keys, total, latencies)


# ================================================================
#  Falcon Lattice Encryption Benchmark (Original)
# ================================================================
def bench_falcon(security_level, num_keys, warmup=3):
    banner(f"Falcon-{security_level} Lattice [Original] ({num_keys} keys)")
    from pqkds.falcon_certificateless_strict import CertificatelessFalconStrict
    from pqkds.falcon_encryption_strict import CertificatelessFalconEncryption

    PARAMS = {512: (512, 1024, 12289), 1024: (1024, 2048, 12289)}
    n, m, q = PARAMS[security_level]
    cf = CertificatelessFalconStrict(n, m, q)
    enc = CertificatelessFalconEncryption(cf)

    # Setup + keygen
    cf.setup()
    node_id = "bench_node"
    D_id, H_id = cf.partial_key_gen(node_id)
    S_id = cf.set_secret_value()
    sk = cf.set_sk(D_id, S_id)
    U_id = cf.set_pk(S_id)
    A = cf.system_params['A']
    B = cf.system_params['B']
    print(f"  n={n}, m={m}, q={q}")

    # warmup
    for _ in range(warmup):
        aes_key = os.urandom(32)
        er = enc.encrypt_session_key_with_params(node_id, aes_key, U_id, H_id, A, B)
        ct_json = json.loads(er['ciphertext'])
        enc.decrypt_session_key(ct_json, sk)

    latencies = []
    t_start = time.perf_counter()
    for _ in range(num_keys):
        t0 = time.perf_counter()
        aes_key = os.urandom(32)
        er = enc.encrypt_session_key_with_params(node_id, aes_key, U_id, H_id, A, B)
        ct_json = json.loads(er['ciphertext'])
        dr = enc.decrypt_session_key(ct_json, sk)
        assert dr['success']
        assert dr['session_key'] == aes_key
        latencies.append((time.perf_counter() - t0) * 1000)
    total = time.perf_counter() - t_start
    return _report(f"Falcon-{security_level} [Original]", num_keys, total, latencies)


# ================================================================
#  Falcon Fast Engine Benchmark (Optimized)
# ================================================================
def bench_falcon_fast(security_level, num_keys, warmup=5):
    banner(f"Falcon-{security_level} [FastEngine] ({num_keys} keys)")
    logging.disable(logging.CRITICAL)  # suppress verbose logs
    from pqkds.falcon_fast_engine import FastFalconEncryptionEngine

    PARAMS = {512: (512, 1024, 12289), 1024: (1024, 2048, 12289)}
    n, m, q = PARAMS[security_level]
    engine = FastFalconEncryptionEngine(n, m, q)
    user = engine.setup_user("bench_fast_node")
    sk, H_id, U_id = user['sk'], user['H_id'], user['U_id']
    print(f"  n={n}, m={m}, q={q} [FastDelegatedBasis + ParallelSampling + VectorizedRounding]")

    for _ in range(warmup):
        aes_key = os.urandom(32)
        ct = engine.encrypt("bench_fast_node", aes_key, U_id, H_id)
        recovered = engine.decrypt(ct, sk)
        assert recovered == aes_key

    latencies = []
    t_start = time.perf_counter()
    for _ in range(num_keys):
        t0 = time.perf_counter()
        aes_key = os.urandom(32)
        ct = engine.encrypt("bench_fast_node", aes_key, U_id, H_id)
        recovered = engine.decrypt(ct, sk)
        assert recovered == aes_key
        latencies.append((time.perf_counter() - t0) * 1000)
    total = time.perf_counter() - t_start
    logging.disable(logging.NOTSET)
    return _report(f"Falcon-{security_level} [FastEngine]", num_keys, total, latencies)


# ================================================================
#  Report
# ================================================================
def _report(name, count, total_sec, latencies):
    tp = count / total_sec if total_sec > 0 else 0
    avg = statistics.mean(latencies)
    med = statistics.median(latencies)
    mn, mx = min(latencies), max(latencies)
    p95 = sorted(latencies)[int(len(latencies) * 0.95)]
    std = statistics.stdev(latencies) if len(latencies) > 1 else 0
    status = "PASS" if tp >= 50 else "FAIL"

    print(f"\n  --- {name} Results ---")
    print(f"  Keys:       {count}")
    print(f"  Total time: {total_sec:.3f} sec")
    print(f"  Throughput: {tp:.1f} keys/sec")
    print(f"  Avg:        {avg:.2f} ms")
    print(f"  Median:     {med:.2f} ms")
    print(f"  Min/Max:    {mn:.2f} / {mx:.2f} ms")
    print(f"  P95:        {p95:.2f} ms")
    print(f"  StdDev:     {std:.2f} ms")
    print(f"  >>> {status}: {tp:.1f} keys/sec {'>=':} 50 keys/sec")
    return name, tp, status


# ================================================================
#  Main
# ================================================================
def main():
    banner("PQKDS Lattice-Based Key Pre-Distribution Benchmark")
    print("  Target: >= 50 keys/sec per scheme\n")

    N = 200
    results = []

    for v in [512, 768, 1024]:
        try:
            results.append(bench_kyber(v, N))
        except Exception as e:
            print(f"  Kyber-{v} SKIPPED: {e}")

    for sl in [512, 1024]:
        try:
            results.append(bench_falcon(sl, N))
        except Exception as e:
            print(f"  Falcon-{sl} Original SKIPPED: {e}")

    for sl in [512, 1024]:
        try:
            results.append(bench_falcon_fast(sl, N))
        except Exception as e:
            print(f"  Falcon-{sl} FastEngine SKIPPED: {e}")

    banner("SUMMARY")
    print(f"  {'Scheme':<35} {'Throughput':<18} {'Status'}")
    print(f"  {'-'*60}")
    for name, tp, status in results:
        print(f"  {name:<35} {tp:>8.1f} keys/sec    {status}")
    print(f"{'='*65}\n")


if __name__ == "__main__":
    main()
