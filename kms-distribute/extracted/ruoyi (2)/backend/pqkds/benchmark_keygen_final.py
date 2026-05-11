import time
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ultra_fast_keygen_final import FinalOptimizedKyberKeygen, FinalOptimizedFalconKeygen

def benchmark_kyber():
    print("\n" + "="*60)
    print("Kyber 无证书密钥生成性能测试 (最终版)")
    print("="*60)
    
    gen = FinalOptimizedKyberKeygen()
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
    print("Falcon 无证书密钥生成性能测试 (最终版)")
    print("="*60)
    
    gen = FinalOptimizedFalconKeygen()
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

if __name__ == '__main__':
    kyber_rate = benchmark_kyber()
    falcon_rate = benchmark_falcon()
    
    print("\n" + "="*60)
    print("性能总结 (最终版本)")
    print("="*60)
    print(f"Kyber 单线程: {kyber_rate:.2f} 密钥对/秒")
    print(f"Falcon 单线程: {falcon_rate:.2f} 密钥对/秒")
    
    print("\n" + "="*60)
    print("优化成果")
    print("="*60)
    if kyber_rate >= 50:
        print(f"✓ Kyber 达到目标: {kyber_rate:.2f} 密钥对/秒 (目标: 50)")
    else:
        print(f"✗ Kyber 未达到目标: {kyber_rate:.2f} 密钥对/秒 (目标: 50)")
    
    if falcon_rate >= 50:
        print(f"✓ Falcon 达到目标: {falcon_rate:.2f} 密钥对/秒 (目标: 50)")
    else:
        print(f"✗ Falcon 未达到目标: {falcon_rate:.2f} 密钥对/秒 (目标: 50)")

