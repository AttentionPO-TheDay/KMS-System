import os
import sys
import django
import time
import logging
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'application.settings')
django.setup()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
import numpy as np
from pqkds.ultra_fast_keygen_implementations import (
    UltraFastCertificatelessFalcon,
    UltraFastCertificatelessKyber
)
from pqkds.falcon_aes_session_encryption_optimized import FalconAESSessionKeyEncryptionOptimized
from pqkds.certificateless_kyber_node_keygen import CertificatelessKyberNodeKeyGeneration
def benchmark_falcon_generation(num_tests: int = 5) -> Dict[str, float]:
    logger.info(f"\n{'='*70}")
    logger.info(f"Falcon密钥对生成性能对比 (测试{num_tests}次)")
    logger.info(f"{'='*70}")
    D_id_sample = np.random.randint(0, 12289, size=(1024, 1024), dtype=np.int64)
    logger.info("\n[测试1] 超快速实现 (并行采样 + 向量化)")
    ultra_times = []
    for i in range(num_tests):
        falcon_ultra = UltraFastCertificatelessFalcon(n=512, m=1024, num_workers=8)
        start = time.time()
        result = falcon_ultra.generate_falcon_keypair_ultra_fast(f"node_{i}", D_id_sample.copy())
        elapsed = time.time() - start
        ultra_times.append(elapsed)
        logger.info(f"  测试{i+1}: {elapsed:.4f}秒")
        falcon_ultra.shutdown()
    ultra_avg = np.mean(ultra_times)
    logger.info(f"超快速平均耗时：{ultra_avg:.4f}秒")
    logger.info("\n[测试2] 标准优化实现")
    standard_times = []
    for i in range(num_tests):
        falcon_service = FalconAESSessionKeyEncryptionOptimized(n=512, m=1024, num_workers=4)
        falcon_service._initialize_cf()
        if falcon_service.cf_strict.system_params is None:
            falcon_service.cf_strict.setup()
        start = time.time()
        S_id = falcon_service.cf_strict.set_secret_value()
        U_id = falcon_service.cf_strict.set_pk(S_id)
        elapsed = time.time() - start
        standard_times.append(elapsed)
        logger.info(f"  测试{i+1}: {elapsed:.4f}秒")
    standard_avg = np.mean(standard_times)
    logger.info(f"标准优化平均耗时：{standard_avg:.4f}秒")
    improvement = (standard_avg - ultra_avg) / standard_avg * 100
    speedup = standard_avg / ultra_avg
    logger.info(f"\n性能提升：{improvement:.1f}% (提速{speedup:.2f}倍)")
    return {
        'ultra_avg': ultra_avg,
        'standard_avg': standard_avg,
        'improvement_pct': improvement,
        'speedup': speedup
    }
def benchmark_kyber_generation(num_tests: int = 5) -> Dict[str, float]:
    logger.info(f"\n{'='*70}")
    logger.info(f"Kyber密钥对生成性能对比 (测试{num_tests}次)")
    logger.info(f"{'='*70}")
    logger.info("\n[测试1] 超快速实现")
    ultra_times = []
    for i in range(num_tests):
        kyber_ultra = UltraFastCertificatelessKyber(n=512, m=1024, num_workers=8)
        start = time.time()
        result = kyber_ultra.generate_kyber_keypair_ultra_fast(f"node_{i}")
        elapsed = time.time() - start
        ultra_times.append(elapsed)
        logger.info(f"  测试{i+1}: {elapsed:.4f}秒")
        kyber_ultra.shutdown()
    ultra_avg = np.mean(ultra_times)
    logger.info(f"超快速平均耗时：{ultra_avg:.4f}秒")
    logger.info("\n[测试2] 标准实现")
    standard_times = []
    for i in range(num_tests):
        ck_kyber = CertificatelessKyberNodeKeyGeneration(n=512, m=1024)
        start = time.time()
        result = ck_kyber.generate_node_kyber_keypair(f"node_{i}")
        elapsed = time.time() - start
        standard_times.append(elapsed)
        logger.info(f"  测试{i+1}: {elapsed:.4f}秒")
    standard_avg = np.mean(standard_times)
    logger.info(f"标准平均耗时：{standard_avg:.4f}秒")
    improvement = (standard_avg - ultra_avg) / standard_avg * 100
    speedup = standard_avg / ultra_avg
    logger.info(f"\n性能提升：{improvement:.1f}% (提速{speedup:.2f}倍)")
    return {
        'ultra_avg': ultra_avg,
        'standard_avg': standard_avg,
        'improvement_pct': improvement,
        'speedup': speedup
    }
def benchmark_concurrent_generation(num_nodes: int = 10) -> Dict[str, float]:
    logger.info(f"\n{'='*70}")
    logger.info(f"并发密钥生成性能测试 ({num_nodes}个节点)")
    logger.info(f"{'='*70}")
    from concurrent.futures import ThreadPoolExecutor, as_completed
    def generate_falcon_concurrent(node_id: int):
        D_id = np.random.randint(0, 12289, size=(1024, 1024), dtype=np.int64)
        falcon = UltraFastCertificatelessFalcon(n=512, m=1024, num_workers=4)
        result = falcon.generate_falcon_keypair_ultra_fast(f"node_{node_id}", D_id)
        falcon.shutdown()
        return result.get('timing', {}).get('total', 0)
    logger.info(f"\n[超快速版本] {num_nodes}个节点并发生成Falcon密钥对")
    start = time.time()
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(generate_falcon_concurrent, i) for i in range(num_nodes)]
        times = [f.result() for f in as_completed(futures)]
    total_time_ultra = time.time() - start
    logger.info(f"总耗时：{total_time_ultra:.2f}秒")
    logger.info(f"单个平均：{np.mean(times):.4f}秒")
    logger.info(f"理论串行耗时：{np.sum(times):.2f}秒")
    logger.info(f"并发效率：{np.sum(times) / total_time_ultra:.2f}倍")
    return {
        'total_time': total_time_ultra,
        'per_node_avg': np.mean(times),
        'concurrency_factor': np.sum(times) / total_time_ultra
    }
if __name__ == '__main__':
    logger.info("╔" + "═"*68 + "╗")
    logger.info("║" + " "*15 + "Falcon-KDS2 性能优化验证测试" + " "*20 + "║")
    logger.info("╚" + "═"*68 + "╝")
    try:
        falcon_results = benchmark_falcon_generation(num_tests=5)
        kyber_results = benchmark_kyber_generation(num_tests=5)
        concurrent_results = benchmark_concurrent_generation(num_nodes=10)
        logger.info(f"\n{'='*70}")
        logger.info("性能测试总结报告")
        logger.info(f"{'='*70}")
        logger.info(f"\n[Falcon密钥对生成]")
        logger.info(f"  超快速实现：{falcon_results['ultra_avg']:.4f}秒")
        logger.info(f"  标准实现：{falcon_results['standard_avg']:.4f}秒")
        logger.info(f"  性能提升：{falcon_results['improvement_pct']:.1f}%")
        logger.info(f"  提速倍数：{falcon_results['speedup']:.2f}倍")
        logger.info(f"\n[Kyber密钥对生成]")
        logger.info(f"  超快速实现：{kyber_results['ultra_avg']:.4f}秒")
        logger.info(f"  标准实现：{kyber_results['standard_avg']:.4f}秒")
        logger.info(f"  性能提升：{kyber_results['improvement_pct']:.1f}%")
        logger.info(f"  提速倍数：{kyber_results['speedup']:.2f}倍")
        logger.info(f"\n[并发生成测试（10个节点）]")
        logger.info(f"  总耗时：{concurrent_results['total_time']:.2f}秒")
        logger.info(f"  单个平均：{concurrent_results['per_node_avg']:.4f}秒")
        logger.info(f"  并发效率：{concurrent_results['concurrency_factor']:.2f}倍")
        logger.info(f"\n✅ 性能优化验证完成！")
        logger.info(f"{'='*70}\n")
    except Exception as e:
        logger.error(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()