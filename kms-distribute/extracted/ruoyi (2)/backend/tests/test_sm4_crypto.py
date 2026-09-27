# -*- coding: utf-8 -*-
"""
SM4 载荷加密的自测（决策 D3 / 计划 P2 验证项）
=============================================================================

**为什么先写这个再改业务代码**：整个 P2 的风险都压在"SM4 到底算得对不对"上。
先用手抄不了的标准向量把密码学底座钉死，后面替换十个调用点时才有立足点。

覆盖：
  1. GB/T 32907-2016 附录 A.1 单块向量（key 与明文相同）
  2. GB/T 32907-2016 附录 A.2 连续加密 10⁶ 次向量
  3. GCM 往返（空明文 / 16 字节 / 大报文）
  4. **认证失败必须抛异常**：密文篡改、标签篡改、错误密钥、错误 AAD
  5. 密钥长度约束（SM4 只接受 16 字节）
  6. **历史 AES-256 数据仍可解开**（P2 的硬性验证项）
  7. `PayloadCipher` 按密钥长度正确分派

运行方式（镜像里的代码是构建期烤进去的，所以用 docker cp 送进去跑）：

    docker cp "backend/pqkds/sm4_crypto.py"            dvadmin3-django:/backend/pqkds/
    docker cp "backend/tests/test_sm4_crypto.py"       dvadmin3-django:/backend/tests/
    docker exec -w /backend dvadmin3-django python tests/test_sm4_crypto.py

它同时兼容 pytest（函数名都是 test_*，断言都是裸 assert）。
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pqkds.sm4_crypto import (  # noqa: E402
    GCM_IV_BYTES,
    GCM_TAG_BYTES,
    LEGACY_AES_KEY_BYTES,
    LEGACY_GCM_NONCE_BYTES,
    PAYLOAD_ALGORITHM_AES_256,
    PAYLOAD_ALGORITHM_SM4,
    SM4_GB_VECTOR_1E6_CIPHERTEXT,
    SM4_GB_VECTOR_1E6_ROUNDS,
    SM4_GB_VECTOR_CIPHERTEXT,
    SM4_GB_VECTOR_KEY,
    SM4_GB_VECTOR_PLAINTEXT,
    SM4_KEY_BYTES,
    InvalidTag,
    LegacyAESCrypto,
    PayloadCipher,
    SM4Crypto,
)


# ---------------------------------------------------------------------------
# 1 / 2. 国标标准向量
# ---------------------------------------------------------------------------
def test_gb_vector_single_block():
    """GB/T 32907-2016 附录 A.1：单块 ECB 加密结果必须逐字节一致。"""
    got = SM4Crypto.ecb_encrypt_block(SM4_GB_VECTOR_PLAINTEXT, SM4_GB_VECTOR_KEY)
    assert got == SM4_GB_VECTOR_CIPHERTEXT, (
        f"单块向量不匹配：期望 {SM4_GB_VECTOR_CIPHERTEXT.hex()}，实际 {got.hex()}"
    )


def test_gb_vector_iterated_1e6():
    """GB/T 32907-2016 附录 A.2：连续加密 10⁶ 次的结果必须一致。

    这条比单块向量强得多 —— 任何一轮密钥扩展或轮函数写错都会累积成完全不同的结果。
    """
    block = SM4_GB_VECTOR_PLAINTEXT
    key = SM4_GB_VECTOR_KEY
    for _ in range(SM4_GB_VECTOR_1E6_ROUNDS):
        block = SM4Crypto.ecb_encrypt_block(block, key)
    assert block == SM4_GB_VECTOR_1E6_CIPHERTEXT, (
        f"10⁶ 次迭代向量不匹配：期望 {SM4_GB_VECTOR_1E6_CIPHERTEXT.hex()}，实际 {block.hex()}"
    )


# ---------------------------------------------------------------------------
# 3. GCM 往返
# ---------------------------------------------------------------------------
def test_gcm_roundtrip_various_sizes():
    key = SM4Crypto.generate_key()
    for size in (0, 1, 15, 16, 17, 1024, 65536):
        plaintext = os.urandom(size)
        ciphertext, nonce_tag = SM4Crypto.encrypt(plaintext, key)
        assert len(nonce_tag) == GCM_IV_BYTES + GCM_TAG_BYTES
        assert len(ciphertext) == size
        assert SM4Crypto.decrypt(ciphertext, key, nonce_tag) == plaintext, f"size={size} 往返失败"


def test_gcm_roundtrip_with_aad():
    key = SM4Crypto.generate_key()
    aad = b"pool:pool_dist_abc|index:7"
    ciphertext, nonce_tag = SM4Crypto.encrypt(b"session-key-material", key, aad=aad)
    assert SM4Crypto.decrypt(ciphertext, key, nonce_tag, aad=aad) == b"session-key-material"


def test_each_encryption_uses_fresh_iv():
    """同一明文两次加密必须得到不同密文（否则 IV 复用，GCM 会被彻底攻破）。"""
    key = SM4Crypto.generate_key()
    a = SM4Crypto.encrypt(b"same plaintext", key)
    b = SM4Crypto.encrypt(b"same plaintext", key)
    assert a[0] != b[0], "两次加密的密文相同 —— IV 没有随机化"
    assert a[1][:GCM_IV_BYTES] != b[1][:GCM_IV_BYTES], "两次加密的 IV 相同"


# ---------------------------------------------------------------------------
# 4. 认证失败必须抛异常（而不是返回垃圾明文）
# ---------------------------------------------------------------------------
def _expect_invalid_tag(fn, what):
    try:
        fn()
    except InvalidTag:
        return
    except Exception as exc:  # 其它异常也算"没有静默通过"，但要报出来便于区分
        raise AssertionError(f"{what} 抛了非 InvalidTag 的异常：{type(exc).__name__}: {exc}") from exc
    raise AssertionError(f"{what} 竟然没有报错 —— 认证加密失效")


def test_tampered_ciphertext_rejected():
    key = SM4Crypto.generate_key()
    ciphertext, nonce_tag = SM4Crypto.encrypt(b"important payload", key)
    bad = bytearray(ciphertext)
    bad[0] ^= 0x01
    _expect_invalid_tag(lambda: SM4Crypto.decrypt(bytes(bad), key, nonce_tag), "篡改密文")


def test_tampered_tag_rejected():
    key = SM4Crypto.generate_key()
    ciphertext, nonce_tag = SM4Crypto.encrypt(b"important payload", key)
    bad = bytearray(nonce_tag)
    bad[-1] ^= 0x01
    _expect_invalid_tag(lambda: SM4Crypto.decrypt(ciphertext, key, bytes(bad)), "篡改标签")


def test_tampered_iv_rejected():
    key = SM4Crypto.generate_key()
    ciphertext, nonce_tag = SM4Crypto.encrypt(b"important payload", key)
    bad = bytearray(nonce_tag)
    bad[0] ^= 0x01  # 改 IV
    _expect_invalid_tag(lambda: SM4Crypto.decrypt(ciphertext, key, bytes(bad)), "篡改 IV")


def test_wrong_key_rejected():
    key = SM4Crypto.generate_key()
    other = SM4Crypto.generate_key()
    ciphertext, nonce_tag = SM4Crypto.encrypt(b"important payload", key)
    _expect_invalid_tag(lambda: SM4Crypto.decrypt(ciphertext, other, nonce_tag), "错误密钥")


def test_wrong_aad_rejected():
    key = SM4Crypto.generate_key()
    ciphertext, nonce_tag = SM4Crypto.encrypt(b"important payload", key, aad=b"ctx-A")
    _expect_invalid_tag(
        lambda: SM4Crypto.decrypt(ciphertext, key, nonce_tag, aad=b"ctx-B"), "错误 AAD"
    )


def test_missing_aad_rejected():
    key = SM4Crypto.generate_key()
    ciphertext, nonce_tag = SM4Crypto.encrypt(b"important payload", key, aad=b"ctx-A")
    _expect_invalid_tag(lambda: SM4Crypto.decrypt(ciphertext, key, nonce_tag), "缺少 AAD")


# ---------------------------------------------------------------------------
# 5. 密钥长度约束
# ---------------------------------------------------------------------------
def test_sm4_rejects_non_16_byte_keys():
    for bad_len in (8, 15, 17, 24, 32):
        wrong = bytes(bad_len)
        try:
            SM4Crypto.encrypt(b"x", wrong)
        except ValueError:
            continue
        raise AssertionError(f"SM4 竟然接受了 {bad_len} 字节的密钥")


def test_generated_key_is_16_bytes():
    key = SM4Crypto.generate_key()
    assert len(key) == SM4_KEY_BYTES, f"新密钥应为 {SM4_KEY_BYTES} 字节，实际 {len(key)}"
    assert len(set(SM4Crypto.generate_key() for _ in range(8))) == 8, "生成的密钥出现重复"


# ---------------------------------------------------------------------------
# 6. 历史 AES-256 数据仍可解开（P2 硬性验证项）
# ---------------------------------------------------------------------------
def test_legacy_aes_data_still_decrypts():
    """模拟"库里那批 32 字节密钥的老数据"：用旧实现加密，必须能用新分派器解开。"""
    legacy_key = os.urandom(LEGACY_AES_KEY_BYTES)
    payload = b"\x11" * SM4_KEY_BYTES  # 例如一把旧池里的 SM4/AES 会话密钥

    # 严格沿用替换前的旧代码路径构造历史数据
    ct_legacy, nt_legacy = LegacyAESCrypto.encrypt(payload, legacy_key)
    assert len(nt_legacy) == LEGACY_GCM_NONCE_BYTES + GCM_TAG_BYTES

    # 新的统一入口应当按密钥长度把它路由到旧实现
    assert PayloadCipher.decrypt(ct_legacy, legacy_key, nt_legacy) == payload


def test_legacy_aes_matches_original_implementation():
    """与替换前 `pqkds.crypto_utils.AESCrypto` 的实现逐字节对齐。

    这是"旧数据可读"的真正保证：不是"我们自己能解开自己"，而是
    **与历史实现产生完全相同的密文/信封布局**。
    """
    from Crypto.Cipher import AES  # 替换前用的就是 pycryptodome

    key = os.urandom(32)
    data = b"historical pool payload"

    # 替换前的原始实现（原样照抄，用于对照）
    original = AES.new(key, AES.MODE_GCM)
    original_ct, original_tag = original.encrypt_and_digest(data)
    original_nonce_tag = original.nonce + original_tag

    assert len(original.nonce) == LEGACY_GCM_NONCE_BYTES, (
        f"pycryptodome 的 AES-GCM 默认 nonce 变成 {len(original.nonce)} 字节了，"
        f"旧信封布局假设失效，需同步调整 LegacyAESCrypto"
    )
    ct, nt = LegacyAESCrypto.encrypt(data, key)
    assert len(ct) == len(original_ct)
    assert len(nt) == len(original_nonce_tag)
    # nonce 每次都随机，只能校验"用对照的信封能解出原文"
    assert LegacyAESCrypto.decrypt(original_ct, key, original_nonce_tag) == data
    ct2 = AES.new(key, AES.MODE_GCM, nonce=nt[:LEGACY_GCM_NONCE_BYTES])
    assert ct2.decrypt_and_verify(ct, nt[LEGACY_GCM_NONCE_BYTES:]) == data


# ---------------------------------------------------------------------------
# 7. PayloadCipher 分派
# ---------------------------------------------------------------------------
def test_payload_cipher_dispatches_by_key_length():
    sm4_key = PayloadCipher.generate_key()
    assert len(sm4_key) == SM4_KEY_BYTES, "新载荷密钥必须是 16 字节（SM4）"
    assert PayloadCipher.algorithm_of_key(sm4_key) == PAYLOAD_ALGORITHM_SM4
    assert PayloadCipher.cipher_for_key(sm4_key) is SM4Crypto

    legacy_key = os.urandom(LEGACY_AES_KEY_BYTES)
    assert PayloadCipher.algorithm_of_key(legacy_key) == PAYLOAD_ALGORITHM_AES_256
    assert PayloadCipher.cipher_for_key(legacy_key) is LegacyAESCrypto


def test_payload_cipher_rejects_ambiguous_key_length():
    for bad_len in (0, 8, 24, 64):
        try:
            PayloadCipher.algorithm_of_key(bytes(bad_len))
        except ValueError:
            continue
        raise AssertionError(f"{bad_len} 字节的密钥竟被判定了算法 —— 分派规则不够严格")


def test_payload_cipher_nonce_tag_bytes():
    assert PayloadCipher.nonce_tag_bytes(os.urandom(16)) == GCM_IV_BYTES + GCM_TAG_BYTES
    assert PayloadCipher.nonce_tag_bytes(os.urandom(32)) == LEGACY_GCM_NONCE_BYTES + GCM_TAG_BYTES


def test_payload_cipher_roundtrip_both_algorithms():
    payload = os.urandom(16)  # 一把典型的会话密钥
    for key in (PayloadCipher.generate_key(), os.urandom(LEGACY_AES_KEY_BYTES)):
        ct, nt = PayloadCipher.encrypt(payload, key)
        assert PayloadCipher.decrypt(ct, key, nt) == payload


# ---------------------------------------------------------------------------
# 自运行入口（不依赖 pytest）
# ---------------------------------------------------------------------------
def _main() -> int:
    tests = [
        (name, obj)
        for name, obj in sorted(globals().items())
        if name.startswith("test_") and callable(obj)
    ]
    failed = []
    print(f"== SM4 自测：{len(tests)} 项 ==\n")
    for name, fn in tests:
        try:
            fn()
        except Exception as exc:
            failed.append((name, exc))
            print(f"  [FAIL] {name}\n         {type(exc).__name__}: {exc}")
        else:
            print(f"  [OK]   {name}")
    print(f"\n== 结果：{len(tests) - len(failed)} 通过 / {len(failed)} 失败 ==")
    if failed:
        for name, exc in failed:
            print(f"  失败项 {name}: {exc}")
        return 1
    print("SM4 密码学底座通过全部国标向量与认证失败用例。")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
