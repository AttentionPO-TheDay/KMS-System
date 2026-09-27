# -*- coding: utf-8 -*-
"""封装算法注册表：把"用某把公钥把载荷密钥封起来"收敛成查表（计划 §3.1 / P3 步骤 2–4）。

为什么要一张表
--------------
分发需要**同时**产生 N+1 份密文：N 个节点各一份、用户自己一份。而"怎么封"按收件人不同：

    节点腿：Kyber / Falcon（**后量子**，D10 —— 节点侧一行不改）
    用户腿：SM2 / SSCL   （**国密**，D17 —— 只有这两种）

把四种实现收进同一张表，是为了让分发主流程只写一次"给谁封、用哪把公钥"，
而不必在每个分支里重复一遍 KEM+DEM 的编排。

D17 的收窄在**服务端**强制
---------------------------
`USER_LEG_ALGORITHMS` 是白名单，`get_wrapper(..., leg='user')` 会拒绝其余算法，
`assert_user_leg_allowed()` 供接口层直接调用。**只靠前端下拉过滤是不行的** ——
直接构造请求把 CL-Kyber 的 key_id 塞进来照样能拿到信封，而那种信封的私钥就在服务端，
等于没有机密性。

节点腿为什么"零改动"
--------------------
`KyberWrapper` / `FalconWrapper` 刻意**委托给既有的池生成函数**，不重新实现一遍。
P0-C 已经验证过那条路径能正确往返 16 字节载荷，重写只会引入回归风险；
本模块对它们的作用仅是"提供一个统一入口"，行为与原路径完全一致。
"""

from __future__ import annotations

import base64
import json
import logging
from typing import Any, Dict, Optional

from .sm2_crypto import SM2Crypto
from .sm4_crypto import PAYLOAD_ALGORITHM_SM4, PayloadCipher

logger = logging.getLogger(__name__)

#: 用户腿允许的算法（D17）。服务端强制，不是"前端过滤"。
USER_LEG_ALGORITHMS = frozenset({'SM2', 'SSCL'})

#: 节点腿允许的算法（D10）。节点侧零改动。
NODE_LEG_ALGORITHMS = frozenset({'KYBER', 'FALCON', 'kyber', 'falcon', 'kyber_kem', 'falcon_lattice'})


class WrapperError(Exception):
    """封装/解封失败。与"算法不被允许"分开：前者是运行故障，后者是调用方越权。"""


class AlgorithmNotAllowed(Exception):
    """该算法不允许用于这条腿（D17）。接口层应据此返回 400。"""


class Sm2Wrapper:
    """用户腿的 SM2 封装。

    ⚠️ 传进来的**必须**是加密目标点 `P_A = W_A + λ·P_pub`，**不是** `key_value` 里的
    `finalPublicKey`（`W_A`）。用 `W_A` 封装出来的信封**谁都打不开**，连用户自己也不行
    （计划 §3.2.3 用实验纠正过这一点，`tools/verify-pa-target.mjs` 有回归用例）。
    本类无法自行判断拿到的是哪一个点 —— 它只负责"封给这个点"，
    所以取点这件事由主 KMS 的 `user-public-key` 接口统一提供，不要另算。
    """

    name = 'SM2'
    leg = 'user'

    @staticmethod
    def wrap(payload_key: bytes, recipient_public_key: str) -> Dict[str, Any]:
        if not SM2Crypto.is_valid_public_key(recipient_public_key):
            raise WrapperError(f'SM2 加密目标点非法（应为 04 开头、130 位十六进制、且在曲线上）')
        envelope = SM2Crypto.encrypt(recipient_public_key, payload_key)
        # 统一再带上载荷算法，便于读取端确认解出来的是什么
        envelope['payload_algorithm'] = PAYLOAD_ALGORITHM_SM4
        return envelope

    @staticmethod
    def unwrap(envelope: Dict[str, Any], recipient_private_key: str) -> bytes:
        return SM2Crypto.decrypt(recipient_private_key, envelope)

    @staticmethod
    def recipient_public_key_of(key_value_json: Any) -> Optional[str]:
        """从 `key_value` 里取**候选**点。

        ⚠️ 只作为兜底/自检用途。返回的是 `finalPublicKey`（`W_A`），
        **它不能直接用于加密** —— 真正该用的是主 KMS 给出的 `P_A`。
        保留这个函数是为了在排查时能一眼看出"两者不是一回事"。
        """
        payload = key_value_json
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except (ValueError, TypeError):
                return None
        if not isinstance(payload, dict):
            return None
        value = payload.get('finalPublicKey') or payload.get('publicKey')
        return value.lower() if isinstance(value, str) and value else None


class SsclWrapper:
    """用户腿的 SSCL 封装。

    实现上**复用同一套 SM2 原语**：SSCL 的 `d_A` 是 sm2p256v1 上的标量、
    `P_A` 是同一曲线上的点，因此加解密算法完全相同，差别只在**密钥怎么派生**
    （那部分由主 KMS 负责，本模块只拿到最终的点）。

    SSCL 的 `key_value` 里没有 `finalPublicKey`，只有 `SSCLKey`/`SSCLEA`/`SSCLDomain`。
    它的加密目标同样是 `P_A`，由主 KMS 按 `P_A = u_A + (e_A·m)·G` 算出后经
    `user-public-key` 接口给出 —— **不要**试图从 `SSCLKey` 直接拼一个点出来。
    """

    name = 'SSCL'
    leg = 'user'

    @staticmethod
    def wrap(payload_key: bytes, recipient_public_key: str) -> Dict[str, Any]:
        if not SM2Crypto.is_valid_public_key(recipient_public_key):
            raise WrapperError('SSCL 加密目标点非法（应为 04 开头、130 位十六进制、且在曲线上）')
        envelope = SM2Crypto.encrypt(recipient_public_key, payload_key)
        envelope['payload_algorithm'] = PAYLOAD_ALGORITHM_SM4
        # ⚠️ 这里**不能**改写 `algorithm` 字段。
        # `algorithm` 表达的是"用的哪个**密码算法**"（两者都是 SM2 公钥加密），
        # 而 `SM2Crypto.decrypt` 会校验它必须等于 'sm2' —— 改成 'sscl' 会让解封直接失败
        # （这个坑是本文件的测试抓出来的）。
        # "密钥体系是 SSCL 还是 SM2" 是另一件事，用 `key_system` 单独表达。
        envelope['key_system'] = 'sscl'
        return envelope

    @staticmethod
    def unwrap(envelope: Dict[str, Any], recipient_private_key: str) -> bytes:
        return SM2Crypto.decrypt(recipient_private_key, envelope)


class _DelegatingNodeWrapper:
    """节点腿的占位封装器：**委托给既有池生成路径**，不重新实现。

    P0-C 已验证既有路径能正确往返 16 字节载荷；重写只会引入回归风险。
    本类存在的意义是让"四种算法都在一张表里"这件事成立，
    从而让分发主流程不必关心收件人是节点还是用户。
    """

    def __init__(self, name: str, legacy_algorithm: str):
        self.name = name
        self.leg = 'node'
        self.legacy_algorithm = legacy_algorithm

    def wrap(self, payload_key: bytes, **kwargs) -> Dict[str, Any]:
        raise WrapperError(
            f'{self.name} 的封装走既有的密钥池生成路径（key_pool_service.generate_*_pool），'
            f'不经过本注册表的 wrap()。这样做的目的是保持节点腿零改动（D10）。'
        )


#: 四种算法的统一入口。键是**规范名**（大写），查找请用 `get_wrapper`。
WRAPPERS: Dict[str, Any] = {
    'SM2': Sm2Wrapper,
    'SSCL': SsclWrapper,
    'KYBER': _DelegatingNodeWrapper('KYBER', 'kyber_kem'),
    'FALCON': _DelegatingNodeWrapper('FALCON', 'falcon_lattice'),
}


#: 节点腿默认封装算法（D16）。由节点管理的「默认封装算法」字段配置，这里只是缺省值。
NODE_DEFAULT_WRAPPING = 'kyber_kem'

#: 密钥池/分发里节点腿能用的封装算法。
#:
#: 2026-09-26 从两种扩到四种：用户要能选"这次分发不用抗量子"，
#: 而节点腿上原本只有格密码（Kyber/Falcon）—— 于是补了国密两条：
#:   gm_sm2   → 节点持有 SM2 密钥对
#:   gm_sscl  → 节点持有 SSCL 密钥对（加解密与 SM2 同一套曲线运算，见 SsclWrapper）
#:
#: ⚠️ 2026-09-28 阶段 5（文档 §6.2）：**移除 falcon_lattice**。
#: 原因是职责错配 —— SM4 的机密性必须由**加密/封装**算法提供，而 Falcon 是
#: **签名**算法；签名不提供机密性，"用 Falcon 封装会话密钥"是概念混用。
#:
#: 正确分工（文档 §6.2）：
#:   SM2 / SSCL / Kyber  → 保护 SM4（加密或 KEM）
#:   Falcon              → 对分发消息签名、验签
#:
#: 本元组只约束**新的**选择；已存在的 falcon_lattice 历史记录不受影响
#: —— 读取端按记录自身的 algorithm 字段分派，与这里无关。
NODE_WRAPPING_CHOICES = ('kyber_kem', 'gm_sm2', 'gm_sscl')


def wrap_for_node(payload_key: bytes, node, wrapping_algorithm: str = NODE_DEFAULT_WRAPPING):
    """把载荷密钥封给**一个节点**（节点腿，D10 保留抗量子）。

    ⚠️ 这里刻意**不改** `key_pool_service` 里那条既有路径 —— D10 要求节点侧零改动，
    而 P0-C 已验证那条路径能正确往返 16 字节载荷，重写只会引入回归。
    本函数复用的是**同一套配方**（见 `key_pool_service.py` 里
    `generate_distributable_pool` 的 Step 2）：
        kem_ct, ss = kyber.encrypt(node_pk)
        kek        = PayloadCipher.kek_from_shared_secret(SM4, ss)
        enc, tag   = SM4Crypto.encrypt(payload_key, kek)
    两者产出同构的数据包，因此既有读取端（`consume_key` / 节点侧解封）**无需改动**即可解开。

    <h2>为什么节点那份必须用同一把 K</h2>
    用户要与节点用**同一把 SM4** 通信，双方都必须持有 K（计划 §3.1）。
    用户那份走国密 SM2、节点那份走抗量子 Kyber —— **两条腿算法不同，但解出的 K 是同一把**。
    这正是 D10 方案 A 能成立的根本原因；如果两条腿各生成一把 K，双方就根本对不上。

    @return `(envelope, key_hash)`；封装失败抛 `WrapperError`
    """
    import base64
    import hashlib

    from .sm4_crypto import GCM_IV_BYTES, SM4Crypto

    algorithm = wrapping_algorithm or NODE_DEFAULT_WRAPPING
    if algorithm not in NODE_WRAPPING_CHOICES:
        raise WrapperError(f'节点腿不支持的封装算法: {algorithm}')

    if algorithm == 'kyber_kem':
        public_key_b64 = getattr(node, 'kyber_public_key', None)
        if not public_key_b64:
            raise WrapperError(f'节点 {getattr(node, "node_id", "?")} 没有 Kyber 公钥，无法封装')
        try:
            node_pk = base64.b64decode(public_key_b64)
        except Exception as exc:  # noqa: BLE001
            raise WrapperError(f'节点 Kyber 公钥解码失败: {exc}') from exc

        from .crypto_utils import KyberCrypto
        # 与既有池路径同一套判定：按公钥长度定 Kyber 变体（见 key_pool_service 的 pk_len_map）
        pk_len_map = {800: 512, 1184: 768, 1568: 1024}
        variant = pk_len_map.get(len(node_pk), 512)
        kyber = KyberCrypto(variant)
        kem_ct, shared_secret = kyber.encrypt(node_pk)
    elif algorithm in ('gm_sm2', 'gm_sscl'):
        # 国密节点腿（2026-09-26 补）。
        #
        # 用户要能选"这次分发不用抗量子"，而节点腿原本只有格密码，
        # 所以给节点加了一对 SM2、一对 SSCL 密钥（node_service.generate_gm_keys）。
        #
        # 这里**复用用户腿的封装器**（Sm2Wrapper / SsclWrapper）而不是另写一套：
        # SSCL 与 SM2 的加解密本来就是同一套 sm2p256v1 曲线运算，
        # 差别只在密钥怎么派生（见 SsclWrapper 的说明），
        # 因此节点用对应私钥即可解封，节点侧不需要新代码。
        node_code = getattr(node, 'node_id', '?')
        if algorithm == 'gm_sm2':
            public_key_hex = getattr(node, 'gm_public_key', None)
            if not public_key_hex:
                raise WrapperError(f'节点 {node_code} 没有国密公钥，无法封装')
            wrapper = WRAPPERS['SM2']
        else:
            public_key_hex = getattr(node, 'sscl_public_key', None)
            if not public_key_hex:
                raise WrapperError(f'节点 {node_code} 没有 SSCL 公钥，无法封装')
            wrapper = WRAPPERS['SSCL']

        gm_envelope = wrapper.wrap(payload_key, public_key_hex)
        # ⚠️ 不改 `algorithm`（那是密码算法，SM2 解密会校验它必须是 'sm2'），
        # 节点腿用的是哪种**算法档位**由 wrapping_algorithm 表达。
        gm_envelope['wrapping_algorithm'] = algorithm
        gm_envelope['recipient_public_key'] = str(public_key_hex).lower()
        return gm_envelope, hashlib.sha256(payload_key).hexdigest()
    else:
        # Falcon 节点腿（2026-09-26 补）。
        #
        # 这里**复用**既有的 Falcon 池路径配方（key_pool_service.generate_falcon_pool Step 2：
        # FalconAESSessionKeyEncryption.encrypt_aes_key_with_falcon），
        # 而不是另写一套格加密 —— 节点侧的解封路径因此不用改，
        # 信封形状也与池路径一致（{ciphertext, algorithm, security_level, payload_algorithm}）。
        #
        # 之所以原先这里是抛错：D16 把 Kyber 定为唯一默认值，而"用户能否选抗量子算法"
        # 当时没有需求。现在用户侧要能选 Kyber / Falcon，所以把这条腿补齐。
        public_key_b64 = getattr(node, 'falcon_public_key', None)
        node_code = getattr(node, 'node_id', '?')
        if not public_key_b64:
            raise WrapperError(f'节点 {node_code} 没有 Falcon 公钥，无法封装')

        from .falcon_aes_session_encryption import FalconAESSessionKeyEncryption
        try:
            security_level = int(getattr(node, 'falcon_security_level', '512') or '512')
        except (TypeError, ValueError):
            security_level = 512
        falcon_enc = FalconAESSessionKeyEncryption(security_level=security_level)
        enc_result = falcon_enc.encrypt_aes_key_with_falcon(
            recipient_id=node_code,
            aes_key=payload_key,
            recipient_public_key_b64=public_key_b64,
        )
        if not enc_result.get('success'):
            raise WrapperError(
                f'节点 {node_code} 的 Falcon 封装失败：{enc_result.get("message") or "未知原因"}'
            )
        falcon_envelope = {
            'ciphertext': enc_result['ciphertext'],
            'algorithm': enc_result.get('algorithm', f'CertificatelessFalcon-{security_level}'),
            'security_level': security_level,
            'payload_algorithm': PAYLOAD_ALGORITHM_SM4,
            'wrapping_algorithm': algorithm,
        }
        return falcon_envelope, hashlib.sha256(payload_key).hexdigest()

    kek = PayloadCipher.kek_from_shared_secret(PAYLOAD_ALGORITHM_SM4, shared_secret)
    encrypted_key, nonce_tag = SM4Crypto.encrypt(payload_key, kek)
    nonce, tag = nonce_tag[:GCM_IV_BYTES], nonce_tag[GCM_IV_BYTES:]

    envelope = {
        'kem_ciphertext': base64.b64encode(kem_ct).decode(),
        'encrypted_key': base64.b64encode(encrypted_key).decode(),
        'nonce': base64.b64encode(nonce).decode(),
        'tag': base64.b64encode(tag).decode(),
        'payload_algorithm': PAYLOAD_ALGORITHM_SM4,
        'wrapping_algorithm': algorithm,
    }
    return envelope, hashlib.sha256(payload_key).hexdigest()


def open_node_envelope(envelope: Dict[str, Any], node_kyber_private_key_b64: str) -> bytes:
    """节点侧解封（验收与故障排查用）。生产路径由节点自己按既有方式解开。"""
    import base64

    from .sm4_crypto import GCM_IV_BYTES, SM4Crypto

    if not isinstance(envelope, dict):
        raise WrapperError('节点信封格式错误：应为字典')

    from .crypto_utils import KyberCrypto
    pk_len_map = {800: 512, 1184: 768, 1568: 1024}
    node_sk = base64.b64decode(node_kyber_private_key_b64)
    # 私钥长度同样用于定变体；取不到时退回 512（与池路径的缺省一致）
    variant = {32: 512, 64: 768, 128: 1024}.get(len(node_sk), 512)
    shared_secret = KyberCrypto(variant).decrypt(
        base64.b64decode(envelope['kem_ciphertext']), node_sk
    )
    kek = PayloadCipher.kek_from_shared_secret(PAYLOAD_ALGORITHM_SM4, shared_secret)
    nonce = base64.b64decode(envelope['nonce'])
    tag = base64.b64decode(envelope['tag'])
    return SM4Crypto.decrypt(base64.b64decode(envelope['encrypted_key']), kek, nonce + tag)


def normalize_algorithm(algorithm: str) -> str:
    """把各种历史写法归一成注册表的键。

    节点腿历史上用过 `kyber_kem` / `falcon_lattice` / `Kyber` / `Falcon` 等写法，
    用户腿用 `SM2` / `SSCL`。这里统一收口，避免调用方各写一套判断。
    """
    if algorithm is None:
        raise AlgorithmNotAllowed('算法为空')
    text = str(algorithm).strip()
    upper = text.upper()
    if upper in ('SM2',):
        return 'SM2'
    if upper in ('SSCL',):
        return 'SSCL'
    if 'KYBER' in upper:
        return 'KYBER'
    if 'FALCON' in upper:
        return 'FALCON'
    raise AlgorithmNotAllowed(f'未知算法: {text}')


def get_wrapper(algorithm: str, leg: Optional[str] = None):
    """按算法取封装器；给定 `leg` 时同时执行 D17/D10 的白名单校验。

    `leg='user'` 时，只有 SM2 / SSCL 能通过 —— 这是**服务端**的收窄，
    接口层必须传 `leg='user'`，不能依赖前端下拉过滤。
    """
    key = normalize_algorithm(algorithm)
    if leg == 'user' and key not in ('SM2', 'SSCL'):
        raise AlgorithmNotAllowed(
            f'算法 {algorithm} 不可用于分发给用户（用户腿仅支持 SM2 / SSCL）。'
            f'CL-Kyber / CL-Falcon 的完整私钥存放在服务端，用它封装等于没有机密性。'
        )
    wrapper = WRAPPERS.get(key)
    if wrapper is None:
        raise AlgorithmNotAllowed(f'没有注册的封装实现: {algorithm}')
    return wrapper


def assert_user_leg_allowed(algorithm: str) -> str:
    """D17 的服务端强制入口。返回规范名，越权时抛 `AlgorithmNotAllowed`。

    接口层应当在**读取密钥材料之前**调用它，这样越权请求连密钥都碰不到。
    """
    key = normalize_algorithm(algorithm)
    if key not in USER_LEG_ALGORITHMS:
        raise AlgorithmNotAllowed(
            f'算法 {algorithm} 不可用于分发给用户（用户腿仅支持 SM2 / SSCL）'
        )
    return key


def build_user_envelope(payload_key: bytes, source_algorithm: str,
                        recipient_public_key_hex: str) -> Dict[str, Any]:
    """给用户本人封一份信封。整个用户腿只有这一个入口。

    顺序刻意是"先校验算法、再封装"：越权请求不会走到密钥运算那一步。
    """
    wrapper = get_wrapper(source_algorithm, leg='user')
    envelope = wrapper.wrap(payload_key, recipient_public_key_hex)
    # `algorithm` 由 SM2Crypto 填成 'sm2'（密码算法本身）；
    # 这里补的是**密钥体系**，两者不是一回事，别混。
    envelope.setdefault('algorithm', 'sm2')
    envelope.setdefault('key_system', wrapper.name.lower())
    # 记录"密文是按哪一把密钥封的"：解封失败时能立刻看出是不是拿错了密钥
    envelope['recipient_public_key'] = recipient_public_key_hex.lower()
    return envelope


def open_user_envelope(envelope: Dict[str, Any], recipient_private_key_hex: str) -> bytes:
    """用户侧解封。`recipient_private_key_hex` 是 `d_A`（64 位十六进制私钥标量）。

    按 `algorithm`（**密码算法**）分派，而不是 `key_system`（密钥体系）——
    两者现在都是 `'sm2'` 公钥加密，所以这里必然走同一条路。
    日后若引入第三种用户腿算法，才需要在这里按 `algorithm` 真正分支。
    """
    if not isinstance(envelope, dict):
        raise WrapperError('信封格式错误：应为字典')
    algorithm = envelope.get('algorithm') or 'sm2'
    wrapper = get_wrapper(algorithm, leg='user')
    return wrapper.unwrap(envelope, recipient_private_key_hex)


def envelope_to_json(envelope: Dict[str, Any]) -> str:
    """落库用：序列化成 JSON 文本（与既有 `encrypted_key_data` 的存法一致）。"""
    return json.dumps(envelope, ensure_ascii=False, sort_keys=True)


def envelope_from_json(text: Any) -> Dict[str, Any]:
    """读库用：接受 dict 或 JSON 文本。"""
    if isinstance(text, dict):
        return text
    if isinstance(text, str):
        try:
            parsed = json.loads(text)
        except (ValueError, TypeError) as exc:
            raise WrapperError(f'信封不是合法 JSON: {exc}') from exc
        if isinstance(parsed, dict):
            return parsed
    raise WrapperError('信封格式错误：应为字典或 JSON 对象文本')