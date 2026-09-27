import ctypes
import os
import hashlib
import secrets
import numpy as np
import logging
from typing import Tuple, Optional, Dict
from pathlib import Path

# 载荷加解密已统一到 SM4（决策 D3），并保留对历史 AES-256 数据的读取能力。
# 见 pqkds/sm4_crypto.py 与 backend/tests/test_sm4_crypto.py。
from .sm4_crypto import InvalidTag, PayloadCipher

logger = logging.getLogger(__name__)
BASE_DIR = Path(__file__).resolve().parent.parent
FALCON_512_DLL = BASE_DIR / "falcon" / "falcon512.dll"
FALCON_1024_DLL_MAIN = BASE_DIR / "falcon" / "falcon1024.dll"
FALCON_1024_DLL_SUB = BASE_DIR / "falcon" / "falcon1024" / "falcon1024int" / "falcon1024.dll"
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
    except OSError as exc:
        errors.append(f"{fips_path}: {exc}")
FALCON_KDS_DIR = BASE_DIR.parent / "falcon-kds-有陷门"
class FalconCrypto:
    def __init__(self, variant=512):
        self.variant = variant
        if variant == 512:
            self.dll_path = FALCON_512_DLL
            self.public_key_bytes = 897
            self.secret_key_bytes = 1281
            self.signature_bytes = 690
        elif variant == 1024:
            if os.path.exists(FALCON_1024_DLL_MAIN):
                self.dll_path = FALCON_1024_DLL_MAIN
            else:
                self.dll_path = FALCON_1024_DLL_SUB
            self.public_key_bytes = 1793
            self.secret_key_bytes = 2305
            self.signature_bytes = 1330
        else:
            raise ValueError("Falcon variant must be 512 or 1024")
        self.dll = self._load_falcon_dll()
        self.dll.crypto_sign_keypair.argtypes = [
            ctypes.POINTER(ctypes.c_ubyte),
            ctypes.POINTER(ctypes.c_ubyte)
        ]
        self.dll.crypto_sign_keypair.restype = ctypes.c_int
        self.dll.crypto_sign.argtypes = [
            ctypes.POINTER(ctypes.c_ubyte),
            ctypes.POINTER(ctypes.c_ulonglong),
            ctypes.POINTER(ctypes.c_ubyte),
            ctypes.c_ulonglong,
            ctypes.POINTER(ctypes.c_ubyte)
        ]
        self.dll.crypto_sign.restype = ctypes.c_int
        self.dll.crypto_sign_open.argtypes = [
            ctypes.POINTER(ctypes.c_ubyte),
            ctypes.POINTER(ctypes.c_ulonglong),
            ctypes.POINTER(ctypes.c_ubyte),
            ctypes.c_ulonglong,
            ctypes.POINTER(ctypes.c_ubyte)
        ]
        self.dll.crypto_sign_open.restype = ctypes.c_int
    def _load_falcon_dll(self):
        # 路径必须是**候选列表**，不能只试一个。
        #
        # 原先 variant==512 时只试 `FALCON_512_DLL`（= BASE_DIR/falcon/falcon512.dll），
        # 而容器里真实的库在 **BASE_DIR/falcon/falcon512/falcon512.dll**（多一层目录），
        # 于是 Falcon 在本项目里从来没加载成功过 ——
        # 症状是"更新 Kyber 密钥"也会连带失败（那条路径顺带要用 Falcon）。
        # 这里照 KyberCrypto._kyber_library_candidates 的写法改成候选列表。
        if self.variant == 1024:
            dll_paths = [
                FALCON_1024_DLL_MAIN,
                FALCON_1024_DLL_SUB,
            ]
        else:
            dll_paths = [
                FALCON_512_DLL,
                BASE_DIR / "falcon" / "falcon512" / "falcon512.dll",
                BASE_DIR / "falcon" / "falcon512" / "falcon512int" / "falcon512.dll",
            ]
        for dll_path in dll_paths:
            if not os.path.exists(dll_path):
                continue
            try:
                dll = ctypes.CDLL(str(dll_path))
                if hasattr(dll, 'crypto_sign_keypair') and \
                   hasattr(dll, 'crypto_sign') and \
                   hasattr(dll, 'crypto_sign_open'):
                    return dll
            except Exception:
                continue
        raise FileNotFoundError(f"No working Falcon DLL found for variant {self.variant}")
    def generate_keypair(self) -> Tuple[bytes, bytes]:
        pk = (ctypes.c_ubyte * self.public_key_bytes)()
        sk = (ctypes.c_ubyte * self.secret_key_bytes)()
        result = self.dll.crypto_sign_keypair(pk, sk)
        if result != 0:
            raise RuntimeError(f"Falcon keypair generation failed with code {result}")
        return bytes(pk), bytes(sk)
    def sign(self, message: bytes, secret_key: bytes) -> bytes:
        if len(secret_key) != self.secret_key_bytes:
            raise ValueError(f"Invalid secret key length: {len(secret_key)}")
        max_signed_len = len(message) + self.signature_bytes
        sm = (ctypes.c_ubyte * max_signed_len)()
        smlen = ctypes.c_ulonglong()
        m_array = (ctypes.c_ubyte * len(message))(*message)
        sk_array = (ctypes.c_ubyte * len(secret_key))(*secret_key)
        result = self.dll.crypto_sign(
            sm, ctypes.byref(smlen),
            m_array, len(message),
            sk_array
        )
        if result != 0:
            raise RuntimeError(f"Falcon signing failed with code {result}")
        return bytes(sm[:smlen.value])
    def verify(self, signed_message: bytes, public_key: bytes) -> Optional[bytes]:
        if len(public_key) != self.public_key_bytes:
            raise ValueError(f"Invalid public key length: {len(public_key)}")
        m = (ctypes.c_ubyte * len(signed_message))()
        mlen = ctypes.c_ulonglong()
        sm_array = (ctypes.c_ubyte * len(signed_message))(*signed_message)
        pk_array = (ctypes.c_ubyte * len(public_key))(*public_key)
        result = self.dll.crypto_sign_open(
            m, ctypes.byref(mlen),
            sm_array, len(signed_message),
            pk_array
        )
        if result != 0:
            return None
        return bytes(m[:mlen.value])
class KyberCrypto:
    def __init__(self, variant=512):
        self.variant = variant
        if variant == 512:
            self.public_key_bytes = 800
            self.secret_key_bytes = 1632
            self.ciphertext_bytes = 768
            self.shared_secret_bytes = 32
        elif variant == 768:
            self.public_key_bytes = 1184
            self.secret_key_bytes = 2400
            self.ciphertext_bytes = 1088
            self.shared_secret_bytes = 32
        elif variant == 1024:
            self.public_key_bytes = 1568
            self.secret_key_bytes = 3168
            self.ciphertext_bytes = 1568
            self.shared_secret_bytes = 32
        else:
            raise ValueError("Kyber variant must be 512, 768, or 1024")
        self.dll = self._load_kyber_library()
        prefix = f"pqcrystals_kyber{variant}_ref"
        keypair_func = getattr(self.dll, f"{prefix}_keypair")
        keypair_func.argtypes = [
            ctypes.POINTER(ctypes.c_ubyte),
            ctypes.POINTER(ctypes.c_ubyte)
        ]
        keypair_func.restype = ctypes.c_int
        self.keypair_func = keypair_func
        enc_func = getattr(self.dll, f"{prefix}_enc")
        enc_func.argtypes = [
            ctypes.POINTER(ctypes.c_ubyte),
            ctypes.POINTER(ctypes.c_ubyte),
            ctypes.POINTER(ctypes.c_ubyte)
        ]
        enc_func.restype = ctypes.c_int
        self.enc_func = enc_func
        dec_func = getattr(self.dll, f"{prefix}_dec")
        dec_func.argtypes = [
            ctypes.POINTER(ctypes.c_ubyte),
            ctypes.POINTER(ctypes.c_ubyte),
            ctypes.POINTER(ctypes.c_ubyte)
        ]
        dec_func.restype = ctypes.c_int
        self.dec_func = dec_func
    def _load_kyber_library(self):
        errors = []
        _preload_kyber_dependencies(errors)
        for lib_path in _kyber_library_candidates(self.variant):
            if not lib_path.exists():
                continue
            try:
                return ctypes.CDLL(str(lib_path))
            except OSError as exc:
                errors.append(f"{lib_path}: {exc}")
        raise FileNotFoundError(f"Kyber dynamic library not found or not loadable: {'; '.join(errors) or self.variant}")
    def generate_keypair(self) -> Tuple[bytes, bytes]:
        pk = (ctypes.c_ubyte * self.public_key_bytes)()
        sk = (ctypes.c_ubyte * self.secret_key_bytes)()
        result = self.keypair_func(pk, sk)
        if result != 0:
            raise RuntimeError(f"Kyber keypair generation failed with code {result}")
        return bytes(pk), bytes(sk)
    def encrypt(self, public_key: bytes) -> Tuple[bytes, bytes]:
        if len(public_key) != self.public_key_bytes:
            raise ValueError(f"Invalid public key length: {len(public_key)}")
        ct = (ctypes.c_ubyte * self.ciphertext_bytes)()
        ss = (ctypes.c_ubyte * self.shared_secret_bytes)()
        pk_array = (ctypes.c_ubyte * len(public_key))(*public_key)
        result = self.enc_func(ct, ss, pk_array)
        if result != 0:
            raise RuntimeError(f"Kyber encryption failed with code {result}")
        return bytes(ct), bytes(ss)
    def decrypt(self, ciphertext: bytes, secret_key: bytes) -> bytes:
        if len(ciphertext) != self.ciphertext_bytes:
            raise ValueError(f"Invalid ciphertext length: {len(ciphertext)}")
        if len(secret_key) != self.secret_key_bytes:
            raise ValueError(f"Invalid secret key length: {len(secret_key)}")
        ss = (ctypes.c_ubyte * self.shared_secret_bytes)()
        ct_array = (ctypes.c_ubyte * len(ciphertext))(*ciphertext)
        sk_array = (ctypes.c_ubyte * len(secret_key))(*secret_key)
        result = self.dec_func(ss, ct_array, sk_array)
        if result != 0:
            raise RuntimeError(f"Kyber decryption failed with code {result}")
        return bytes(ss)
class AESCrypto:
    """载荷加解密（历史类名保留，实现已切到 SM4）。

    ⚠️ 类名是历史遗留：**新的载荷密钥是 SM4（16 字节），不再是 AES-256（32 字节）**（决策 D3）。
    这里保留 `AESCrypto` 这个名字与 `generate_key` / `encrypt` / `decrypt` 三个静态方法的签名，
    是为了让所有既有调用点（`CryptoUtils`、`kgc_service`、`key_update_service`、
    `real_crypto_with_fallback` 等）不必逐个改写，同时**自动获得**两件事：

      1. 新生成的密钥就是 SM4（16 字节）；
      2. 读取历史数据时按**密钥长度**自动分派 —— 32 字节走旧的 AES-256-GCM，
         16 字节走 SM4-GCM，因此 2026-09 之前写入的密钥池仍能解开。

    分派逻辑与国标向量自测见 `pqkds/sm4_crypto.py` 与 `backend/tests/test_sm4_crypto.py`。
    新代码请直接用 `sm4_crypto.PayloadCipher`（或 `SM4Crypto`），不要再依赖这个旧名字。
    """

    @staticmethod
    def generate_key() -> bytes:
        """生成一把载荷密钥 —— 现在是 SM4 的 16 字节（原为 AES-256 的 32 字节）。"""
        return PayloadCipher.generate_key()

    @staticmethod
    def encrypt(data: bytes, key: bytes) -> Tuple[bytes, bytes]:
        """加密，返回 `(ciphertext, nonce_tag)`。

        信封布局随算法而定：SM4 是 `iv(12)||tag(16)`，旧 AES 是 `nonce(16)||tag(16)`。
        解密端按密钥长度即可判断，无需额外的版本字节。
        """
        return PayloadCipher.encrypt(data, key)

    @staticmethod
    def decrypt(ciphertext: bytes, key: bytes, nonce_tag: bytes) -> bytes:
        """解密并校验完整性；被篡改时抛 `InvalidTag`。

        兼容历史数据：`key` 为 32 字节时自动走旧 AES-256-GCM 路径。
        """
        return PayloadCipher.decrypt(ciphertext, key, nonce_tag)
class CryptoUtils:
    def __init__(self, falcon_variant=512, kyber_variant=512):
        from .real_crypto_with_fallback import RealFalconSignature, RealKyberKEM
        self.falcon = RealFalconSignature(falcon_variant)
        self.kyber = RealKyberKEM(kyber_variant)
        self.aes = AESCrypto()
    def generate_session_key_package(self, recipient_kyber_pk: bytes, sender_falcon_sk: bytes) -> Dict[str, bytes]:
        session_key = self.aes.generate_key()
        kyber_ciphertext, kyber_shared_secret = self.kyber.encaps(recipient_kyber_pk)
        encrypted_session_key, nonce_tag = self.aes.encrypt(session_key, kyber_shared_secret)
        data_to_sign = kyber_ciphertext + encrypted_session_key + nonce_tag
        signed_data = self.falcon.sign(data_to_sign, sender_falcon_sk)
        return {
            'kyber_ciphertext': kyber_ciphertext,
            'encrypted_session_key': encrypted_session_key,
            'nonce_tag': nonce_tag,
            'falcon_signature': signed_data,
            'original_data': data_to_sign
        }
    def extract_session_key(self, key_package: Dict[str, bytes],
                          recipient_kyber_sk: bytes, sender_falcon_pk: bytes) -> Optional[bytes]:
        try:
            message_to_verify = (key_package['kyber_ciphertext'] +
                               key_package['encrypted_session_key'] +
                               key_package['nonce_tag'])
            signature_valid = self.falcon.verify(key_package['falcon_signature'], message_to_verify, sender_falcon_pk)
            if not signature_valid:
                return None
            kyber_shared_secret = self.kyber.decaps(
                key_package['kyber_ciphertext'],
                recipient_kyber_sk
            )
            session_key = self.aes.decrypt(
                key_package['encrypted_session_key'],
                kyber_shared_secret,
                key_package['nonce_tag']
            )
            return session_key
        except Exception as e:
            print(f"Session key extraction failed: {e}")
            return None