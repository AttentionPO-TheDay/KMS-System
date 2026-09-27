# -*- coding: utf-8 -*-
"""阶段 5（文档 §6.3 / §6.4）：对 DistributionEnvelope 做 Falcon 签名与验签。

## 为什么需要
信封里装的是**用接收方公钥封好的 SM4 会话密钥**。只做封装而不签名，
接收方无法区分：

  * 这封信真的是声称的发送方发的，还是别人伪造的
  * 密文与元数据（算法、接收方、有效期）有没有被中途改过

封装保证**机密性**，签名保证**来源与完整性** —— 两者缺一不可，
这也是文档 §6.2 把 Falcon 的职责定为"对分发消息签名"的原因。

## 签什么（§6.4）
**对关键元数据与密文整体签名**，而不是只签某个字段。
只签密文的话，攻击者可以改 `recipient_user_id` 把信转给别人而不被发现；
只签元数据的话，密文可被替换。所以签名覆盖二者，
并且**用确定性序列化**（`sort_keys=True`）—— 否则同一份内容会因
字典顺序不同算出不同签名，验签随机失败。

## 时序要点
签名用**发送方**的 Falcon 私钥，验签用**发送方**的 Falcon 公钥。
接收方用自己的私钥解封（那是机密性那条线），与签名是两条独立的链。
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

#: 参与签名的字段。**顺序无关**（序列化时 sort_keys），
#: 但**集合必须固定** —— 漏签一个字段就等于允许它被篡改。
#:
#: ⚠️ 用的是 `ciphertext_digest`（内层信封的 SHA256）而不是密文原文。
#:    原因是一个踩过的坑：签名发生在"往信封里写 signature 字段之前"，
#:    而库里存的是"写完之后"的 JSON —— 验签时若拿存储值反推，
#:    重建出的字节串与签名时的那份**必然不同**，表现为"自己签的信自己验不过"。
#:    存摘要就绕开了这个自指问题：摘要只取决于内层密文，与签名自身无关。
SIGNED_FIELDS = (
    'batch_id',
    'wrapping_algorithm',
    'payload_algorithm',
    'recipient_user_id',
    'ciphertext_digest',
    'source_key_id',
    'expires_at',
)


def ciphertext_digest(inner_envelope_json: str) -> str:
    """内层信封（含密文）的 SHA256。

    这是被签内容里唯一"与密文相关"的部分 —— 改一个字节密文，
    摘要就变，验签即失败。等价于对密文整体签名，但不受
    "签名会改动信封本身"这个自指问题影响。
    """
    return hashlib.sha256((inner_envelope_json or '').encode('utf-8')).hexdigest()


def canonical_payload(envelope: Dict[str, Any]) -> bytes:
    """把信封的关键字段序列化成**确定性字节串**，用于签名/验签。

    只取 `SIGNED_FIELDS` 里的字段，缺失的记为 None（而不是跳过）——
    跳过会让"攻击者删掉某字段"与"该字段本就为空"产生同样的字节串，
    等于给了一次静默篡改的机会。
    """
    subset = {k: envelope.get(k) for k in SIGNED_FIELDS}
    return json.dumps(subset, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode('utf-8')


def sign_envelope(envelope: Dict[str, Any], falcon_private_key: str) -> Optional[str]:
    """用发送方 Falcon 私钥签名信封，返回 base64 签名。

    私钥是 `Node.falcon_private_key` 里压缩过的 base64（含 zlib），
    经 `node_service.decode_falcon_partial_key` 那套解压。

    签名失败返回 None 并记日志，**不抛异常** —— 调用方需要据此决定
    "无签名地发出"还是"拒绝发送"。这个决定不该由本函数替它做。
    """
    try:
        from .crypto_utils import FalconCrypto

        sk = _decode_falcon_private_key(falcon_private_key)
        if not sk:
            logger.warning('签封信封失败：发送方 Falcon 私钥不可用')
            return None

        f = FalconCrypto(512)
        if len(sk) != f.secret_key_bytes:
            logger.warning('签封信封失败：私钥长度 %d 与 Falcon-512 期望的 %d 不符',
                           len(sk), f.secret_key_bytes)
            return None

        # ⚠️ sign() 返回的是 **signature‖message 的完整签名消息**，
        #    不是裸签名。直接 base64 存它，验签时原样喂回去即可 ——
        #    若在这里切掉 message 只存签名，验签侧还要自行拼接，
        #    一旦拼错（比如又拼了一次）就会得到"签名无效"的假失败。
        signed_message = f.sign(canonical_payload(envelope), sk)
        return base64.b64encode(signed_message).decode('ascii')
    except Exception as exc:  # noqa: BLE001
        logger.warning('签封信封异常: %s', exc)
        return None


def verify_envelope(envelope: Dict[str, Any], signature_b64: str, falcon_public_key: str) -> bool:
    """用发送方 Falcon 公钥验证信封签名。

    返回 True 表示**来源可信且内容未被篡改**。任何异常都返回 False ——
    验签的失败方向必须是"拒绝"，不能是"放行"。
    """
    try:
        from .crypto_utils import FalconCrypto

        pk = _decode_falcon_public_key(falcon_public_key)
        if not pk or not signature_b64:
            return False

        f = FalconCrypto(512)
        if len(pk) != f.public_key_bytes:
            logger.warning('验封信封失败：公钥长度 %d 与 Falcon-512 期望的 %d 不符',
                           len(pk), f.public_key_bytes)
            return False

        signed_message = base64.b64decode(signature_b64)
        recovered = f.verify(signed_message, pk)
        if recovered is None:
            # None 表示 crypto_sign_open 返回非 0 —— 签名无效或内容被改
            return False
        # 双保险：恢复出的内容必须与重新计算的规范字节串一致。
        # 只判 recovered is not None 是不够的 —— 那只能证明"签名自洽"，
        # 证明不了"签的正是当前这份信封"。
        return recovered == canonical_payload(envelope)
    except Exception as exc:  # noqa: BLE001
        logger.warning('验封信封异常（按失败处理）: %s', exc)
        return False


def envelope_digest(envelope: Dict[str, Any]) -> str:
    """信封关键字段的 SHA256，供链上存证与排障比对（不含任何密文内容）。"""
    return hashlib.sha256(canonical_payload(envelope)).hexdigest()


# ---------------------------------------------------------------------------
# 密钥解码
# ---------------------------------------------------------------------------
# ⚠️ 这里**不要**去解 `Node.falcon_private_key`。
#    实测该列装的是 CL-Falcon 的格矩阵 {D_id, S_id, ...}（各 1024 维），
#    与标准 Falcon DLL 不兼容 —— crypto_sign 需要 1281 字节的 NIST 私钥。
#    标准签名密钥单独存在 `falcon_sign_private_key` / `falcon_sign_public_key`，
#    是普通 base64 字节串，无需解压或解析结构。
#
#    这个区别是踩过的坑：最初按"从 falcon_private_key 里找 sk 字段"来写，
#    在真实数据上永远解不出来，而失败被 try/except 吞掉后表现为
#    "签名静默不可用"，不会报错。
def _decode_b64(raw: str) -> Optional[bytes]:
    """标准 Falcon 密钥就是 base64 字节串，直接解。"""
    if not raw:
        return None
    try:
        return base64.b64decode(raw)
    except Exception:  # noqa: BLE001
        return None


def _decode_falcon_private_key(raw: str) -> Optional[bytes]:
    """取节点的**标准** Falcon 签名私钥（来自 falcon_sign_private_key）。"""
    return _decode_b64(raw)


def _decode_falcon_public_key(raw: str) -> Optional[bytes]:
    """取节点的**标准** Falcon 签名公钥（来自 falcon_sign_public_key）。"""
    return _decode_b64(raw)