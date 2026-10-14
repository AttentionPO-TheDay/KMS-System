"""Public long-term key payloads shared by node and administrator read views."""
from __future__ import annotations

import base64
import binascii
import logging
import re

from . import api_contract as C
from .models import NodeLongTermKey

logger = logging.getLogger(__name__)

#: 状态文案仍只取冻结契约，不维护第二份状态表。
_STATUS_LABELS = dict(C.KEY_STATUS_CHOICES)
_HEX_RE = re.compile(r'[0-9a-fA-F]+')


def public_key_hex(record) -> str:
    """公钥的**比对形式**：一律小写 hex，与节点本地密钥库里的记录同形。

    为什么要转换而不原样下发
    ------------------------
    存储形式按算法分两种（见 `node_service.store_node_public_key`：Kyber 存
    **base64**，其余存 hex），而节点本地一律是 hex。生成页要拿服务端这把与
    本机那把**逐字节**比对，若原样下发存储形式，**Kyber 会恒定"对不上"**——
    它的表现是"服务端记的不是你本机那把"，看着像密钥被换过或本机被人动过，
    实际只是编码不同。这类假警报比不报警更糟：用户会去重新初始化。

    转不动时返回空串（**不猜**）：页面据此显示"服务端记录无法比对"，
    那才是实情。返回一段看起来像公钥的东西会被拿去比对，且永远不相等。
    """
    raw = str(record.public_key or '').strip()
    if not raw:
        return ''
    if record.algorithm == 'FALCON_CL_V1':
        from .falcon_cl_v1 import parse_material
        try:
            parse_material(raw, 'PUBLIC', record.node.node_id)
        except (ValueError, TypeError):
            return ''
        return raw
    if record.algorithm != 'KYBER':
        return raw.lower()
    # 先认 hex 再认 base64，顺序不能反：hex 的字母表是 base64 的子集，
    # 一段 hex 串往往也能被 base64 解码（得到的是另一串字节，且不报错）。
    if _HEX_RE.fullmatch(raw):
        return raw.lower()
    try:
        return base64.b64decode(raw, validate=True).hex()
    except (binascii.Error, ValueError):
        logger.warning('节点 %s 的 Kyber 公钥既不是 hex 也不是 base64，无法比对', record.node_id)
        return ''


def iso(value):
    """时间戳按 ISO 下发；空值一律 None（前端据此显示"—"而不是 1970）。"""
    return value.isoformat() if value else None


def long_term_key_payload(k: NodeLongTermKey) -> dict:
    """一行长期密钥 → 页面需要的形状。逐行调用，公钥只换算一次。"""
    public_key = public_key_hex(k)
    from .keygen_issuance import public_generation_payload
    from .chain_backend import is_fabric_did, chain_write_state
    chain_binding = None
    if is_fabric_did():
        from .chain_binding_service import get_binding_status
        chain_binding = get_binding_status(k)
    else:
        from .node_fisco_evidence import enabled, status
        if enabled():
            chain_binding = status(k)
    return {
        'algorithm': k.algorithm,
        'purpose': 'ENCRYPT' if k.algorithm == 'FALCON_CL_V1' else ('SIGN' if k.algorithm == 'FALCON' else 'ENCRYPT'),
        'materialVersion': 1 if k.algorithm == 'FALCON_CL_V1' else None,
        'publicKeyEncoding': 'FCL_V1_BASE64_JSON' if k.algorithm == 'FALCON_CL_V1' else 'hex',
        **public_generation_payload(k),
        # 密钥可用与链上确认是两个事实；尚无配置时也不能显示成“上链成功”。
        'chainBinding': chain_binding,
        'chainWriteState': ('ENABLED' if chain_binding and chain_binding.get('provider') == 'FISCO' and chain_binding.get('writeEnabled') else chain_write_state()),
        'keyId': k.key_id,
        'keyVersion': k.key_version,
        'status': k.status,
        # 状态文案与「这把还能干什么」都由服务端下发，取自 `api_contract`。
        # 前端**不另写一份**中文表与可用性判断：两份必然漂移，而漂移的表现是
        # "界面写着可用、实际已被取代"—— 用户据此做的判断全是错的，
        # 且没有任何一处会报错。
        'statusLabel': _STATUS_LABELS.get(k.status, k.status),
        'allowsNewWork': k.allows_new_work,
        'allowsUnwrap': k.allows_unwrap,
        'securityLevel': k.security_level,
        'deviceId': k.device_id,
        # 公钥是公开量，可以自由下发。给的是**比对形式**（小写 hex）：
        # 页面拿它与本机密钥库里的 `publicKey` 逐字节比，判断
        # "服务端记的那把，是不是我本机这把"。两者同形是这段比对能成立的
        # 前提，编码换算（Kyber 的 base64↔hex）收在 public_key_hex 里。
        'publicKey': public_key,
        'publicKeyHash': k.public_key_hash,
        # 字节数而非字符串长度，也不是截断值：字节数才能与 Kyber 变体
        # （800/1184/1568）对上；截断后的串看起来仍像一把公钥、会被拿去比对，
        # 而它永远比不相等。要完整正文用上面那个字段。
        'publicKeyBytes': len(base64.b64decode(public_key)) if k.algorithm == 'FALCON_CL_V1' and public_key else len(public_key) // 2,
        'legacy': k.legacy,
        'legacySource': k.legacy_source,
        'effectiveAt': iso(k.effective_at),
        'expiresAt': iso(k.expires_at),
        'revokedAt': iso(k.revoked_at),
        'revokedReason': k.revoked_reason,
        'createdAt': iso(k.create_datetime),
        'updatedAt': iso(k.update_datetime),
    }
