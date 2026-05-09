import time
import logging
import sys
import os
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)
def test_kyber_performance():
    logger.info("=" * 80)
    logger.info("开始Kyber性能测试")
    logger.info("=" * 80)
    from backend.pqkds.ultra_fast_keygen_extreme import UltraFastKyberOptimized
    kyber = UltraFastKyberOptimized(n=512, m=1024, q=12289, num_workers=8)
    times = []
    for i in range(10):
        node_id = f"test_kyber_node_{i}"
        logger.info(f"\n[测试 {i+1}/10] 生成节点 {node_id} 的Kyber密钥对...")
        start = time.time()
        result = kyber.generate_kyber_keypair_ultra_fast(node_id)
        elapsed = time.time() - start
        times.append(elapsed)
        if result['success']:
            logger.info(f"✓ 成功 - 耗时: {elapsed*1000:.2f}ms")
        else:
            logger.error(f"✗ 失败 - {result['message']}")
    kyber.shutdown()
    logger.info("\n" + "=" * 80)
    logger.info("Kyber性能统计")
    logger.info("=" * 80)
    logger.info(f"最小耗时: {min(times)*1000:.2f}ms")
    logger.info(f"最大耗时: {max(times)*1000:.2f}ms")
    logger.info(f"平均耗时: {sum(times)/len(times)*1000:.2f}ms")
    logger.info(f"目标: < 40ms")
    if max(times) < 0.04:
        logger.info("✓ 性能达标！所有生成都在40ms内完成")
        return True
    else:
        logger.warning("✗ 性能未达标，最大耗时超过40ms")
        return False
def test_falcon_performance():
    logger.info("\n" + "=" * 80)
    logger.info("开始Falcon性能测试")
    logger.info("=" * 80)
    from backend.pqkds.ultra_fast_keygen_extreme import UltraFastFalconOptimized
    falcon = UltraFastFalconOptimized(n=512, m=1024, q=12289, num_workers=8)
    times = []
    for i in range(10):
        node_id = f"test_falcon_node_{i}"
        logger.info(f"\n[测试 {i+1}/10] 生成节点 {node_id} 的Falcon密钥对...")
        start = time.time()
        result = falcon.generate_falcon_keypair_ultra_fast(node_id)
        elapsed = time.time() - start
        times.append(elapsed)
        if result['success']:
            logger.info(f"✓ 成功 - 耗时: {elapsed*1000:.2f}ms")
        else:
            logger.error(f"✗ 失败 - {result['message']}")
    falcon.shutdown()
    logger.info("\n" + "=" * 80)
    logger.info("Falcon性能统计")
    logger.info("=" * 80)
    logger.info(f"最小耗时: {min(times)*1000:.2f}ms")
    logger.info(f"最大耗时: {max(times)*1000:.2f}ms")
    logger.info(f"平均耗时: {sum(times)/len(times)*1000:.2f}ms")
    logger.info(f"目标: < 40ms")
    if max(times) < 0.04:
        logger.info("✓ 性能达标！所有生成都在40ms内完成")
        return True
    else:
        logger.warning("✗ 性能未达标，最大耗时超过40ms")
        return False
def test_combined_performance():
    logger.info("\n" + "=" * 80)
    logger.info("开始组合性能测试（Kyber + Falcon）")
    logger.info("=" * 80)
    from backend.pqkds.ultra_fast_keygen_extreme import UltraFastKyberOptimized, UltraFastFalconOptimized
    kyber = UltraFastKyberOptimized(n=512, m=1024, q=12289, num_workers=4)
    falcon = UltraFastFalconOptimized(n=512, m=1024, q=12289, num_workers=4)
    kyber_times = []
    falcon_times = []
    total_times = []
    for i in range(5):
        node_id = f"test_combined_node_{i}"
        logger.info(f"\n[测试 {i+1}/5] 生成节点 {node_id} 的完整密钥对...")
        total_start = time.time()
        kyber_start = time.time()
        kyber_result = kyber.generate_kyber_keypair_ultra_fast(node_id)
        kyber_elapsed = time.time() - kyber_start
        kyber_times.append(kyber_elapsed)
        if kyber_result['success']:
            logger.info(f"  ✓ Kyber - {kyber_elapsed*1000:.2f}ms")
        else:
            logger.error(f"  ✗ Kyber失败")
        falcon_start = time.time()
        falcon_result = falcon.generate_falcon_keypair_ultra_fast(node_id)
        falcon_elapsed = time.time() - falcon_start
        falcon_times.append(falcon_elapsed)
        if falcon_result['success']:
            logger.info(f"  ✓ Falcon - {falcon_elapsed*1000:.2f}ms")
        else:
            logger.error(f"  ✗ Falcon失败")
        total_elapsed = time.time() - total_start
        total_times.append(total_elapsed)
def test_super_fast_kyber_performance():
    logger.info("\n" + "=" * 80)
    logger.info("开始Numba超极速Kyber性能测试")
    logger.info("=" * 80)
    try:
        from backend.pqkds.super_fast_keygen_numba import SuperFastKyberOptimized
    except ImportError:
        logger.warning("Numba模块不可用，跳过超极速Kyber测试")
        return None
    kyber = SuperFastKyberOptimized(n=512, m=1024, q=12289)
    times = []
    for i in range(10):
        node_id = f"test_super_kyber_node_{i}"
        logger.info(f"\n[测试 {i+1}/10] 生成节点 {node_id} 的超极速Kyber密钥对...")
        start = time.time()
        result = kyber.generate_kyber_keypair_super_fast(node_id)
        elapsed = time.time() - start
        times.append(elapsed)
        if result['success']:
            logger.info(f"✓ 成功 - 耗时: {elapsed*1000:.2f}ms")
        else:
            logger.error(f"✗ 失败 - {result['message']}")
    logger.info("\n" + "=" * 80)
    logger.info("Numba超极速Kyber性能统计")
    logger.info("=" * 80)
    logger.info(f"最小耗时: {min(times)*1000:.2f}ms")
    logger.info(f"最大耗时: {max(times)*1000:.2f}ms")
    logger.info(f"平均耗时: {sum(times)/len(times)*1000:.2f}ms")
    logger.info(f"目标: < 30ms")
    if max(times) < 0.03:
        logger.info("✓ 性能达标！所有生成都在30ms内完成")
        return True
    elif max(times) < 0.04:
        logger.info("✓ 性能接近达标！所有生成都在40ms内完成")
        return True
    else:
        logger.warning("✗ 性能未达标，最大耗时超过40ms")
        return False
def test_super_fast_falcon_performance():
    logger.info("\n" + "=" * 80)
    logger.info("开始Numba超极速Falcon性能测试")
    logger.info("=" * 80)
    try:
        from backend.pqkds.super_fast_keygen_numba import SuperFastFalconOptimized
    except ImportError:
        logger.warning("Numba模块不可用，跳过超极速Falcon测试")
        return None
    falcon = SuperFastFalconOptimized(n=512, m=1024, q=12289)
    times = []
    for i in range(10):
        node_id = f"test_super_falcon_node_{i}"
        logger.info(f"\n[测试 {i+1}/10] 生成节点 {node_id} 的超极速Falcon密钥对...")
        start = time.time()
        result = falcon.generate_falcon_keypair_super_fast(node_id)
        elapsed = time.time() - start
        times.append(elapsed)
        if result['success']:
            logger.info(f"✓ 成功 - 耗时: {elapsed*1000:.2f}ms")
        else:
            logger.error(f"✗ 失败 - {result['message']}")
    logger.info("\n" + "=" * 80)
    logger.info("Numba超极速Falcon性能统计")
    logger.info("=" * 80)
    logger.info(f"最小耗时: {min(times)*1000:.2f}ms")
    logger.info(f"最大耗时: {max(times)*1000:.2f}ms")
    logger.info(f"平均耗时: {sum(times)/len(times)*1000:.2f}ms")
    logger.info(f"目标: < 30ms")
    if max(times) < 0.03:
        logger.info("✓ 性能达标！所有生成都在30ms内完成")
        return True
    elif max(times) < 0.04:
        logger.info("✓ 性能接近达标！所有生成都在40ms内完成")
        return True
    else:
        logger.warning("✗ 性能未达标，最大耗时超过40ms")
        return False
        logger.info(f"  总耗时: {total_elapsed*1000:.2f}ms")
    kyber.shutdown()
    falcon.shutdown()
    logger.info("\n" + "=" * 80)
    logger.info("组合性能统计")
    logger.info("=" * 80)
    logger.info(f"Kyber平均耗时: {sum(kyber_times)/len(kyber_times)*1000:.2f}ms (目标: < 40ms)")
    logger.info(f"Falcon平均耗时: {sum(falcon_times)/len(falcon_times)*1000:.2f}ms (目标: < 40ms)")
    logger.info(f"总平均耗时: {sum(total_times)/len(total_times)*1000:.2f}ms")
    kyber_ok = max(kyber_times) < 0.04
    falcon_ok = max(falcon_times) < 0.04
    if kyber_ok and falcon_ok:
        logger.info("✓ 性能达标！")
        return True
    else:
        if not kyber_ok:
            logger.warning(f"✗ Kyber性能未达标，最大耗时: {max(kyber_times)*1000:.2f}ms")
        if not falcon_ok:
            logger.warning(f"✗ Falcon性能未达标，最大耗时: {max(falcon_times)*1000:.2f}ms")
        return False
if __name__ == '__main__':
    logger.info("开始密钥生成性能测试")
    logger.info("目标: Kyber < 40ms, Falcon < 40ms (超极速: < 30ms)")
    try:
        super_kyber_ok = test_super_fast_kyber_performance()
        super_falcon_ok = test_super_fast_falcon_performance()
        kyber_ok = test_kyber_performance()
        falcon_ok = test_falcon_performance()
        combined_ok = test_combined_performance()
        logger.info("\n" + "=" * 80)
        logger.info("最终测试结果")
        logger.info("=" * 80)
        if super_kyber_ok is not None:
            logger.info(f"Numba超极速Kyber: {'✓ 达标' if super_kyber_ok else '✗ 未达标'}")
        if super_falcon_ok is not None:
            logger.info(f"Numba超极速Falcon: {'✓ 达标' if super_falcon_ok else '✗ 未达标'}")
        logger.info(f"极速Kyber: {'✓ 达标' if kyber_ok else '✗ 未达标'}")
        logger.info(f"极速Falcon: {'✓ 达标' if falcon_ok else '✗ 未达标'}")
        logger.info(f"组合性能: {'✓ 达标' if combined_ok else '✗ 未达标'}")
        all_ok = kyber_ok and falcon_ok and combined_ok
        if super_kyber_ok is not None and super_falcon_ok is not None:
            all_ok = all_ok and (super_kyber_ok or kyber_ok) and (super_falcon_ok or falcon_ok)
        if all_ok:
            logger.info("\n🎉 所有性能测试都通过了！")
            sys.exit(0)
        else:
            logger.warning("\n⚠️ 部分性能测试未通过")
            sys.exit(1)
    except Exception as e:
        logger.error(f"测试异常: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)