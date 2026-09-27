import time
import sys
import os
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ultra_fast_keygen_v5 import FastKyberKeygen, FastFalconKeygen, ParallelKeygenPool

def benchmark_kyber():
    print("\n" + "="*60)
    print("Kyber 无证书密钥生成性能测试")
    print("="*60)
    
    gen = FastKyberKeygen()
    gen.setup_cached()
    
    num_keys = 50
    start = time.time()
    
    for i in range(num_keys):
        gen.generate_keypair_fast(f"user_{i}")
    
    elapsed = time.time() - start
    rate = num_keys / elapsed
    
    print(f"生成 {num_keys} 个密钥对耗时: {elapsed:.3f} 秒")
    print(f"生成速率: {rate:.2f} 密钥对/秒")
    print(f"目标: 50 密钥对/秒")
    print(f"状态: {'✓ 达到目标' if rate >= 50 else '✗ 未达到目标'}")
    
    return rate

def benchmark_falcon():
    print("\n" + "="*60)
    print("Falcon 无证书密钥生成性能测试")
    print("="*60)
    
    gen = FastFalconKeygen()
    gen.setup_cached()
    
    num_keys = 50
    start = time.time()
    
    for i in range(num_keys):
        gen.generate_keypair_fast(f"user_{i}")
    
    elapsed = time.time() - start
    rate = num_keys / elapsed
    
    print(f"生成 {num_keys} 个密钥对耗时: {elapsed:.3f} 秒")
    print(f"生成速率: {rate:.2f} 密钥对/秒")
    print(f"目标: 50 密钥对/秒")
    print(f"状态: {'✓ 达到目标' if rate >= 50 else '✗ 未达到目标'}")
    
    return rate

def benchmark_parallel():
    print("\n" + "="*60)
    print("并行密钥生成性能测试")
    print("="*60)
    
    pool = ParallelKeygenPool(num_workers=4)
    
    user_ids = [f"user_{i}" for i in range(50)]
    
    start = time.time()
    kyber_keys = pool.generate_kyber_keypairs_batch(user_ids)
    kyber_time = time.time() - start
    
    start = time.time()
    falcon_keys = pool.generate_falcon_keypairs_batch(user_ids)
    falcon_time = time.time() - start
    
    pool.shutdown()
    
    kyber_rate = len(user_ids) / kyber_time
    falcon_rate = len(user_ids) / falcon_time
    
    print(f"\nKyber 并行生成 {len(user_ids)} 个密钥对耗时: {kyber_time:.3f} 秒")
    print(f"Kyber 生成速率: {kyber_rate:.2f} 密钥对/秒")
    
    print(f"\nFalcon 并行生成 {len(user_ids)} 个密钥对耗时: {falcon_time:.3f} 秒")
    print(f"Falcon 生成速率: {falcon_rate:.2f} 密钥对/秒")
    
    return kyber_rate, falcon_rate

if __name__ == '__main__':
    kyber_rate = benchmark_kyber()
    falcon_rate = benchmark_falcon()
    kyber_parallel, falcon_parallel = benchmark_parallel()
    
    print("\n" + "="*60)
    print("性能总结")
    print("="*60)
    print(f"Kyber 单线程: {kyber_rate:.2f} 密钥对/秒")
    print(f"Falcon 单线程: {falcon_rate:.2f} 密钥对/秒")
    print(f"Kyber 并行: {kyber_parallel:.2f} 密钥对/秒")
    print(f"Falcon 并行: {falcon_parallel:.2f} 密钥对/秒")

