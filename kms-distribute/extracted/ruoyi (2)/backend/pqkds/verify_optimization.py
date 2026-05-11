import os
import sys
import logging
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)
def check_files():
    logger.info("=" * 80)
    logger.info("检查文件完整性")
    logger.info("=" * 80)
    base_path = "backend/pqkds"
    required_files = [
        "ultra_fast_keygen_extreme.py",
        "super_fast_keygen_numba.py",
        "performance_test_extreme.py",
        "requirements_optimization.txt",
        "PERFORMANCE_OPTIMIZATION_GUIDE.txt",
        "QUICK_START_OPTIMIZATION.txt",
        "IMPLEMENTATION_SUMMARY.txt",
    ]
    all_exist = True
    for filename in required_files:
        filepath = os.path.join(base_path, filename)
        if os.path.exists(filepath):
            size = os.path.getsize(filepath)
            logger.info(f"✓ {filename} ({size} bytes)")
        else:
            logger.error(f"✗ {filename} 不存在")
            all_exist = False
    return all_exist
def check_node_service():
    logger.info("\n" + "=" * 80)
    logger.info("检查node_service.py修改")
    logger.info("=" * 80)
    filepath = "backend/pqkds/node_service.py"
    if not os.path.exists(filepath):
        logger.error(f"✗ {filepath} 不存在")
        return False
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    checks = [
        ("超极速Kyber导入", "from .super_fast_keygen_numba import SuperFastKyberOptimized"),
        ("极速Kyber导入", "from .ultra_fast_keygen_extreme import UltraFastKyberOptimized"),
        ("超极速Falcon导入", "from .super_fast_keygen_numba import SuperFastFalconOptimized"),
        ("极速Falcon导入", "from .ultra_fast_keygen_extreme import UltraFastFalconOptimized"),
        ("Kyber超极速调用", "kyber_super.generate_kyber_keypair_super_fast"),
        ("Kyber极速调用", "kyber_ultra.generate_kyber_keypair_ultra_fast"),
        ("Falcon超极速调用", "falcon_super.generate_falcon_keypair_super_fast"),
        ("Falcon极速调用", "falcon_ultra.generate_falcon_keypair_ultra_fast"),
    ]
    all_ok = True
    for check_name, check_str in checks:
        if check_str in content:
            logger.info(f"✓ {check_name}")
        else:
            logger.error(f"✗ {check_name} 未找到")
            all_ok = False
    return all_ok
def check_imports():
    logger.info("\n" + "=" * 80)
    logger.info("检查模块导入")
    logger.info("=" * 80)
    all_ok = True
    try:
        from backend.pqkds.ultra_fast_keygen_extreme import UltraFastKyberOptimized, UltraFastFalconOptimized
        logger.info("✓ ultra_fast_keygen_extreme 模块可导入")
    except ImportError as e:
        logger.error(f"✗ ultra_fast_keygen_extreme 导入失败: {e}")
        all_ok = False
    try:
        from backend.pqkds.super_fast_keygen_numba import SuperFastKyberOptimized, SuperFastFalconOptimized
        logger.info("✓ super_fast_keygen_numba 模块可导入")
    except ImportError as e:
        logger.warning(f"⚠ super_fast_keygen_numba 导入失败（可能是Numba未安装）: {e}")
    try:
        from backend.pqkds.performance_test_extreme import test_kyber_performance, test_falcon_performance
        logger.info("✓ performance_test_extreme 模块可导入")
    except ImportError as e:
        logger.error(f"✗ performance_test_extreme 导入失败: {e}")
        all_ok = False
    return all_ok
def check_dependencies():
    logger.info("\n" + "=" * 80)
    logger.info("检查依赖")
    logger.info("=" * 80)
    all_ok = True
    try:
        import numpy as np
        logger.info(f"✓ NumPy {np.__version__} 已安装")
    except ImportError:
        logger.error("✗ NumPy 未安装，请运行: pip install numpy>=1.21.0")
        all_ok = False
    try:
        import numba
        logger.info(f"✓ Numba {numba.__version__} 已安装（超极速模式可用）")
    except ImportError:
        logger.warning("⚠ Numba 未安装，将使用极速模式（纯NumPy）")
        logger.info("  建议安装: pip install numba>=0.55.0")
    return all_ok
def main():
    logger.info("\n")
    logger.info("🔍 Falcon-KDS2 密钥生成性能优化 - 验证脚本")
    logger.info("=" * 80)
    results = {
        "文件完整性": check_files(),
        "node_service.py修改": check_node_service(),
        "模块导入": check_imports(),
        "依赖检查": check_dependencies(),
    }
    logger.info("\n" + "=" * 80)
    logger.info("验证结果总结")
    logger.info("=" * 80)
    for check_name, result in results.items():
        status = "✓ 通过" if result else "✗ 失败"
        logger.info(f"{check_name}: {status}")
    all_passed = all(results.values())
    logger.info("\n" + "=" * 80)
    if all_passed:
        logger.info("✅ 所有验证都通过了！")
        logger.info("\n下一步：")
        logger.info("1. 运行性能测试: python backend/pqkds/performance_test_extreme.py")
        logger.info("2. 通过前端注册节点进行集成测试")
        logger.info("3. 观察日志中的密钥生成耗时")
        return 0
    else:
        logger.warning("⚠️ 部分验证未通过，请检查上面的错误信息")
        return 1
if __name__ == '__main__':
    sys.exit(main())