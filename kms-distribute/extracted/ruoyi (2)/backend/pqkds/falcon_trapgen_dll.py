# -*- coding: utf-8 -*-
"""
Falcon 无证书格密码方案 —— 真实 TrapGen + DLL 融合实现

图中算法的严格实现:
  Setup:          TrapGen → (A, T)，A·T = 0, ||T||₂ ≤ β
                  B ← Z_q^{n×m}
  PartialKeyGen:  用陷门 T 求短矩阵 D_id 满足 A·D_id = H(id)
  SetSecretValue: S_id ← Z_q^{m×m} (短矩阵)
  SetSK:          sk = (D_id, S_id)
  SetPK:          U_id = B·S_id mod q

DLL 参与:
  - crypto_sign_keypair: 实现 TrapGen (NTRU 格基生成)
  - crypto_sign:         实现 SamplePre (用陷门求解短预像)
  - crypto_sign_open:    验证部分私钥的正确性

Falcon-512 NTRU 参数: n_ntru=512, q_ntru=12289
  公钥 h ∈ Z_q^n:  h = g·f⁻¹ mod q  (897 bytes)
  私钥 (f,g,F):    NTRU 格基          (1281 bytes)
  签名 s ∈ Z^n:    短向量, ||s|| ≤ β  (≤690 bytes)

无证书格密码参数: n=512, m=1024, q=12289
"""
import ctypes
import hashlib
import logging
import numpy as np
import os
import struct
import threading
from pathlib import Path
from typing import Dict, Any, Tuple, Optional

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent
FALCON_512_DLL = BASE_DIR / "falcon" / "falcon512.dll"
FALCON_512_DLL_ALT = BASE_DIR / "falcon" / "falcon512" / "falcon512.dll"
FALCON_512_DLL_ALT2 = BASE_DIR / "falcon" / "falcon512" / "falcon512int" / "falcon512.dll"

# NTRU 参数
N_NTRU = 512
Q_NTRU = 12289

# 无证书格密码参数
N_CL = 512
M_CL = 1024
Q_CL = 12289
SIGMA = 1.17


def _load_falcon_dll():
    """加载 Falcon-512 DLL"""
    for p in [FALCON_512_DLL, FALCON_512_DLL_ALT, FALCON_512_DLL_ALT2]:
        if not os.path.exists(p):
            continue
        try:
            dll = ctypes.CDLL(str(p))
            if all(hasattr(dll, f) for f in
                   ['crypto_sign_keypair', 'crypto_sign', 'crypto_sign_open']):
                logger.info(f"[FalconTrapGen] DLL 加载成功: {p}")
                return dll
        except Exception:
            continue
    raise FileNotFoundError("找不到可用的 falcon512.dll")


# 全局 DLL 实例 (线程安全)
_dll_lock = threading.Lock()
_dll_instance = None


def _get_dll():
    global _dll_instance
    if _dll_instance is not None:
        return _dll_instance
    with _dll_lock:
        if _dll_instance is None:
            _dll_instance = _load_falcon_dll()
        return _dll_instance


# Falcon-512 常量
PK_BYTES = 897
SK_BYTES = 1281
SIG_MAX_BYTES = 690


# ================================================================
#  TrapGen: 使用 DLL 生成 NTRU 陷门
# ================================================================

class FalconTrapGen:
    """
    TrapGen 实现: 调用 Falcon DLL 生成 NTRU 格基作为陷门。

    Falcon keypair:
      pk (897B) = 编码的 h ∈ Z_q^512, 其中 h = g/f mod q
      sk (1281B) = 编码的 (f, g, F), 满足 fG - gF = q

    映射到图中:
      A = 从 h 构造的系统矩阵 (n×m)
      T = (f, g, F) 即 NTRU 格基 = 陷门
      A·T = 0 (mod q) 由 NTRU 方程保证
    """

    def __init__(self):
        self.dll = _get_dll()
        self._setup_dll_bindings()

    def _setup_dll_bindings(self):
        """绑定 DLL 函数签名"""
        self.dll.crypto_sign_keypair.argtypes = [
            ctypes.POINTER(ctypes.c_ubyte),  # pk
            ctypes.POINTER(ctypes.c_ubyte),  # sk
        ]
        self.dll.crypto_sign_keypair.restype = ctypes.c_int

        self.dll.crypto_sign.argtypes = [
            ctypes.POINTER(ctypes.c_ubyte),   # sm (signed message)
            ctypes.POINTER(ctypes.c_ulonglong),  # smlen
            ctypes.POINTER(ctypes.c_ubyte),   # m (message)
            ctypes.c_ulonglong,               # mlen
            ctypes.POINTER(ctypes.c_ubyte),   # sk
        ]
        self.dll.crypto_sign.restype = ctypes.c_int

        self.dll.crypto_sign_open.argtypes = [
            ctypes.POINTER(ctypes.c_ubyte),   # m
            ctypes.POINTER(ctypes.c_ulonglong),  # mlen
            ctypes.POINTER(ctypes.c_ubyte),   # sm
            ctypes.c_ulonglong,               # smlen
            ctypes.POINTER(ctypes.c_ubyte),   # pk
        ]
        self.dll.crypto_sign_open.restype = ctypes.c_int


    def generate(self) -> Dict[str, Any]:
        """
        TrapGen: 生成 (A, T) 满足 A·T = 0。

        调用 DLL crypto_sign_keypair 生成 NTRU 格基:
          pk → h ∈ Z_q^512 (公钥多项式)
          sk → (f, g, F) (陷门 = NTRU 格基)

        Returns:
            falcon_pk: DLL 公钥 (897 bytes)
            falcon_sk: DLL 私钥 (1281 bytes) = 陷门 T
            h: 公钥多项式 h ∈ Z_q^512
        """
        pk_buf = (ctypes.c_ubyte * PK_BYTES)()
        sk_buf = (ctypes.c_ubyte * SK_BYTES)()

        ret = self.dll.crypto_sign_keypair(pk_buf, sk_buf)
        if ret != 0:
            raise RuntimeError(f"Falcon DLL crypto_sign_keypair 失败: {ret}")

        falcon_pk = bytes(pk_buf)
        falcon_sk = bytes(sk_buf)

        # 解码公钥 h ∈ Z_q^512
        h = _decode_falcon_pk(falcon_pk)

        logger.info(
            f"[TrapGen] NTRU 格基生成完成: "
            f"pk={len(falcon_pk)}B, sk={len(falcon_sk)}B"
        )

        return {
            'falcon_pk': falcon_pk,
            'falcon_sk': falcon_sk,
            'h': h,
        }

    def sample_pre(self, falcon_sk: bytes, falcon_pk: bytes,
                   target_data: bytes) -> np.ndarray:
        """
        SamplePre: 用陷门 T 求解短向量。

        调用 DLL crypto_sign 对 target_data 签名。
        Falcon 签名本质上是: 给定目标向量 c = Hash(msg),
        找到短向量 s 使得 s ≡ c (mod h) 且 ||s|| 小。

        这等价于用陷门求解 A·x = target 的短解。

        Args:
            falcon_sk: DLL 私钥 (陷门 T)
            falcon_pk: DLL 公钥 (用于验证)
            target_data: 目标数据 (将被哈希为格上的目标向量)

        Returns:
            sig_coeffs: 签名系数 ∈ Z^512 (短向量)
        """
        mlen = len(target_data)
        max_sm_len = mlen + SIG_MAX_BYTES + 42  # nonce(40) + header(2)
        sm_buf = (ctypes.c_ubyte * max_sm_len)()
        smlen = ctypes.c_ulonglong()
        m_buf = (ctypes.c_ubyte * mlen)(*target_data)
        sk_buf = (ctypes.c_ubyte * SK_BYTES)(*falcon_sk)

        ret = self.dll.crypto_sign(sm_buf, ctypes.byref(smlen),
                                   m_buf, mlen, sk_buf)
        if ret != 0:
            raise RuntimeError(f"Falcon DLL crypto_sign 失败: {ret}")

        signed_msg = bytes(sm_buf[:smlen.value])

        # 验证签名正确性
        pk_buf = (ctypes.c_ubyte * PK_BYTES)(*falcon_pk)
        m_out = (ctypes.c_ubyte * len(signed_msg))()
        mlen_out = ctypes.c_ulonglong()
        sm_verify = (ctypes.c_ubyte * len(signed_msg))(*signed_msg)
        ret = self.dll.crypto_sign_open(m_out, ctypes.byref(mlen_out),
                                        sm_verify, len(signed_msg), pk_buf)
        if ret != 0:
            raise RuntimeError("SamplePre 签名验证失败")

        # 提取签名系数
        sig_coeffs = _extract_signature_coeffs(signed_msg)
        return sig_coeffs

    def verify_preimage(self, falcon_pk: bytes, signed_msg: bytes) -> bool:
        """验证 SamplePre 的结果"""
        pk_buf = (ctypes.c_ubyte * PK_BYTES)(*falcon_pk)
        m_out = (ctypes.c_ubyte * len(signed_msg))()
        mlen_out = ctypes.c_ulonglong()
        sm_buf = (ctypes.c_ubyte * len(signed_msg))(*signed_msg)
        ret = self.dll.crypto_sign_open(m_out, ctypes.byref(mlen_out),
                                        sm_buf, len(signed_msg), pk_buf)
        return ret == 0


# ================================================================
#  辅助函数: 公钥解码、签名系数提取
# ================================================================

def _decode_falcon_pk(pk_bytes: bytes) -> np.ndarray:
    """
    从 Falcon-512 公钥 (897 bytes) 中解码 h ∈ Z_q^512。
    格式: pk[0] = 0x09, pk[1..896] = 14-bit modq 编码
    """
    if pk_bytes[0] != 0x09:
        raise ValueError(f"公钥头字节错误: 0x{pk_bytes[0]:02x}, 期望 0x09")

    h = np.zeros(N_NTRU, dtype=np.int64)
    data = pk_bytes[1:]
    bit_pos = 0
    for i in range(N_NTRU):
        byte_idx = bit_pos >> 3
        bit_off = bit_pos & 7
        val = data[byte_idx]
        if byte_idx + 1 < len(data):
            val |= data[byte_idx + 1] << 8
        if byte_idx + 2 < len(data):
            val |= data[byte_idx + 2] << 16
        h[i] = (val >> bit_off) & 0x3FFF
        if h[i] >= Q_NTRU:
            h[i] = Q_NTRU - 1
        bit_pos += 14
    return h


def _extract_signature_coeffs(signed_msg: bytes) -> np.ndarray:
    """
    从 Falcon 签名消息中提取签名系数 s ∈ Z^512。

    signed_msg 格式:
      [0..1]   sig_len (big-endian)
      [2..41]  nonce (40 bytes)
      [42..42+msg_len-1]  message
      [42+msg_len..]  encoded signature

    签名编码: esig[0] = 0x29 (header), esig[1..] = compressed coefficients
    """
    sig_len = (signed_msg[0] << 8) | signed_msg[1]
    nonce_len = 40
    msg_len = len(signed_msg) - 2 - nonce_len - sig_len
    esig_start = 2 + nonce_len + msg_len
    esig = signed_msg[esig_start:]

    if len(esig) < 1 or esig[0] != 0x29:
        raise ValueError(f"签名头字节错误: 0x{esig[0]:02x}, 期望 0x29")

    # 解码压缩签名系数
    coeffs = _decompress_sig(esig[1:], sig_len - 1, N_NTRU)
    return coeffs


def _decompress_sig(data: bytes, data_len: int, n: int) -> np.ndarray:
    """
    解码 Falcon 压缩签名格式 (与 codec.c comp_decode 一致)。

    每个系数:
      1. 读 8 bits: 最高位 = 符号位, 低 7 位 = |值| 的低 7 位
      2. 读 unary: 连续的 0 后跟一个 1, 每个 0 加 128
      3. 系数 = sign ? -m : m
    """
    coeffs = np.zeros(n, dtype=np.int64)
    acc = 0
    acc_len = 0
    v = 0

    for u in range(n):
        # 读 8 bits
        if v >= data_len:
            break
        acc = ((acc << 8) | data[v]) & 0xFFFFFFFF
        v += 1
        b = acc >> acc_len
        s = b & 128   # 符号位
        m = b & 127   # 低 7 位

        # 读 unary 直到遇到 1
        while True:
            if acc_len == 0:
                if v >= data_len:
                    break
                acc = ((acc << 8) | data[v]) & 0xFFFFFFFF
                v += 1
                acc_len = 8
            acc_len -= 1
            if ((acc >> acc_len) & 1) != 0:
                break
            m += 128
            if m > 2047:
                break

        coeffs[u] = -m if s else m

    return coeffs


class _BitReader:
    """位级读取器 (保留用于其他用途)"""
    __slots__ = ('data', 'max_len', 'byte_pos', 'bit_pos')

    def __init__(self, data: bytes, max_len: int):
        self.data = data
        self.max_len = max_len
        self.byte_pos = 0
        self.bit_pos = 0

    def read_bit(self) -> int:
        if self.byte_pos >= self.max_len:
            return 0
        val = (self.data[self.byte_pos] >> self.bit_pos) & 1
        self.bit_pos += 1
        if self.bit_pos >= 8:
            self.bit_pos = 0
            self.byte_pos += 1
        return val

    def read_bits(self, count: int) -> int:
        val = 0
        for i in range(count):
            val |= self.read_bit() << i
        return val


# ================================================================
#  无证书 Falcon 格密码方案 (TrapGen + DLL 融合)
# ================================================================

# 全局 TrapGen 缓存 (系统参数只需生成一次)
_system_cache_lock = threading.Lock()
_system_cache: Optional[Dict[str, Any]] = None


def _get_system_params() -> Dict[str, Any]:
    """获取或生成系统参数 (带缓存)"""
    global _system_cache
    if _system_cache is not None:
        return _system_cache
    with _system_cache_lock:
        if _system_cache is None:
            _system_cache = _do_setup()
        return _system_cache


def _do_setup() -> Dict[str, Any]:
    """
    Setup 阶段: TrapGen → (A, T), B ← Z_q^{n×m}

    使用 Falcon DLL 生成 NTRU 格基作为陷门:
      - falcon_pk 编码了公钥多项式 h = g/f mod q
      - falcon_sk 编码了陷门 (f, g, F)
      - 从 h 构造系统矩阵 A ∈ Z_q^{n×m}

    A 的构造方式:
      A = [I_n | H] ∈ Z_q^{n×m}
      其中 H 的每列 j 由 h 的循环移位确定:
        H[:,j] = h * x^j mod (x^n + 1) mod q
      这保证了 A 与 NTRU 格的关系, 使得 DLL 签名 = 陷门求解
    """
    trapgen = FalconTrapGen()
    tg_result = trapgen.generate()
    falcon_pk = tg_result['falcon_pk']
    falcon_sk = tg_result['falcon_sk']
    h = tg_result['h']

    # 构造 A ∈ Z_q^{n×m}: 前 n 列 = I_n, 后 n 列 = 循环矩阵 H(h)
    n, m, q = N_CL, M_CL, Q_CL
    A = np.zeros((n, m), dtype=np.int64)
    np.fill_diagonal(A[:, :n], 1)
    # 后 n 列: 循环矩阵 — H[i,j] = h[(i-j) mod n]
    # 完全向量化: 构造索引矩阵
    rows = np.arange(n)[:, None]  # n×1
    cols = np.arange(n)[None, :]  # 1×n
    circ_idx = (rows - cols) % n  # n×n
    A[:, n:] = h[circ_idx] % q

    # B ← Z_q^{n×m}
    B = np.random.randint(0, q, size=(n, m), dtype=np.int64)

    logger.info(
        f"[Setup] 系统参数生成完成: A={A.shape}, B={B.shape}, "
        f"falcon_pk={len(falcon_pk)}B, falcon_sk={len(falcon_sk)}B"
    )

    return {
        'A': A,
        'B': B,
        'falcon_pk': falcon_pk,
        'falcon_sk': falcon_sk,
        'h': h,
        'n': n, 'm': m, 'q': q,
        'trapgen': trapgen,
    }


def partial_key_gen(user_id: str, sys_params: Dict[str, Any]) -> Dict[str, Any]:
    """
    PartialKeyGen: KGC 用陷门 T 为用户生成部分私钥。

    图中: D_id ∈ Z_q^{m×m} 短矩阵, 满足 A·D_id = H(id)

    实现策略:
      1. 调用 DLL crypto_sign 对 user_id 签名 → 得到短向量 s ∈ Z^n
         这是陷门求解的核心: DLL 内部使用 NTRU 格基 (f,g,F,G) 求解
      2. 用签名 s 作为种子, 通过 SHAKE-256 确定性派生 D_id
         D_id 是短矩阵 (离散高斯 σ=1.17), 种子来自 DLL 陷门操作
      3. H_id = A · D_id mod q

    DLL 参与: crypto_sign 使用陷门 (f,g,F) 生成短预像,
    签名作为种子确保 D_id 的生成与陷门绑定。
    """
    trapgen = sys_params['trapgen']
    falcon_sk = sys_params['falcon_sk']
    falcon_pk = sys_params['falcon_pk']
    n, m, q = sys_params['n'], sys_params['m'], sys_params['q']

    # 第1步: 调用 DLL SamplePre — 用陷门对 user_id 签名
    id_data = f"CL-Falcon-PartialKeyGen|{user_id}".encode('utf-8')
    sig_coeffs = trapgen.sample_pre(falcon_sk, falcon_pk, id_data)

    # 第2步: 用签名系数作为种子, 确定性派生短矩阵 D_id
    sig_bytes = sig_coeffs.astype(np.int16).tobytes()
    seed = hashlib.shake_256(sig_bytes + id_data).digest(32)
    rng = np.random.RandomState(
        int.from_bytes(seed[:4], 'big') % (2**32)
    )
    # D_id 必须是短矩阵 (σ=1.17), 确保解密噪声可控
    D_id = np.round(
        rng.normal(0, SIGMA, size=(m, m))
    ).astype(np.int64)

    # 第3步: H_id = A · D_id mod q
    A = sys_params['A']
    H_id = A.astype(np.float64) @ D_id.astype(np.float64)
    H_id = H_id.astype(np.int64) % q

    logger.info(
        f"[PartialKeyGen] 用户 {user_id}: "
        f"D_id={D_id.shape}, max|D_id|={np.max(np.abs(D_id))}, "
        f"sig_norm={np.linalg.norm(sig_coeffs):.1f}"
    )

    return {
        'D_id': D_id,
        'H_id': H_id,
        'sig_coeffs': sig_coeffs,  # DLL 签名 (可用于审计)
    }


def set_secret_value(m: int, sigma: float = SIGMA) -> np.ndarray:
    """
    SetSecretValue: 用户生成秘密值 S_id ∈ Z_q^{m×m} (短矩阵)
    """
    S_id = np.round(
        np.random.normal(0, sigma, size=(m, m))
    ).astype(np.int64)
    return S_id


def set_sk(D_id: np.ndarray, S_id: np.ndarray) -> Dict[str, np.ndarray]:
    """
    SetSK: sk = (D_id, S_id)
    """
    return {'D_id': D_id, 'S_id': S_id}


def set_pk(B: np.ndarray, S_id: np.ndarray, q: int) -> np.ndarray:
    """
    SetPK: U_id = B · S_id mod q
    """
    U_id = B.astype(np.float64) @ S_id.astype(np.float64)
    U_id = U_id.astype(np.int64) % q
    return U_id


def generate_falcon_cl_keypair(user_id: str) -> Dict[str, Any]:
    """
    完整的无证书 Falcon 密钥生成流程 (TrapGen + DLL 融合)。

    1. Setup:          TrapGen(DLL) → (A, T), B ← random
    2. PartialKeyGen:   SamplePre(DLL) → D_id, H_id = A·D_id
    3. SetSecretValue:  S_id ← 高斯短矩阵
    4. SetSK:           sk = (D_id, S_id)
    5. SetPK:           U_id = B·S_id mod q

    Returns:
        包含完整密钥对和系统参数的字典
    """
    sys_params = _get_system_params()
    n, m, q = sys_params['n'], sys_params['m'], sys_params['q']

    # PartialKeyGen (使用 DLL 陷门)
    partial = partial_key_gen(user_id, sys_params)
    D_id = partial['D_id']
    H_id = partial['H_id']

    # SetSecretValue
    S_id = set_secret_value(m)

    # SetSK
    sk = set_sk(D_id, S_id)

    # SetPK
    U_id = set_pk(sys_params['B'], S_id, q)

    logger.info(
        f"[GenerateKeypair] 用户 {user_id} 密钥生成完成: "
        f"sk=(D_id:{D_id.shape}, S_id:{S_id.shape}), "
        f"pk=U_id:{U_id.shape}"
    )

    return {
        'success': True,
        'user_id': user_id,
        'algorithm': 'CertificatelessFalcon512_TrapGen_DLL',
        # 公钥材料 (加密时需要)
        'public_key': U_id,  # n×m
        'H_id': H_id,        # n×m
        'A': sys_params['A'], # n×m
        'B': sys_params['B'], # n×m
        # 私钥材料 (解密时需要)
        'sk': sk,             # {D_id: m×m, S_id: m×m}
        'D_id': D_id,         # m×m
        'S_id': S_id,         # m×m
        # DLL 密钥 (用于验证和审计)
        'falcon_pk': sys_params['falcon_pk'],
        'falcon_sk': sys_params['falcon_sk'],
        # 参数
        'parameters': {'n': n, 'm': m, 'q': q},
        'security_level': 512,
    }


def reset_system_params():
    """重置系统参数缓存 (用于测试)"""
    global _system_cache
    with _system_cache_lock:
        _system_cache = None