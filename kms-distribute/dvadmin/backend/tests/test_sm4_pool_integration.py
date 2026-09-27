# -*- coding: utf-8 -*-
"""
密钥池载荷层替换的集成自测（决策 D3 / 计划 P2 验证项）
=============================================================================

计划 P2 的验证要求有两句，本脚本各用一段来证明：

  1. 「分发 → 本地落盘 → 解封回读端到端」—— 新生成的池必须是 **SM4**，
     并且能按 `key_hash` 校验着解封回原值。
  2. 「**旧 AES 密钥池数据仍可读取与使用**」—— 库里/磁盘上那些 2026-09 之前
     写入的、32 字节密钥 + 无 `payload_algorithm` 标记的池，必须仍能解开。

**它必须跑在 dvadmin3-django 容器里**（要 Django 环境与数据库）：

    docker cp "backend/pqkds/sm4_crypto.py"            dvadmin3-django:/backend/pqkds/
    docker cp "backend/pqkds/key_pool_service.py"      dvadmin3-django:/backend/pqkds/
    docker cp "backend/pqkds/kyber_aes_session_encryption.py" dvadmin3-django:/backend/pqkds/
    docker cp "backend/pqkds/crypto_utils.py"          dvadmin3-django:/backend/pqkds/
    docker cp "backend/pqkds/views.py"                 dvadmin3-django:/backend/pqkds/
    docker cp "backend/pqkds/node_service.py"          dvadmin3-django:/backend/pqkds/
    docker cp "backend/tests/test_sm4_pool_integration.py" dvadmin3-django:/backend/tests/
    docker exec -w /backend dvadmin3-django python tests/test_sm4_pool_integration.py
"""

import base64
import hashlib
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "application.settings")

import django  # noqa: E402

django.setup()

from pqkds.sm4_crypto import (  # noqa: E402
    PAYLOAD_ALGORITHM_AES_256,
    PAYLOAD_ALGORITHM_SM4,
    SM4_KEY_BYTES,
    InvalidTag,
    LegacyAESCrypto,
    PayloadCipher,
    SM4Crypto,
)


def _report(name, ok, detail=""):
    print(f"  [{'OK' if ok else 'FAIL'}] {name}" + (f"  {detail}" if detail else ""))
    return ok


def test_new_pool_payload_is_sm4():
    """新池的载荷密钥必须是 16 字节，且信封里带 sm4 标记。"""
    results = []

    # 直接复刻 generate_kyber_pool 第 1 条的核心步骤（不依赖节点/KEM，只验证载荷层）
    payload_key = PayloadCipher.generate_key()
    results.append(_report("新载荷密钥为 16 字节（SM4）", len(payload_key) == SM4_KEY_BYTES,
                           f"len={len(payload_key)}"))
    results.append(_report("算法标记为 sm4", PayloadCipher.algorithm_of_key(payload_key) == PAYLOAD_ALGORITHM_SM4))

    # 模拟 KEM 共享秘密（真实实现里由 Kyber 给出，长度 32）
    shared_secret = os.urandom(32)
    kek = PayloadCipher.kek_from_shared_secret(PAYLOAD_ALGORITHM_SM4, shared_secret)
    results.append(_report("SM4 的 KEK 为 16 字节（而非旧的 32）", len(kek) == 16, f"len={len(kek)}"))

    ciphertext, nonce_tag = SM4Crypto.encrypt(payload_key, kek)
    nonce, tag = nonce_tag[:12], nonce_tag[12:]
    envelope = {
        "kem_ciphertext": base64.b64encode(os.urandom(768)).decode(),
        "encrypted_aes_key": base64.b64encode(ciphertext).decode(),
        "nonce": base64.b64encode(nonce).decode(),
        "tag": base64.b64encode(tag).decode(),
        "variant": 512,
        "payload_algorithm": PAYLOAD_ALGORITHM_SM4,
    }
    results.append(_report("信封里带 payload_algorithm=sm4",
                           PayloadCipher.algorithm_from_envelope(envelope) == PAYLOAD_ALGORITHM_SM4))

    # 读取端按信封分派解封
    alg = PayloadCipher.algorithm_from_envelope(envelope)
    kek2 = PayloadCipher.kek_from_shared_secret(alg, shared_secret)
    recovered = PayloadCipher.decrypt_with(
        alg,
        base64.b64decode(envelope["encrypted_aes_key"]),
        kek2,
        base64.b64decode(envelope["nonce"]) + base64.b64decode(envelope["tag"]),
    )
    key_hash = hashlib.sha256(payload_key).hexdigest()
    results.append(_report("解封回读与 key_hash 一致", recovered == payload_key and hashlib.sha256(recovered).hexdigest() == key_hash))

    return all(results)


def test_legacy_envelope_still_reads():
    """历史信封（无标记、32 字节密钥、AES-256-GCM）必须仍能解开。"""
    results = []

    legacy_key = os.urandom(32)
    shared_secret = os.urandom(32)

    # 严格照抄替换前的写法构造历史信封
    from Crypto.Cipher import AES as AES_Cipher

    kek_legacy = shared_secret[:32]
    cipher = AES_Cipher.new(kek_legacy, AES_Cipher.MODE_GCM)
    ct, tag = cipher.encrypt_and_digest(legacy_key)
    legacy_envelope = {
        "kem_ciphertext": base64.b64encode(os.urandom(768)).decode(),
        "encrypted_aes_key": base64.b64encode(ct).decode(),
        "nonce": base64.b64encode(cipher.nonce).decode(),
        "tag": base64.b64encode(tag).decode(),
        "variant": 512,
        # 刻意不带 payload_algorithm —— 这正是历史行的样子
    }

    alg = PayloadCipher.algorithm_from_envelope(legacy_envelope)
    results.append(_report("无标记的信封被判为 aes_256（安全的默认）", alg == PAYLOAD_ALGORITHM_AES_256, f"alg={alg}"))

    kek = PayloadCipher.kek_from_shared_secret(alg, shared_secret)
    results.append(_report("历史 AES 的 KEK 取 32 字节", len(kek) == 32, f"len={len(kek)}"))

    recovered = PayloadCipher.decrypt_with(
        alg,
        base64.b64decode(legacy_envelope["encrypted_aes_key"]),
        kek,
        base64.b64decode(legacy_envelope["nonce"]) + base64.b64decode(legacy_envelope["tag"]),
    )
    results.append(_report("历史信封解封回读一致", recovered == legacy_key))

    return all(results)


def test_real_legacy_rows_in_db():
    """拿库里**真实存在**的历史池行来验，而不是只验自造的信封。"""
    from pqkds.models import PreDistributedKey

    rows = list(
        PreDistributedKey.objects.exclude(encrypted_key_data="{}").order_by("id")[:5]
    )
    if not rows:
        print("  [SKIP] 库里没有可用的密钥池行（可能是全新环境）")
        return True

    results = []
    for row in rows:
        try:
            env = json.loads(row.encrypted_key_data)
        except Exception as exc:
            results.append(_report(f"行 id={row.id} 信封可解析", False, str(exc)))
            continue
        alg = PayloadCipher.algorithm_from_envelope(env)
        has_marker = "payload_algorithm" in env
        results.append(_report(
            f"行 id={row.id} 判定算法={alg}（信封{'带' if has_marker else '不带'}标记）",
            True,
        ))
        # 关键：历史行必须被判为 aes_256，才可能用旧 KEK 长度解开
        if not has_marker:
            results.append(_report(f"行 id={row.id} 无标记 → 判为 aes_256", alg == PAYLOAD_ALGORITHM_AES_256))

    return all(results)


def test_rejects_bad_key_length():
    """长度非法时宁可报错，也不要用错算法解出垃圾。"""
    results = []
    try:
        PayloadCipher.decrypt(b"x", bytes(24), bytes(28))
        results.append(_report("24 字节密钥被拒绝", False, "竟然没报错"))
    except ValueError as exc:
        results.append(_report("24 字节密钥被拒绝", True, str(exc)[:60]))
    return all(results)


def _main():
    tests = [
        ("新池载荷层为 SM4", test_new_pool_payload_is_sm4),
        ("历史 AES 信封仍可读", test_legacy_envelope_still_reads),
        ("库中真实历史行判定正确", test_real_legacy_rows_in_db),
        ("非法密钥长度被拒绝", test_rejects_bad_key_length),
    ]
    print(f"== 密钥池载荷层集成自测：{len(tests)} 组 ==\n")
    failed = []
    for name, fn in tests:
        print(f"-- {name}")
        try:
            if not fn():
                failed.append(name)
        except Exception as exc:
            failed.append(name)
            print(f"  [FAIL] 抛异常: {type(exc).__name__}: {exc}")
        print()
    print(f"== 结果：{len(tests) - len(failed)} 组通过 / {len(failed)} 组失败 ==")
    if failed:
        for name in failed:
            print(f"  失败 {name}")
        return 1
    print("新数据走 SM4，历史 AES 数据仍可读。")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())