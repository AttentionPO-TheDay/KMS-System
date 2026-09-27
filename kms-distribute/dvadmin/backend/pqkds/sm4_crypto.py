# -*- coding: utf-8 -*-
"""
国密 SM4 载荷加密（决策 D3）
=============================================================================

背景
----
本系统原先用 **AES-256-GCM** 做 DEM（数据封装）层，对称密钥是 32 字节
（`os.urandom(32)` / `secrets.token_bytes(32)`）。D3 要求对称层全部换成
**SM4**，密钥随之变为 16 字节。

为什么用 `cryptography` 而不是 gmssl / pycryptodome
---------------------------------------------------
* `pycryptodome 3.20.0`（镜像里已装）**没有 SM4**；
* `gmssl` 未安装，且要装就得重建镜像、引入一个新的第三方密码库；
* `cryptography`（Dockerfile 里本来就显式安装了）**自带 `algorithms.SM4`**，
  并且实测**通过 GB/T 32907-2016 的两个标准向量**（单块 + 10⁶ 次迭代）。

因此本次替换**不需要新增任何依赖**。

历史数据兼容
------------
计划 P2 的硬性验证项之一是「**旧 AES 密钥池数据仍可读取与使用**」。分派规则用
**密钥长度**：

===========================  ===================================
密钥长度                      算法
===========================  ===================================
**16 字节**                   SM4-GCM（新写入的数据）
**32 字节**                   旧 AES-256-GCM（历史数据）
===========================  ===================================

本项目历史上所有对称密钥都是 `os.urandom(32)` / `secrets.token_bytes(32)`，
没有 16 字节的 AES 密钥，所以这个判据**没有歧义**。
（`cryptography.algorithms.SM4` 只接受 16 字节，AES 只接受 16/24/32 字节，
两侧都不会静默接受对方的密钥，这一层由库本身兜底。）

信封格式
--------
`nonce_tag` 是"随机数 + 认证标签"的拼接：

* SM4-GCM：``iv(12) || tag(16)``  → 28 字节
* 旧 AES-GCM：``nonce(16) || tag(16)`` → 32 字节（沿用 pycryptodome 的默认 nonce 长度）

两者长度不同，且解密时已按密钥长度选定算法，所以**不需要额外的版本字节**。

安全说明
--------
GCM 是认证加密：密文被篡改时 `decrypt` 会抛 `InvalidTag`，**绝不返回明文**。
调用方不要吞掉这个异常——它是完整性校验失败的唯一信号。
"""

from __future__ import annotations

import os
from typing import Optional, Tuple

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

__all__ = [
    "SM4_KEY_BYTES",
    "LEGACY_AES_KEY_BYTES",
    "GCM_IV_BYTES",
    "LEGACY_GCM_NONCE_BYTES",
    "GCM_TAG_BYTES",
    "PAYLOAD_ALGORITHM_SM4",
    "PAYLOAD_ALGORITHM_AES_256",
    "SM4_GB_VECTOR_KEY",
    "SM4_GB_VECTOR_PLAINTEXT",
    "SM4_GB_VECTOR_CIPHERTEXT",
    "SM4_GB_VECTOR_1E6_CIPHERTEXT",
    "SM4Crypto",
    "LegacyAESCrypto",
    "PayloadCipher",
    "InvalidTag",
    "kek_for_algorithm",
]

#: 便捷别名：`kek_for_algorithm('sm4', ss)`
kek_for_algorithm = None  # 在文件末尾绑定，避免前向引用

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------
SM4_KEY_BYTES = 16
LEGACY_AES_KEY_BYTES = 32
GCM_IV_BYTES = 12
GCM_TAG_BYTES = 16
# pycryptodome 的 AES-GCM 默认 nonce 是 16 字节，旧数据按这个长度解
LEGACY_GCM_NONCE_BYTES = 16

#: 写入 `dvadmin_pqkds_pre_distributed_keys.payload_algorithm` 的取值
PAYLOAD_ALGORITHM_SM4 = "sm4"
PAYLOAD_ALGORITHM_AES_256 = "aes_256"

# ---------------------------------------------------------------------------
# GB/T 32907-2016《信息安全技术 SM4 分组密码算法》标准测试向量
# ---------------------------------------------------------------------------
#: 附录 A.1：密钥与明文相同
SM4_GB_VECTOR_KEY = bytes.fromhex("0123456789abcdeffedcba9876543210")
SM4_GB_VECTOR_PLAINTEXT = bytes.fromhex("0123456789abcdeffedcba9876543210")
#: 附录 A.1：单次加密的期望密文
SM4_GB_VECTOR_CIPHERTEXT = bytes.fromhex("681edf34d206965e86b3e94f536e4246")
#: 附录 A.2：对同一分组连续加密 10⁶ 次的期望密文
SM4_GB_VECTOR_1E6_CIPHERTEXT = bytes.fromhex("595298c7c6fd271f0402f804c33d3f66")
SM4_GB_VECTOR_1E6_ROUNDS = 1_000_000


def _require_len(value: bytes, expected: int, label: str) -> bytes:
    if not isinstance(value, (bytes, bytearray)):
        raise TypeError(f"{label} 必须是 bytes，收到 {type(value).__name__}")
    if len(value) != expected:
        raise ValueError(f"{label} 长度必须为 {expected} 字节，收到 {len(value)}")
    return bytes(value)


class SM4Crypto:
    """国密 SM4-GCM 加解密（新数据的唯一算法）。"""

    #: 本算法对应的 `payload_algorithm` 标记
    algorithm = PAYLOAD_ALGORITHM_SM4
    key_bytes = SM4_KEY_BYTES

    @staticmethod
    def generate_key() -> bytes:
        """生成一把 SM4 密钥（16 字节，密码学安全随机）。"""
        return os.urandom(SM4_KEY_BYTES)

    @staticmethod
    def encrypt(data: bytes, key: bytes, aad: Optional[bytes] = None) -> Tuple[bytes, bytes]:
        """加密并认证。

        返回 ``(ciphertext, nonce_tag)``，其中 ``nonce_tag = iv(12) || tag(16)``。
        """
        _require_len(key, SM4_KEY_BYTES, "SM4 密钥")
        iv = os.urandom(GCM_IV_BYTES)
        encryptor = Cipher(algorithms.SM4(key), modes.GCM(iv)).encryptor()
        if aad:
            encryptor.authenticate_additional_data(aad)
        ciphertext = encryptor.update(data) + encryptor.finalize()
        return ciphertext, iv + encryptor.tag

    @staticmethod
    def decrypt(ciphertext: bytes, key: bytes, nonce_tag: bytes, aad: Optional[bytes] = None) -> bytes:
        """解密并校验完整性；被篡改时抛 `InvalidTag`。"""
        _require_len(key, SM4_KEY_BYTES, "SM4 密钥")
        expected = GCM_IV_BYTES + GCM_TAG_BYTES
        _require_len(nonce_tag, expected, "SM4 nonce_tag")
        iv = nonce_tag[:GCM_IV_BYTES]
        tag = nonce_tag[GCM_IV_BYTES:]
        decryptor = Cipher(algorithms.SM4(key), modes.GCM(iv, tag)).decryptor()
        if aad:
            decryptor.authenticate_additional_data(aad)
        return decryptor.update(ciphertext) + decryptor.finalize()

    @staticmethod
    def ecb_encrypt_block(block: bytes, key: bytes) -> bytes:
        """单分组 ECB 加密，**仅供标准向量自测使用**。

        生产路径一律走 GCM。ECB 会泄露明文分组结构，不得用于业务数据。
        """
        _require_len(key, SM4_KEY_BYTES, "SM4 密钥")
        _require_len(block, 16, "SM4 分组")
        encryptor = Cipher(algorithms.SM4(key), modes.ECB()).encryptor()
        return encryptor.update(block) + encryptor.finalize()


class LegacyAESCrypto:
    """历史 AES-256-GCM 实现，**只用于读取既有数据**。

    行为与替换前的 `pqkds.crypto_utils.AESCrypto` 完全一致（含 16 字节 nonce），
    以保证 2026-09 之前写入的密钥池仍能解开。新数据一律走 :class:`SM4Crypto`。
    """

    algorithm = PAYLOAD_ALGORITHM_AES_256
    key_bytes = LEGACY_AES_KEY_BYTES

    @staticmethod
    def generate_key() -> bytes:
        """**不要在新代码里调用**：保留它只是为了对齐旧实现的接口。"""
        return os.urandom(LEGACY_AES_KEY_BYTES)

    @staticmethod
    def encrypt(data: bytes, key: bytes, aad: Optional[bytes] = None) -> Tuple[bytes, bytes]:
        """保留旧实现的加密路径，便于测试里构造"历史数据"。"""
        _require_len(key, LEGACY_AES_KEY_BYTES, "AES-256 密钥")
        from Crypto.Cipher import AES  # pycryptodome；仅历史路径需要

        cipher = AES.new(key, AES.MODE_GCM)
        if aad:
            cipher.update(aad)
        ciphertext, tag = cipher.encrypt_and_digest(data)
        return ciphertext, cipher.nonce + tag

    @staticmethod
    def decrypt(ciphertext: bytes, key: bytes, nonce_tag: bytes, aad: Optional[bytes] = None) -> bytes:
        _require_len(key, LEGACY_AES_KEY_BYTES, "AES-256 密钥")
        expected = LEGACY_GCM_NONCE_BYTES + GCM_TAG_BYTES
        _require_len(nonce_tag, expected, "AES nonce_tag")
        from Crypto.Cipher import AES  # pycryptodome

        nonce = nonce_tag[:LEGACY_GCM_NONCE_BYTES]
        tag = nonce_tag[LEGACY_GCM_NONCE_BYTES:]
        cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
        if aad:
            cipher.update(aad)
        return cipher.decrypt_and_verify(ciphertext, tag)


class PayloadCipher:
    """载荷加解密分派器：新数据用 SM4，历史数据用 AES-256。

    这是替换期间**唯一**应该被业务代码调用的入口。业务侧只要拿
    :meth:`generate_key` 产出的密钥，就不必关心用的是哪种算法；
    而读取历史数据时，密钥长度会自动把请求路由到旧实现上。
    """

    @staticmethod
    def generate_key() -> bytes:
        """生成新载荷密钥 —— 永远是 SM4（16 字节）。"""
        return SM4Crypto.generate_key()

    @staticmethod
    def algorithm_of_key(key: bytes) -> str:
        """按密钥长度判断该用哪种算法。

        * 16 → ``sm4``
        * 32 → ``aes_256``（历史数据）

        其他长度直接报错：宁可失败，也不要用错算法解出垃圾。
        """
        if key is None:
            raise ValueError("密钥不能为空")
        length = len(key)
        if length == SM4_KEY_BYTES:
            return PAYLOAD_ALGORITHM_SM4
        if length == LEGACY_AES_KEY_BYTES:
            return PAYLOAD_ALGORITHM_AES_256
        raise ValueError(
            f"不支持的载荷密钥长度 {length}；应为 {SM4_KEY_BYTES}（SM4）或 "
            f"{LEGACY_AES_KEY_BYTES}（历史 AES-256）"
        )

    @staticmethod
    def cipher_for_key(key: bytes):
        return SM4Crypto if PayloadCipher.algorithm_of_key(key) == PAYLOAD_ALGORITHM_SM4 else LegacyAESCrypto

    @staticmethod
    def encrypt(data: bytes, key: bytes, aad: Optional[bytes] = None) -> Tuple[bytes, bytes]:
        return PayloadCipher.cipher_for_key(key).encrypt(data, key, aad)

    @staticmethod
    def decrypt(ciphertext: bytes, key: bytes, nonce_tag: bytes, aad: Optional[bytes] = None) -> bytes:
        return PayloadCipher.cipher_for_key(key).decrypt(ciphertext, key, nonce_tag, aad)

    @staticmethod
    def nonce_tag_bytes(key: bytes) -> int:
        """该密钥对应信封里 `nonce_tag` 应有的长度，供读取端做长度校验。"""
        return (
            GCM_IV_BYTES + GCM_TAG_BYTES
            if PayloadCipher.algorithm_of_key(key) == PAYLOAD_ALGORITHM_SM4
            else LEGACY_GCM_NONCE_BYTES + GCM_TAG_BYTES
        )

    # -----------------------------------------------------------------------
    # 显式指定算法的接口
    # -----------------------------------------------------------------------
    # 为什么需要它们：上面那套"按密钥长度分派"只适用于**密钥本身就是待判据**的场景
    # （例如节点本地 JSON 里存的明文载荷密钥）。
    #
    # 但密钥池信封里被加密的载荷密钥是**用 KEM 共享秘密派生出的 KEK 包起来的**，
    # 而 KEK 的长度是**代码决定的、不从数据里来**：
    #   SM4    → KEK = shared_secret[:16]
    #   旧 AES → KEK = shared_secret[:32]
    # 解密时无法从密文反推 KEK 该取多长，因此必须由**信封里的显式标记**（或数据库列
    # `payload_algorithm`）来决定用哪种算法。缺少该标记 = 历史行 = AES-256。
    # -----------------------------------------------------------------------

    @staticmethod
    def normalize_algorithm(value) -> str:
        """把各种历史写法归一成 `sm4` / `aes_256`。

        缺省（None/空/未知）一律视为 **`aes_256`**：所有没有显式标记的数据
        都是 2026-09 之前用 AES-256 写下的，这是唯一安全的默认。
        """
        if value is None:
            return PAYLOAD_ALGORITHM_AES_256
        text = str(value).strip().lower().replace("-", "_")
        if text in ("sm4", "gm_sm4", "sm4_gcm"):
            return PAYLOAD_ALGORITHM_SM4
        return PAYLOAD_ALGORITHM_AES_256

    @staticmethod
    def algorithm_from_envelope(envelope) -> str:
        """从密钥池信封字典里读算法标记；读不到即视为历史 AES-256 行。"""
        if not isinstance(envelope, dict):
            return PAYLOAD_ALGORITHM_AES_256
        return PayloadCipher.normalize_algorithm(
            envelope.get("payload_algorithm") or envelope.get("payloadAlgorithm")
        )

    @staticmethod
    def kek_from_shared_secret(algorithm, shared_secret: bytes) -> bytes:
        """按算法从 KEM 共享秘密里取 KEK。

        KEM 共享秘密本身是均匀随机的，取前 16 / 32 字节即可用作 KEK。
        """
        if not isinstance(shared_secret, (bytes, bytearray)) or len(shared_secret) < LEGACY_AES_KEY_BYTES:
            raise ValueError(f"KEM 共享秘密长度不足：{len(shared_secret) if shared_secret else 0}")
        if PayloadCipher.normalize_algorithm(algorithm) == PAYLOAD_ALGORITHM_SM4:
            return bytes(shared_secret[:SM4_KEY_BYTES])
        return bytes(shared_secret[:LEGACY_AES_KEY_BYTES])

    @staticmethod
    def encrypt_with(algorithm, data: bytes, key: bytes,
                     aad: Optional[bytes] = None) -> Tuple[bytes, bytes]:
        """用**指定**算法加密（不做长度推断）。"""
        cipher = SM4Crypto if PayloadCipher.normalize_algorithm(algorithm) == PAYLOAD_ALGORITHM_SM4 else LegacyAESCrypto
        return cipher.encrypt(data, key, aad)

    @staticmethod
    def decrypt_with(algorithm, ciphertext: bytes, key: bytes, nonce_tag: bytes,
                     aad: Optional[bytes] = None) -> bytes:
        """用**指定**算法解密（不做长度推断）。"""
        cipher = SM4Crypto if PayloadCipher.normalize_algorithm(algorithm) == PAYLOAD_ALGORITHM_SM4 else LegacyAESCrypto
        return cipher.decrypt(ciphertext, key, nonce_tag, aad)


# 便捷别名（在类定义之后绑定）
kek_for_algorithm = PayloadCipher.kek_from_shared_secret
