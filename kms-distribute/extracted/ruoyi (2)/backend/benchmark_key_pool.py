# -*- coding: utf-8 -*-
"""
基于格的安全密钥预分配 —— 完整加解密闭环性能基准测试

测试流程 (每条密钥):
  Kyber:  生成随机AES密钥 → 无证书格密码Enc加密 → 无证书格密码Dec解密 → 验证正确性 → 记录耗时
  Falcon: 生成随机AES密钥 → Falcon格密码加密 → Falcon格密码解密 → 验证正确性 → 记录耗时

通过标准: 每秒不小于 50 条

运行方式:
    cd backend
    python benchmark_key_pool.py
"""
import os, sys, time, hashlib, statistics, base64
import numpy as np

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'application.settings')
import django; django.setup()

# 抑制加解密过程中的大量日志输出
import logging
logging.getLogger('pqkds').setLevel(logging.WARNING)

from pqkds.models import Node

# ── 配置 ──
COUNT          = 100    # 每轮测试密钥数
ROUNDS         = 3      # 测试轮数
MIN_THROUGHPUT = 50     # 最低吞吐量 (keys/sec)


def pick_kyber_pair():
    """选取两个拥有无证书 Kyber 密钥数据 (含 cl_public_key, cl_private_key, A) 的节点"""
    import json as _json
    candidates = []
    for n in Node.objects.exclude(kyber_partial_key_data='').order_by('node_id'):
        try:
            data = _json.loads(n.kyber_partial_key_data)
            if data.get('cl_public_key') and data.get('cl_private_key') and data.get('A'):
                candidates.append(n)
        except Exception:
            continue
        if len(candidates) >= 2:
            break
    if len(candidates) < 2:
        print("❌ 需要至少 2 个拥有无证书 Kyber 密钥 (含 cl_public_key, cl_private_key, A) 的节点")
        print("   提示: 重新注册节点以生成包含无证书层密钥的 Kyber 密钥对")
        sys.exit(1)
    return candidates[0], candidates[1]


def pick_falcon_pair():
    """选取两个拥有可解析 Falcon 格密码公钥+私钥的节点"""
    from pqkds.falcon_aes_session_encryption import _parse_key_json
    candidates = []
    for n in Node.objects.exclude(falcon_public_key='').exclude(falcon_private_key='').order_by('node_id'):
        try:
            data = _parse_key_json(n.falcon_public_key)
            if 'U_id' in data:
                candidates.append(n)
        except Exception:
            continue
        if len(candidates) >= 2:
            break
    if len(candidates) < 2:
        print("❌ 需要至少 2 个拥有完整 Falcon 格密码密钥的节点 (含 U_id)")
        print("   提示: 在节点管理中为节点生成 Falcon 密钥")
        sys.exit(1)
    return candidates[0], candidates[1]


def banner(title, node1, node2):
    print(f"\n{'='*64}")
    print(f"  {title}")
    print(f"{'='*64}")
    print(f"  节点对:   {node1.node_id} ↔ {node2.node_id}")
    print(f"  每轮:     {COUNT} 条  ×  {ROUNDS} 轮")
    print(f"  要求:     ≥ {MIN_THROUGHPUT} keys/sec")
    print(f"{'='*64}")


def run_kyber_benchmark(node2):
    """
    Kyber 无证书格密码: 生成AES密钥 → Enc加密 → Dec解密 → 验证

    Enc: c₁ = Aᵗ·r + e₁, c₂ = uᵗ·r + e₂ + ⌊q/2⌋·M
    Dec: M = ⌊(c₂ − s̄ᵗ·c₁) / (q/2)⌋
    """
    import json as _json
    from pqkds.kyber_fast_engine import kyber_fast_encrypt, kyber_fast_decrypt

    # 解析无证书层密钥
    data = _json.loads(node2.kyber_partial_key_data)
    A = np.array(data['A'], dtype=np.int64)
    u = np.array(data['cl_public_key'], dtype=np.int64)
    sk = np.array(data['cl_private_key'], dtype=np.int64)
    params = data.get('parameters', {})
    n = params.get('n', 512)
    m = params.get('m', 1024)
    q = params.get('q', 12289)
    sigma = 1.17

    # 预热: 触发 BLAS 缓存和 numpy 内部优化
    for _ in range(5):
        _key = os.urandom(32)
        _ct = kyber_fast_encrypt(A, u, _key, n, m, q, sigma)
        kyber_fast_decrypt(_ct['C1'], _ct['C2'], sk, q, 32)

    throughputs = []

    for r in range(1, ROUNDS + 1):
        latencies = []
        ok_count = 0
        for _ in range(COUNT):
            t0 = time.perf_counter()

            # 1. 生成随机 AES-256 密钥
            aes_key = os.urandom(32)
            # 2. 无证书格密码 Enc 加密
            ct = kyber_fast_encrypt(A, u, aes_key, n, m, q, sigma)
            # 3. 无证书格密码 Dec 解密
            recovered_key = kyber_fast_decrypt(ct['C1'], ct['C2'], sk, q, len(aes_key))

            t1 = time.perf_counter()
            # 4. 验证正确性
            assert recovered_key == aes_key, "Kyber 无证书格密码解密验证失败!"
            ok_count += 1
            latencies.append((t1 - t0) * 1000)

        elapsed = sum(latencies) / 1000
        tp = ok_count / elapsed if elapsed > 0 else 0
        throughputs.append(tp)
        print(f"\n  第 {r}/{ROUNDS} 轮  Kyber-{n} (无证书格密码 Enc/Dec):")
        print(f"    成功: {ok_count}/{COUNT}  耗时: {elapsed:.3f}s")
        print(f"    吞吐量: {tp:.1f} keys/sec  平均延迟: {statistics.mean(latencies):.2f} ms")

    return throughputs



def run_falcon_benchmark(node1, node2):
    """Falcon 格密码: 生成AES密钥 → Falcon加密 → Falcon解密 → 验证
    通过系统级 FalconAESSessionKeyEncryption 调用（已集成快速引擎+缓存）"""
    from pqkds.falcon_aes_session_encryption import FalconAESSessionKeyEncryption

    security = int(getattr(node2, 'falcon_security_level', '512') or '512')
    falcon_svc = FalconAESSessionKeyEncryption(security_level=security)

    # 预热: 首次调用触发缓存加载（不计入测试）
    warmup_key = os.urandom(32)
    enc_w = falcon_svc.encrypt_aes_key_with_falcon(node2.node_id, warmup_key, node2.falcon_public_key)
    if enc_w['success']:
        falcon_svc.decrypt_aes_key_with_falcon(enc_w['ciphertext'], node2.falcon_private_key)
    print(f"\n  预热完成 (缓存已加载)")

    throughputs = []

    for r in range(1, ROUNDS + 1):
        latencies = []
        ok_count = 0
        for _ in range(COUNT):
            t0 = time.perf_counter()

            # 1. 生成随机 AES-256 密钥
            aes_key = os.urandom(32)
            # 2. Falcon 格密码加密（系统级调用）
            enc_result = falcon_svc.encrypt_aes_key_with_falcon(
                node2.node_id, aes_key, node2.falcon_public_key
            )
            assert enc_result['success'], f"Falcon 加密失败: {enc_result.get('message')}"
            # 3. Falcon 格密码解密（系统级调用）
            dec_result = falcon_svc.decrypt_aes_key_with_falcon(
                enc_result['ciphertext'], node2.falcon_private_key
            )
            assert dec_result['success'], f"Falcon 解密失败: {dec_result.get('message')}"

            t1 = time.perf_counter()
            # 4. 验证正确性
            recovered = dec_result['session_key']
            assert recovered == aes_key, "Falcon 解密验证失败!"
            ok_count += 1
            latencies.append((t1 - t0) * 1000)

        elapsed = sum(latencies) / 1000
        tp = ok_count / elapsed if elapsed > 0 else 0
        throughputs.append(tp)
        print(f"\n  第 {r}/{ROUNDS} 轮  Falcon-{security} (快速引擎+缓存):")
        print(f"    成功: {ok_count}/{COUNT}  耗时: {elapsed:.3f}s")
        print(f"    吞吐量: {tp:.1f} keys/sec  平均延迟: {statistics.mean(latencies):.2f} ms")

    return throughputs


def print_summary(name, throughputs):
    avg = statistics.mean(throughputs)
    lo, hi = min(throughputs), max(throughputs)
    passed = avg >= MIN_THROUGHPUT
    tag = "✅ 通过" if passed else "❌ 未达标"
    print(f"\n  [{name}]")
    print(f"    平均吞吐量: {avg:.1f} keys/sec  (最低 {lo:.1f}, 最高 {hi:.1f})")
    print(f"    要求: ≥ {MIN_THROUGHPUT} keys/sec  →  {tag}")
    return passed


def main():
    # ── Kyber 测试 ──
    k1, k2 = pick_kyber_pair()
    banner("Kyber 无证书格密码 Enc/Dec 完整加解密闭环测试", k1, k2)
    kyber_tp = run_kyber_benchmark(k2)

    # ── Falcon 测试 ──
    f1, f2 = pick_falcon_pair()
    banner("Falcon 格密码完整加解密闭环测试", f1, f2)
    falcon_tp = run_falcon_benchmark(f1, f2)

    # ── 汇总 ──
    print(f"\n{'━'*64}")
    print(f"  基准测试汇总 (每条 = 生成AES密钥 + 加密 + 解密 + 验证)")
    print(f"{'━'*64}")
    p1 = print_summary("Kyber 无证书格密码", kyber_tp)
    p2 = print_summary("Falcon 格密码", falcon_tp)
    print(f"{'━'*64}\n")

    sys.exit(0 if (p1 and p2) else 1)


if __name__ == '__main__':
    main()
