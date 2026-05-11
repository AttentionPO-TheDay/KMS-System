#!/usr/bin/env python
import sys
import os
sys.path.insert(0, 'D:/pythonProject/1.3-3/falcon-kds2 - aug/ruoyi')
os.chdir('D:/pythonProject/1.3-3/falcon-kds2 - aug/ruoyi')

import time
import logging
from backend.pqkds.ultra_fast_keygen_v3 import UltraFastKeygenV3

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

def benchmark():
    logger.info("\n" + "="*70)
    logger.info("Falcon-KDS2 密钥生成性能优化基准测试")
    logger.info("="*70 + "\n")
    
    keygen = UltraFastKeygenV3(n=512, m=1024, q=12289, num_workers=8)
    
    logger.info("【Falcon密钥生成测试】")
    node_ids = [f"falcon_node_{i}" for i in range(50)]
    start = time.time()
    results = keygen.batch_generate_falcon_keypairs(node_ids)
    falcon_time = time.time() - start
    falcon_throughput = 50 / falcon_time
    
    logger.info(f"生成50个Falcon密钥对耗时: {falcon_time:.3f}秒")
    logger.info(f"吞吐量: {falcon_throughput:.2f} 密钥/秒")
    logger.info(f"平均时间: {falcon_time/50*1000:.2f} ms/密钥")
    if falcon_throughput >= 50:
        logger.info("✓ 达到目标效率 (≥50 密钥/秒)\n")
    else:
        logger.info(f"✗ 未达到目标效率 (当前: {falcon_throughput:.2f}, 目标: 50)\n")
    
    logger.info("【Kyber密钥生成测试】")
    node_ids = [f"kyber_node_{i}" for i in range(50)]
    start = time.time()
    results = keygen.batch_generate_kyber_keypairs(node_ids)
    kyber_time = time.time() - start
    kyber_throughput = 50 / kyber_time
    
    logger.info(f"生成50个Kyber密钥对耗时: {kyber_time:.3f}秒")
    logger.info(f"吞吐量: {kyber_throughput:.2f} 密钥/秒")
    logger.info(f"平均时间: {kyber_time/50*1000:.2f} ms/密钥")
    if kyber_throughput >= 50:
        logger.info("✓ 达到目标效率 (≥50 密钥/秒)\n")
    else:
        logger.info(f"✗ 未达到目标效率 (当前: {kyber_throughput:.2f}, 目标: 50)\n")
    
    logger.info("="*70)
    logger.info("性能总结")
    logger.info("="*70)
    logger.info(f"Falcon: {falcon_throughput:.2f} 密钥/秒 {'✓' if falcon_throughput >= 50 else '✗'}")
    logger.info(f"Kyber:  {kyber_throughput:.2f} 密钥/秒 {'✓' if kyber_throughput >= 50 else '✗'}")
    logger.info("="*70 + "\n")

if __name__ == '__main__':
    benchmark()

