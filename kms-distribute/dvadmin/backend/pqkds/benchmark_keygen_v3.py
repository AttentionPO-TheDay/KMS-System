import time
import logging
from backend.pqkds.ultra_fast_keygen_v3 import UltraFastKeygenV3
from backend.pqkds.ultra_fast_keygen_numba_v2 import UltraFastKeygenNumbaV2

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def benchmark_keygen(keygen_class, algorithm_name, num_keys=50, key_type='both'):
    logger.info(f"\n{'='*60}")
    logger.info(f"性能基准测试: {algorithm_name}")
    logger.info(f"{'='*60}")
    
    keygen = keygen_class(n=512, m=1024, q=12289, num_workers=8)
    node_ids = [f"node_{i}" for i in range(num_keys)]
    
    start_time = time.time()
    
    if key_type == 'falcon':
        results = keygen.batch_generate_falcon_keypairs(node_ids)
    elif key_type == 'kyber':
        results = keygen.batch_generate_kyber_keypairs(node_ids)
    else:
        results = keygen.batch_generate_keypairs(node_ids, algorithm='both')
    
    total_time = time.time() - start_time
    
    successful = sum(1 for r in results if r.get('success', False))
    failed = len(results) - successful
    
    throughput = num_keys / total_time if total_time > 0 else 0
    
    logger.info(f"生成密钥数: {num_keys}")
    logger.info(f"成功: {successful}, 失败: {failed}")
    logger.info(f"总耗时: {total_time:.3f}秒")
    logger.info(f"吞吐量: {throughput:.2f} 密钥/秒")
    logger.info(f"平均时间: {total_time/num_keys*1000:.2f} ms/密钥")
    
    if throughput >= 50:
        logger.info(f"✓ 达到目标效率 (≥50 密钥/秒)")
    else:
        logger.info(f"✗ 未达到目标效率 (当前: {throughput:.2f}, 目标: 50)")
    
    return {
        'algorithm': algorithm_name,
        'num_keys': num_keys,
        'total_time': total_time,
        'throughput': throughput,
        'successful': successful,
        'failed': failed
    }

if __name__ == '__main__':
    logger.info("开始密钥生成性能基准测试")
    
    results = []
    
    results.append(benchmark_keygen(UltraFastKeygenV3, "UltraFastKeygenV3-Falcon", 50, 'falcon'))
    results.append(benchmark_keygen(UltraFastKeygenV3, "UltraFastKeygenV3-Kyber", 50, 'kyber'))
    
    try:
        results.append(benchmark_keygen(UltraFastKeygenNumbaV2, "UltraFastKeygenNumbaV2-Falcon", 50, 'falcon'))
        results.append(benchmark_keygen(UltraFastKeygenNumbaV2, "UltraFastKeygenNumbaV2-Kyber", 50, 'kyber'))
    except Exception as e:
        logger.warning(f"Numba版本测试失败: {e}")
    
    logger.info(f"\n{'='*60}")
    logger.info("性能基准测试总结")
    logger.info(f"{'='*60}")
    
    for result in results:
        status = "✓" if result['throughput'] >= 50 else "✗"
        logger.info(f"{status} {result['algorithm']}: {result['throughput']:.2f} 密钥/秒")

