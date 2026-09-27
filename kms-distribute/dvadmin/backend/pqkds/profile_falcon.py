import time
import sys
import os
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ultra_fast_keygen_v6 import UltraFastFalconKeygen

def profile_falcon():
    print("Falcon 性能分析")
    print("="*60)
    
    gen = UltraFastFalconKeygen()
    params = gen.setup_cached()
    
    user_id = "test_user"
    
    start = time.time()
    H_id = gen._fast_hash_to_matrix(user_id)
    hash_time = time.time() - start
    print(f"哈希矩阵生成: {hash_time*1000:.2f} ms")
    
    start = time.time()
    D_id = np.random.randint(-gen.beta, gen.beta + 1, size=(gen.m, gen.m), dtype=np.int64) % gen.q
    d_id_time = time.time() - start
    print(f"D_id生成: {d_id_time*1000:.2f} ms")
    
    start = time.time()
    S_id = np.random.randint(0, gen.q, size=gen.m, dtype=np.int64)
    s_id_time = time.time() - start
    print(f"S_id生成: {s_id_time*1000:.2f} ms")
    
    B = params['B']
    
    start = time.time()
    U_id = np.dot(B[:, :256], S_id[:256]) % gen.q
    matmul_time = time.time() - start
    print(f"矩阵乘法 (512x256 * 256): {matmul_time*1000:.2f} ms")
    
    start = time.time()
    U_id_full = np.dot(B, S_id) % gen.q
    matmul_full_time = time.time() - start
    print(f"矩阵乘法 (512x1024 * 1024): {matmul_full_time*1000:.2f} ms")
    
    total = hash_time + d_id_time + s_id_time + matmul_time
    print(f"\n总耗时 (优化): {total*1000:.2f} ms")
    print(f"总耗时 (完整): {(hash_time + d_id_time + s_id_time + matmul_full_time)*1000:.2f} ms")

if __name__ == '__main__':
    profile_falcon()

