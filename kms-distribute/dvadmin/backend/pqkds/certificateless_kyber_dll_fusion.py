"""
无证书Kyber密钥生成与DLL融合模块

将图片中的无证书密钥生成算法（Setup, PartialKeyGen, SetSecretValue, SetSK, SetPK）
与Kyber DLL的KEM功能（keypair_derand, enc, dec）真正结合。

设计原理：
- 无证书层：在Z_q^m上执行无证书密钥生成算法，产生无证书私钥sk和公钥pk
- DLL桥接层：将无证书私钥sk通过SHAKE-256确定性派生为64字节coins，
  喂入DLL的keypair_derand函数，生成标准Kyber KEM密钥对
- KEM层：使用DLL生成的标准Kyber密钥对执行encaps/decaps

这样实现了：
1. 密钥生成遵循无证书流程（KGC部分私钥 + 用户秘密值 = 完整密钥）
2. 无证书私钥与DLL密钥对之间存在确定性的密码学绑定
3. 加解密使用DLL的高性能C实现
"""

import ctypes
import os
import hashlib
import numpy as np
import logging
import json
import base64
import struct
from typing import Dict, Any, Tuple
from pathlib import Path

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent

KYBER_LIB_DIR = BASE_DIR / "kyber"
KYBER_REF_LIB_DIR = KYBER_LIB_DIR / "ref" / "lib"


_kyber_dependency_handles = []


def _kyber_library_candidates(variant: int):
    name = f"libpqcrystals_kyber{variant}_ref"
    return [
        KYBER_REF_LIB_DIR / f"{name}.so",
        KYBER_LIB_DIR / f"{name}.so",
        KYBER_LIB_DIR / f"{name}.dll",
    ]


def _preload_kyber_dependencies(errors):
    if _kyber_dependency_handles:
        return
    fips_path = KYBER_REF_LIB_DIR / "libpqcrystals_fips202_ref.so"
    if not fips_path.exists():
        return
    try:
        mode = getattr(ctypes, "RTLD_GLOBAL", 0)
        _kyber_dependency_handles.append(ctypes.CDLL(str(fips_path), mode=mode))
        logger.info(f"[DLL] 成功预加载 {fips_path}")
    except OSError as exc:
        errors.append(f"{fips_path}: {exc}")


# Kyber参数表: variant -> (pk_bytes, sk_bytes, ct_bytes, ss_bytes, coins_bytes)
KYBER_PARAMS = {
    512:  (800,  1632, 768,  32, 64),
    768:  (1184, 2400, 1088, 32, 64),
    1024: (1568, 3168, 1568, 32, 64),
}


def _shake256(data: bytes, output_len: int) -> bytes:
    """使用SHAKE-256从任意长度输入派生固定长度输出"""
    from hashlib import shake_256
    return shake_256(data).digest(output_len)


class CertificatelessKyberDLLFusion:
    """
    无证书Kyber密钥生成与DLL融合的核心类。

    完整实现图片中的无证书算法五个阶段，并通过确定性派生
    将无证书密钥绑定到DLL的标准Kyber KEM密钥对。
    """

    def __init__(self, variant: int = 512, n: int = 512, m: int = 1024,
                 q: int = 12289, sigma: float = 1.17):
        """
        初始化融合系统。

        Args:
            variant: Kyber安全级别 (512/768/1024)，决定DLL使用哪个变体
            n: 无证书算法的矩阵行数
            m: 无证书算法的矩阵列数
            q: 无证书算法的模数
            sigma: 离散高斯分布参数
        """
        if variant not in KYBER_PARAMS:
            raise ValueError(f"不支持的Kyber变体: {variant}，必须是512/768/1024")

        self.variant = variant
        self.n = n
        self.m = m
        self.q = q
        self.sigma = sigma

        # Kyber DLL参数
        params = KYBER_PARAMS[variant]
        self.pk_bytes = params[0]
        self.sk_bytes = params[1]
        self.ct_bytes = params[2]
        self.ss_bytes = params[3]
        self.coins_bytes = params[4]

        # 加载DLL
        self.dll = self._load_dll()

        # 绑定DLL函数
        self._bind_dll_functions()

        # 系统参数缓存
        self._A = None
        self._S_0 = None
        self._U_0 = None

        logger.info(
            f"[CertificatelessKyberDLLFusion] 初始化完成: "
            f"variant=Kyber-{variant}, n={n}, m={m}, q={q}, σ={sigma}"
        )

    def _load_dll(self) -> ctypes.CDLL:
        """加载对应变体的Kyber动态库"""
        errors = []
        _preload_kyber_dependencies(errors)
        for lib_path in _kyber_library_candidates(self.variant):
            if not lib_path.exists():
                continue
            try:
                dll = ctypes.CDLL(str(lib_path))
                logger.info(f"[DLL] 成功加载 {lib_path}")
                return dll
            except OSError as exc:
                errors.append(f"{lib_path}: {exc}")
        raise FileNotFoundError(f"Kyber动态库未找到或不可加载: {'; '.join(errors) or self.variant}")

    def _bind_dll_functions(self):
        """绑定DLL中的函数接口"""
        prefix = f"pqcrystals_kyber{self.variant}_ref"

        # keypair_derand: 确定性密钥生成
        self._keypair_derand = getattr(self.dll, f"{prefix}_keypair_derand")
        self._keypair_derand.argtypes = [
            ctypes.POINTER(ctypes.c_ubyte),  # pk
            ctypes.POINTER(ctypes.c_ubyte),  # sk
            ctypes.POINTER(ctypes.c_ubyte),  # coins (64 bytes)
        ]
        self._keypair_derand.restype = ctypes.c_int

        # enc: 封装
        self._enc = getattr(self.dll, f"{prefix}_enc")
        self._enc.argtypes = [
            ctypes.POINTER(ctypes.c_ubyte),  # ct
            ctypes.POINTER(ctypes.c_ubyte),  # ss
            ctypes.POINTER(ctypes.c_ubyte),  # pk
        ]
        self._enc.restype = ctypes.c_int

        # dec: 解封装
        self._dec = getattr(self.dll, f"{prefix}_dec")
        self._dec.argtypes = [
            ctypes.POINTER(ctypes.c_ubyte),  # ss
            ctypes.POINTER(ctypes.c_ubyte),  # ct
            ctypes.POINTER(ctypes.c_ubyte),  # sk
        ]

    # ========================================================================
    # 第一阶段: Setup - 生成系统参数
    # 对应图片: A ← Z_q^{n×m}, S_0 ← {0,1}^{m×k}, pk_KGC = U_0 = A·S_0
    # ========================================================================

    def setup(self) -> Dict[str, Any]:
        """
        Setup阶段：生成系统公共参数。

        对应图片中的Setup算法：
        - 生成随机矩阵 A ← Z_q^{n×m}
        - KGC选择随机矩阵 S_0 ← {0,1}^{m×k} 作为KGC秘密密钥
        - 计算KGC公钥 pk_KGC = U_0 = A · S_0 mod q
        - 定义离散高斯分布 D，参数为 σ
        - H: {0,1}* → {-1,0,1}^k 安全哈希函数

        Returns:
            系统参数字典
        """
        logger.info("[Setup] 开始生成系统参数")

        # A ← Z_q^{n×m}
        self._A = np.random.randint(0, self.q, size=(self.n, self.m), dtype=np.int64)
        logger.info(f"[Setup] 生成随机矩阵 A ∈ Z_{self.q}^{{{self.n}×{self.m}}}")

        # S_0 ← {0,1}^{m×k}，这里k=m
        self._S_0 = np.random.randint(0, 2, size=(self.m, self.m), dtype=np.int64)
        logger.info(f"[Setup] KGC生成秘密密钥 S_0 ∈ {{0,1}}^{{{self.m}×{self.m}}}")

        # U_0 = A · S_0 mod q
        self._U_0 = np.dot(self._A, self._S_0) % self.q
        logger.info(f"[Setup] 计算KGC公钥 U_0 = A·S_0 mod {self.q}")

        logger.info("[Setup] 系统参数生成完成")
        return {
            'A': self._A,
            'S_0': self._S_0,
            'U_0': self._U_0,
            'n': self.n,
            'm': self.m,
            'q': self.q,
            'sigma': self.sigma,
            'variant': self.variant,
        }

    def get_system_params(self) -> Dict[str, np.ndarray]:
        """获取当前系统参数，如果未初始化则自动执行Setup"""
        if self._A is None:
            self.setup()
        return {
            'A': self._A,
            'S_0': self._S_0,
            'U_0': self._U_0,
        }

    def load_system_params(self, A: np.ndarray, S_0: np.ndarray, U_0: np.ndarray):
        """从外部加载系统参数（用于多节点共享同一套系统参数）"""
        self._A = A
        self._S_0 = S_0
        self._U_0 = U_0
        logger.info("[Setup] 从外部加载系统参数完成")

    # ========================================================================
    # 哈希函数 H: {0,1}* → {-1,0,1}^k
    # ========================================================================

    def _hash_to_ternary_vector(self, user_id: str) -> np.ndarray:
        """
        安全哈希函数 H: {0,1}* → {-1,0,1}^m

        对应图片中的 H: {0,1}* → {-1,0,1}^k
        使用SHA-256迭代扩展到所需长度，映射到三元向量 {-1, 0, 1}
        """
        h = hashlib.sha256(user_id.encode('utf-8')).digest()
        # 使用A的字节作为域分离
        if self._A is not None:
            # 取A的前32字节作为域分离标识，避免对整个大矩阵做tobytes
            a_seed = hashlib.sha256(self._A[:1, :32].tobytes()).digest()
            h = hashlib.sha256(h + a_seed).digest()

        # 迭代扩展到m字节
        extended = h
        while len(extended) < self.m:
            extended += hashlib.sha256(extended).digest()

        c = np.frombuffer(extended[:self.m], dtype=np.uint8)
        c = (c % 3).astype(np.int64) - 1  # 映射到 {-1, 0, 1}
        return c

    # ========================================================================
    # 离散高斯采样 D_σ^m
    # ========================================================================

    def _discrete_gaussian_sample(self, size: int) -> np.ndarray:
        """
        从离散高斯分布 D_σ 采样

        对应图片中的 s̄'_id ← D_σ^m

        注意：不能对采样结果取 mod q，必须保持短向量性质。
        图中的 Enc/Dec 正确性依赖于 sk = s̄ 是短向量（|系数| ≤ O(σ√m)），
        这样解密噪声 e₂ − s̄ᵗ·e₁ 才能保持在 q/4 以内。
        """
        samples = np.random.normal(0, self.sigma, size=size)
        samples = np.round(samples).astype(np.int64)
        return samples

    # ========================================================================
    # 第二阶段: PartialKeyGen - KGC为用户生成部分私钥
    # 对应图片: s̄'_id ← D, ū'_id = A·s̄'_id, c̄ = H(id,A), t̄ = s̄'_id + S_0·c̄
    # ========================================================================

    def partial_key_gen(self, user_id: str) -> Dict[str, np.ndarray]:
        """
        PartialKeyGen阶段：KGC为用户生成部分私钥。

        对应图片中的PartialKeyGen算法：
        1. s̄'_id ← D_σ^m  (从离散高斯分布采样)
        2. ū'_id = A · s̄'_id mod q  (计算部分公钥分量)
        3. c̄ = H(id, A)  (哈希用户身份)
        4. t̄ = s̄'_id + S_0 · c̄ mod q  (计算部分私钥)

        Args:
            user_id: 用户身份标识

        Returns:
            包含 t (部分私钥), c (哈希值), u_prime_id (部分公钥分量) 的字典
        """
        params = self.get_system_params()
        A = params['A']
        S_0 = params['S_0']

        logger.info(f"[PartialKeyGen] 为用户 {user_id} 生成部分私钥")

        # s̄'_id ← D_σ^m
        s_prime_id = self._discrete_gaussian_sample(self.m)
        logger.info(f"[PartialKeyGen] s̄'_id ← D_σ^{self.m}")

        # ū'_id = A · s̄'_id mod q
        u_prime_id = np.dot(A, s_prime_id) % self.q
        logger.info(f"[PartialKeyGen] ū'_id = A · s̄'_id mod {self.q}")

        # c̄ = H(id, A)
        c = self._hash_to_ternary_vector(user_id)
        logger.info(f"[PartialKeyGen] c̄ = H({user_id}, A)")

        # t̄ = s̄'_id + S_0 · c̄  (不取 mod q，保持短向量)
        # S_0 ∈ {0,1}^{m×m}, c̄ ∈ {-1,0,1}^m → S_0·c̄ 的系数 ≈ O(√m)
        # s̄'_id 的系数 ≈ O(σ)，所以 t̄ 仍然是短向量
        S_0_c = np.dot(S_0, c)
        t = s_prime_id + S_0_c
        logger.info(f"[PartialKeyGen] t̄ = s̄'_id + S_0·c̄ (短向量, max|t|={np.max(np.abs(t))})")

        logger.info(f"[PartialKeyGen] 部分私钥生成完成")
        return {
            't': t,
            'c': c,
            'u_prime_id': u_prime_id,
        }

    # ========================================================================
    # 第三阶段: SetSecretValue - 用户生成秘密值
    # 对应图片: s̄_id ← D_σ^m
    # ========================================================================

    def set_secret_value(self) -> np.ndarray:
        """
        SetSecretValue阶段：用户自己生成秘密值。

        对应图片中的SetSecretValue算法：
        - s̄_id ← D_σ^m  (从离散高斯分布采样)

        Returns:
            用户秘密值 s_id
        """
        s_id = self._discrete_gaussian_sample(self.m)
        logger.info(f"[SetSecretValue] s̄_id ← D_σ^{self.m}")
        return s_id

    # ========================================================================
    # 第四阶段: SetSK - 设置完整私钥
    # 对应图片: sk = s̄ = t̄ + s̄_id
    # ========================================================================

    def set_sk(self, t: np.ndarray, s_id: np.ndarray) -> np.ndarray:
        """
        SetSK阶段：合成完整私钥。

        对应图片中的SetSK算法：
        - sk = s̄ = t̄ + s̄_id

        注意：不能对 sk 取 mod q。sk 必须保持短向量性质，
        因为 Dec 的正确性依赖于 |s̄ᵗ·e₁| < q/4。
        t̄ 和 s̄_id 都是离散高斯采样的短向量，它们的和仍然是短向量。

        Args:
            t: KGC生成的部分私钥（短向量）
            s_id: 用户秘密值（短向量）

        Returns:
            完整的无证书私钥 sk（短向量）
        """
        sk = t + s_id
        logger.info(f"[SetSK] sk = t̄ + s̄_id (短向量, max|sk|={np.max(np.abs(sk))})")
        return sk

    # ========================================================================
    # 第五阶段: SetPK - 设置完整公钥
    # 对应图片: ū = ū'_id + U_0·c̄ + A·s̄_id (即 ū_id)
    # ========================================================================

    def set_pk(self, u_prime_id: np.ndarray, c: np.ndarray,
               s_id: np.ndarray) -> np.ndarray:
        """
        SetPK阶段：合成完整公钥。

        对应图片中的SetPK算法：
        - ū_id = ū'_id + U_0·c̄ + A·s̄_id mod q

        Args:
            u_prime_id: 部分公钥分量
            c: 哈希值
            s_id: 用户秘密值

        Returns:
            完整的无证书公钥 pk
        """
        params = self.get_system_params()
        U_0 = params['U_0']
        A = params['A']

        U_0_c = np.dot(U_0, c) % self.q
        A_s_id = np.dot(A, s_id) % self.q
        pk = (u_prime_id + U_0_c + A_s_id) % self.q
        logger.info(f"[SetPK] pk = ū'_id + U_0·c̄ + A·s̄_id mod {self.q}")
        return pk


    # ========================================================================
    # DLL桥接层: 将无证书私钥确定性派生为Kyber KEM密钥对
    # ========================================================================

    def _derive_kyber_coins_from_cl_sk(self, cl_sk: np.ndarray,
                                        user_id: str) -> bytes:
        """
        从无证书私钥确定性派生64字节coins，用于DLL的keypair_derand。

        使用SHAKE-256将无证书私钥sk（短向量）和用户身份
        确定性地映射为64字节的coins。

        这是无证书层与DLL层之间的密码学桥梁：
        - 相同的无证书私钥 + 相同的用户ID → 相同的coins → 相同的Kyber密钥对
        - 不同的无证书私钥 → 不同的coins → 不同的Kyber密钥对

        Args:
            cl_sk: 无证书私钥（短向量，系数 ≈ O(σ√m)）
            user_id: 用户身份标识

        Returns:
            64字节的coins，用于keypair_derand
        """
        # 将无证书私钥序列化为字节
        # 使用小端序int16编码每个系数（短向量系数在 [-O(σ√m), O(σ√m)] 范围内）
        sk_bytes = cl_sk.astype(np.int16).tobytes()

        # 域分离: "CL-KYBER-COINS" || user_id || sk_bytes
        domain_sep = b"CL-KYBER-COINS-V1"
        user_bytes = user_id.encode('utf-8')
        input_data = domain_sep + struct.pack('<I', len(user_bytes)) + user_bytes + sk_bytes

        # 使用SHAKE-256派生64字节coins
        coins = _shake256(input_data, self.coins_bytes)
        return coins

    def _generate_kyber_kem_keypair_from_coins(self, coins: bytes) -> Tuple[bytes, bytes]:
        """
        使用确定性coins通过DLL生成标准Kyber KEM密钥对。

        Args:
            coins: 64字节的确定性随机数

        Returns:
            (kyber_pk, kyber_sk) 标准Kyber格式的公钥和私钥
        """
        pk_buf = (ctypes.c_ubyte * self.pk_bytes)()
        sk_buf = (ctypes.c_ubyte * self.sk_bytes)()
        coins_buf = (ctypes.c_ubyte * self.coins_bytes)(*coins)

        ret = self._keypair_derand(pk_buf, sk_buf, coins_buf)
        if ret != 0:
            raise RuntimeError(f"DLL keypair_derand 返回错误码: {ret}")

        return bytes(pk_buf), bytes(sk_buf)

    # ========================================================================
    # 完整的无证书密钥生成流程（融合版）
    # ========================================================================

    def generate_certificateless_keypair(self, user_id: str) -> Dict[str, Any]:
        """
        执行完整的无证书Kyber密钥生成流程，并通过DLL生成标准KEM密钥对。

        流程：
        1. Setup（如果尚未初始化）
        2. PartialKeyGen: KGC生成部分私钥 t
        3. SetSecretValue: 用户生成秘密值 s_id
        4. SetSK: 合成无证书私钥 sk = t + s_id
        5. SetPK: 合成无证书公钥 pk = u'_id + U_0·c + A·s_id
        6. DLL桥接: sk → SHAKE-256 → coins → keypair_derand → (kyber_pk, kyber_sk)

        Args:
            user_id: 用户身份标识

        Returns:
            包含无证书密钥和DLL KEM密钥对的完整结果
        """
        logger.info(f"[GenerateKeypair] 开始为用户 {user_id} 生成无证书Kyber密钥对")

        # Step 1: 确保系统参数已初始化
        self.get_system_params()

        # Step 2: PartialKeyGen
        partial = self.partial_key_gen(user_id)
        t = partial['t']
        c = partial['c']
        u_prime_id = partial['u_prime_id']

        # Step 3: SetSecretValue
        s_id = self.set_secret_value()

        # Step 4: SetSK
        cl_sk = self.set_sk(t, s_id)

        # Step 5: SetPK
        cl_pk = self.set_pk(u_prime_id, c, s_id)

        # Step 6: DLL桥接 - 从无证书私钥派生Kyber KEM密钥对
        logger.info("[DLL桥接] 从无证书私钥派生Kyber KEM密钥对")
        coins = self._derive_kyber_coins_from_cl_sk(cl_sk, user_id)
        kyber_pk, kyber_sk = self._generate_kyber_kem_keypair_from_coins(coins)
        logger.info(
            f"[DLL桥接] Kyber KEM密钥对生成完成: "
            f"pk={len(kyber_pk)}字节, sk={len(kyber_sk)}字节"
        )

        logger.info(f"[GenerateKeypair] 无证书Kyber密钥对生成完成")
        return {
            'success': True,
            'user_id': user_id,
            'algorithm': f'CertificatelessKyber{self.variant}_DLL',
            # 无证书层密钥（用于无证书体系的验证和管理）
            'cl_public_key': cl_pk,
            'cl_private_key': cl_sk,
            # 系统参数 A（加密时需要）
            'system_A': self._A,
            # 无证书层中间值（用于审计和部分私钥管理）
            'partial_key_t': t,
            'secret_value_s_id': s_id,
            'hash_c': c,
            'u_prime_id': u_prime_id,
            # DLL层KEM密钥对（用于实际的加密/解密操作）
            'kyber_public_key': kyber_pk,
            'kyber_private_key': kyber_sk,
            # 参数信息
            'variant': self.variant,
            'pk_bytes': self.pk_bytes,
            'sk_bytes': self.sk_bytes,
        }

    # ========================================================================
    # 分步密钥生成（KGC和节点分离执行）
    # ========================================================================

    def kgc_partial_key_gen(self, user_id: str) -> Dict[str, Any]:
        """
        KGC侧执行：仅生成部分私钥，不涉及用户秘密值。

        用于KGC和节点分离的场景：
        1. KGC调用此方法生成部分私钥
        2. 将部分私钥传递给节点
        3. 节点调用 node_complete_keygen 完成密钥生成

        Returns:
            部分私钥数据包
        """
        partial = self.partial_key_gen(user_id)
        return {
            'success': True,
            'user_id': user_id,
            'partial_key_t': partial['t'],
            'hash_c': partial['c'],
            'u_prime_id': partial['u_prime_id'],
        }

    def node_complete_keygen(self, user_id: str, t: np.ndarray,
                             c: np.ndarray,
                             u_prime_id: np.ndarray) -> Dict[str, Any]:
        """
        节点侧执行：使用KGC的部分私钥完成完整密钥生成。

        Args:
            user_id: 用户身份标识
            t: KGC生成的部分私钥
            c: 哈希值
            u_prime_id: 部分公钥分量

        Returns:
            包含完整密钥对的结果
        """
        logger.info(f"[NodeKeygen] 节点 {user_id} 使用部分私钥完成密钥生成")

        # SetSecretValue
        s_id = self.set_secret_value()

        # SetSK
        cl_sk = self.set_sk(t, s_id)

        # SetPK
        cl_pk = self.set_pk(u_prime_id, c, s_id)

        # DLL桥接
        coins = self._derive_kyber_coins_from_cl_sk(cl_sk, user_id)
        kyber_pk, kyber_sk = self._generate_kyber_kem_keypair_from_coins(coins)

        logger.info(
            f"[NodeKeygen] 密钥生成完成: "
            f"kyber_pk={len(kyber_pk)}B, kyber_sk={len(kyber_sk)}B"
        )

        return {
            'success': True,
            'user_id': user_id,
            'algorithm': f'CertificatelessKyber{self.variant}_DLL',
            'cl_public_key': cl_pk,
            'cl_private_key': cl_sk,
            'system_A': self._A,
            'partial_key_t': t,
            'secret_value_s_id': s_id,
            'hash_c': c,
            'u_prime_id': u_prime_id,
            'kyber_public_key': kyber_pk,
            'kyber_private_key': kyber_sk,
            'variant': self.variant,
            'pk_bytes': self.pk_bytes,
            'sk_bytes': self.sk_bytes,
        }

    # ========================================================================
    # KEM操作: 使用DLL执行封装/解封装
    # ========================================================================

    def encaps(self, kyber_pk: bytes) -> Tuple[bytes, bytes]:
        """
        KEM封装：使用接收方的Kyber公钥生成密文和共享密钥。

        Args:
            kyber_pk: 接收方的标准Kyber公钥

        Returns:
            (ciphertext, shared_secret)
        """
        if len(kyber_pk) != self.pk_bytes:
            raise ValueError(
                f"公钥长度错误: 期望{self.pk_bytes}字节, 实际{len(kyber_pk)}字节"
            )

        ct_buf = (ctypes.c_ubyte * self.ct_bytes)()
        ss_buf = (ctypes.c_ubyte * self.ss_bytes)()
        pk_buf = (ctypes.c_ubyte * self.pk_bytes)(*kyber_pk)

        ret = self._enc(ct_buf, ss_buf, pk_buf)
        if ret != 0:
            raise RuntimeError(f"DLL enc 返回错误码: {ret}")

        return bytes(ct_buf), bytes(ss_buf)

    def decaps(self, ciphertext: bytes, kyber_sk: bytes) -> bytes:
        """
        KEM解封装：使用私钥从密文中恢复共享密钥。

        Args:
            ciphertext: 密文
            kyber_sk: 接收方的标准Kyber私钥

        Returns:
            shared_secret (32字节)
        """
        if len(ciphertext) != self.ct_bytes:
            raise ValueError(
                f"密文长度错误: 期望{self.ct_bytes}字节, 实际{len(ciphertext)}字节"
            )
        if len(kyber_sk) != self.sk_bytes:
            raise ValueError(
                f"私钥长度错误: 期望{self.sk_bytes}字节, 实际{len(kyber_sk)}字节"
            )

        ss_buf = (ctypes.c_ubyte * self.ss_bytes)()
        ct_buf = (ctypes.c_ubyte * self.ct_bytes)(*ciphertext)
        sk_buf = (ctypes.c_ubyte * self.sk_bytes)(*kyber_sk)

        ret = self._dec(ss_buf, ct_buf, sk_buf)
        if ret != 0:
            raise RuntimeError(f"DLL dec 返回错误码: {ret}")

        return bytes(ss_buf)


    # ========================================================================
    # 序列化/反序列化辅助方法
    # ========================================================================

    @staticmethod
    def serialize_cl_key(key: np.ndarray) -> str:
        """将无证书层密钥序列化为base64字符串"""
        return base64.b64encode(key.astype(np.int16).tobytes()).decode('utf-8')

    @staticmethod
    def deserialize_cl_key(key_b64: str, m: int = 1024) -> np.ndarray:
        """从base64字符串反序列化无证书层密钥"""
        key_bytes = base64.b64decode(key_b64)
        return np.frombuffer(key_bytes, dtype=np.int16).astype(np.int64)


# ============================================================================
# 全局单例管理
# ============================================================================

_fusion_instances: Dict[int, CertificatelessKyberDLLFusion] = {}


def get_fusion_instance(variant: int = 512) -> CertificatelessKyberDLLFusion:
    """
    获取指定变体的融合实例（单例模式）。

    系统参数在首次创建时自动初始化，后续所有节点共享同一套系统参数。

    Args:
        variant: Kyber安全级别 (512/768/1024)

    Returns:
        CertificatelessKyberDLLFusion 实例
    """
    global _fusion_instances
    if variant not in _fusion_instances:
        instance = CertificatelessKyberDLLFusion(variant=variant)
        instance.setup()
        _fusion_instances[variant] = instance
        logger.info(f"[Fusion] 创建Kyber-{variant}融合实例并完成Setup")
    return _fusion_instances[variant]
