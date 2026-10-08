# -*- coding: utf-8 -*-
"""预分配密钥池的**取用**编排（任务书「预分配」的出口）。

规范原文（用户定义，逐字）
--------------------------
    "密钥预分配是指发送节点在实际通信之前，提前生成一定数量的随机 SM4 会话密钥，
     利用接收节点的 Kyber 公钥形成加密保护包，并将保护包上传至 KMS 预分配密钥池。
     服务端仅负责保存、调度和管理保护包。实际建立会话时，发送节点取用一条预分配资源，
     使用 Falcon 私钥签名并发送，接收节点验签和解封装成功后，双方建立 SM4 安全会话。"

本模块落的是**后两句**：取用一条 → 交给发送方一个可签的信封 → 建 `initiated` 会话。
前半句（生成与封装）由**节点侧**完成，见下面的"为什么不能由服务端生成"。

<h2>为什么不能由服务端生成 K（这不是口味问题）</h2>
本系统的会话确认是"双方各自提交 `HMAC(K, session_id)`"（`node_session_views` 的
confirm）。也就是说**发起方也必须持有 K** —— 而 K 是被**接收方**的 Kyber 公钥封的，
发送方用本地私钥**解不开**。如果 K 由服务端生成，服务端就必须在取用时把明文 K
交还发送方，于是无论怎么绕，服务端在生成那一刻都持有过明文会话密钥 ——
与计划 §2.1「服务端禁止接收或返回 SM4 明文」相抵。

节点侧生成则完全没有这个问题：`kyber.encapsulate(接收方公钥)` 只需要**公钥**
（实测节点侧 Kyber-768 封装 + SM4-GCM 约 2600 条/秒，远高于任务书 §20 的
≥50 条/秒），而 K 从头到尾只存在于发送方的浏览器里。服务端收到的只有
密文 + 摘要 + 签名 —— 它**管理**保护包，不生成、也不解开。

<h2>取用时服务端做什么</h2>
1. 授权闸门（与 `/node-self/distributions/` **同一判据** `authorized_node_ids`）；
2. `KeyPoolService.consume_key` —— 行锁 + 状态机 + 未过期 + 长期密钥复核（全部复用，
   一次性取用由它保证，本模块不另写一套）；
3. 把**节点侧上传的保护包**改写成**节点信封**并盖上本次交付的元数据
   （`batch_id` / `recipient_key_*` / `expires_at` / 收发节点 / `key_hash`），
   重算 `ciphertext_digest` —— 见 `_build_delivery_envelope` 的说明；
4. 建 `initiated` 会话（会话号 `{pool_id}-k{key_index}-n{接收方}`）。

⚠️ 取用与建会话在**同一个事务**里：只取用不建会话会留下一条只有服务端知道的
   已消费项（`used_by_session` 为空、接收方也没有会话可走），比"取用失败"更难查。
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional, Tuple

from django.db import transaction
from django.utils import timezone

from . import api_contract as C
from .distribution_service import create_initiated_sessions
from .envelope_signature import ciphertext_digest, node_canonical_payload
from .key_pool_service import KeyPoolService
from .models import Node, PreDistributedKey

logger = logging.getLogger(__name__)

#: 保护包（池项）里属于**内层密文**的字段 —— 也就是 `ciphertext_digest` 覆盖的那几项。
#: 与 `distribution_service._canonical_inner_json` 的作用相同：节点腿信封的"内层"
#: 是密文本体，摘要算的是它（**不含**元数据、更不含摘要自身 —— 后者是自指）。
_INNER_FIELDS = ('kem_ciphertext', 'encrypted_key', 'nonce', 'tag',
                 'payload_algorithm', 'wrapping_algorithm')


class PoolConsumeError(Exception):
    """取用流程里的**业务拒绝**。带 `code`（`api_contract.ERR_*`）供调用方分支。"""

    def __init__(self, message: str, code: str = C.ERR_INVALID_PARAMETER,
                 *, http_status: Optional[int] = None):
        super().__init__(message)
        self.message = message
        self.code = code
        self.http_status = http_status or C.ERROR_HTTP_STATUS.get(code, 400)


def _canonical_inner_json(inner: Dict[str, Any]) -> str:
    """内层密文的紧凑 JSON —— 与 `distribution_service` 的口径逐字节相同。

    ⚠️ `sort_keys=True` + `separators=(',', ':')`：与浏览器侧
    `envelope-signing.canonicalJson` 同一套序列化。任一处不同，节点签的信
    服务端就验不过，而那种失败看起来完全像伪造。
    """
    subset = {k: inner.get(k) for k in _INNER_FIELDS}
    return json.dumps(subset, sort_keys=True, ensure_ascii=False, separators=(',', ':'))


def _normalize_protection_package(package: Dict[str, Any]) -> Dict[str, Any]:
    """把节点侧上传的**保护包**归一成内层密文形状。

    形状只在**字段名**上与节点信封不同（这是历史遗留，不是两种密码学）：
      * 保护包沿用 `wrapForPeer` 的输出 —— `encrypted_key`（KEM+DEM 的密文本体）；
      * 而服务端两条既有的**服务端侧**封装路径（`wrappers.wrap_for_node` 与
        已下线的 `generate_kyber_pool`）写的是 `encrypted_aes_key`
        （名字来自更早的 AES-256 时代，值就是同一件事）。

    前端解封（`browser-provider.unwrapEnvelope`）按 `wrapping_algorithm` 分派、
    按 `encrypted_key` 取密文，所以**两种名字它只认 `encrypted_key`**。
    不在这里归一的话，接收方拿到保护包后是"验签报签名缺失、解封报不支持算法"，
    而库里那一行看起来一切正常。

    ⚠️ 只接受 Kyber 保护包。SM2/SSCL 是**用户腿**（封给用户本人）的封装，
       预分配这条路按用户定下的口径只做格密码（那也是量化的指标面）。
    """
    wrapping = str(package.get('wrapping_algorithm') or 'kyber_kem').strip().lower()
    if wrapping != 'kyber_kem':
        raise PoolConsumeError(
            f'预分配保护包只支持 Kyber（收到 {wrapping!r}）',
            C.ERR_ALGORITHM_NOT_ALLOWED,
        )
    ciphertext = package.get('encrypted_key') or package.get('encrypted_aes_key')
    if not ciphertext:
        raise PoolConsumeError(
            '保护包里没有密文本体（缺 encrypted_key）', C.ERR_INVALID_PARAMETER,
        )
    for required in ('kem_ciphertext', 'nonce', 'tag'):
        if not package.get(required):
            raise PoolConsumeError(
                f'保护包缺少 {required}', C.ERR_INVALID_PARAMETER,
            )
    return {
        'kem_ciphertext': package['kem_ciphertext'],
        'encrypted_key': ciphertext,
        'nonce': package['nonce'],
        'tag': package['tag'],
        'payload_algorithm': package.get('payload_algorithm') or 'sm4',
        'wrapping_algorithm': 'kyber_kem',
    }


def _build_delivery_envelope(*, package: Dict[str, Any], batch_id: str, sender: Node,
                             receiver: Node, recipient_key, key_hash: str,
                             expires_at) -> Tuple[Dict[str, Any], str]:
    """保护包 → **可签的节点信封**（返回 `(envelope, digest)`）。

    加上的是本次交付的元数据，**都被签名覆盖**（`NODE_ENVELOPE_SIGNED_FIELDS`）：
    `batch_id`（= 池号，发送方在预分配时就定下，见端点说明）、`sender/receiver_node_id`、
    `recipient_key_id/version`（接收方那一版长期密钥 —— **就是封装用的那一版**，
    由池项落库时记下的引用还原，不是"当前最新版"）、`expires_at`（**取池项自己的**，
    不接受调用方延长：否则一条即将过期的预分配资源可以被重新签名续命）、
    `key_hash`（发送方声称的 SHA256，供接收方解封后自查）。

    摘要算的是**归一后的内层密文**（`ciphertext_digest`），与现场封装那条路径同一口径。
    """
    inner = _normalize_protection_package(package)
    digest = ciphertext_digest(_canonical_inner_json(inner))
    envelope = {
        **inner,
        'batch_id': batch_id,
        'sender_node_id': sender.node_id,
        'receiver_node_id': receiver.node_id,
        'recipient_key_id': getattr(recipient_key, 'key_id', None),
        'recipient_key_version': getattr(recipient_key, 'key_version', None),
        'key_hash': key_hash,
        'ciphertext_digest': digest,
        'expires_at': expires_at.isoformat() if hasattr(expires_at, 'isoformat') else expires_at,
    }
    return envelope, digest


def envelope_canonical_bytes(envelope: Dict[str, Any]) -> bytes:
    """给端点用的规范字节串（补签名时的复验与它同源）。"""
    return node_canonical_payload(envelope)


def pool_summary(sender: Node, peers) -> list:
    """每个对端**可用**的预分配资源条数（分发页据此显示"可用预分配 N 条"）。

    只数 `READY` + 未过期 + 引用的长期密钥未回收。**不返回密文**：这是"有没有"的
    问题，不是"给我看看"的问题（密文对发送方本来也没用，那是封给接收方的）。
    """
    now = timezone.now()
    rows = (
        PreDistributedKey.objects
        .filter(recipient_type='pool', status__in=KeyPoolService.POOL_STATUS_READY_VALUES,
                expires_at__gt=now)
        .values('node1_id', 'node2_id', 'expires_at', 'pool_id')
    )
    peer_ids = {peer.id: peer for peer in peers}
    out: Dict[int, Dict[str, Any]] = {}
    for row in rows:
        # 池项记的是"这一对节点"，方向无关 —— 发送方可以是其中任一方
        # （`consume_key` 本身就是双向查的，见它的 docstring）。
        if row['node1_id'] == sender.id:
            peer_id = row['node2_id']
        elif row['node2_id'] == sender.id:
            peer_id = row['node1_id']
        else:
            continue
        if peer_id not in peer_ids:
            continue
        item = out.setdefault(peer_id, {
            'nodeCode': peer_ids[peer_id].node_id,
            'nodeName': peer_ids[peer_id].name,
            'available': 0,
            'expiresAt': None,
        })
        item['available'] += 1
        expiry = row['expires_at']
        if expiry is not None and (item['expiresAt'] is None or expiry < item['expiresAt']):
            # 取**最近**的过期时间：页面提示"最迟某时可用到此为止"，
            # 用最远的那条会让用户以为整批都能用到那时候。
            item['expiresAt'] = expiry
    return sorted(out.values(), key=lambda x: x['nodeCode'])


def consume_pool_item(*, sender: Node, receiver: Node, batch_id: str,
                      protection_algorithm: str, falcon_key_id: Any = None,
                      falcon_key_version: Any = None) -> Dict[str, Any]:
    """取用一条预分配资源并**建立 initiated 会话**。见模块 docstring。

    @return `{item, envelope, session, session_id, recipient_key, remaining}`
    @raise PoolConsumeError  业务拒绝（码见各分支）
    """
    canonical = C.canonical_algorithm(protection_algorithm)
    if canonical != 'KYBER':
        raise PoolConsumeError(
            f'预分配资源只支持 Kyber 保护包（收到 {protection_algorithm!r}）—— '
            f'SM2/SSCL 是用户腿的封装，预分配这条按量化口径只做格密码',
            C.ERR_ALGORITHM_NOT_ALLOWED,
        )

    # 池项引用的**接收方那一版**长期密钥 —— 封装它就是用它做的（预分配时落库的引用）。
    # 这里**先于**取用解析：拿不到具体版本就没法在信封里如实标注"用哪一版封的"，
    # 而信封一旦发出去就改不了了（签名覆盖它）。
    # 方向：池项是"这一对节点之间"的资源，谁取用谁就是本次的发送方 ——
    # 于是"接收方"是另一个。封错方向的话接收方解不开（而一切看起来都成功）。
    try:
        recipient_key = _receiver_registry_key(sender, receiver)
    except PoolConsumeError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise PoolConsumeError(
            f'无法确定接收节点 {receiver.node_id} 的 Kyber 长期密钥：{exc}',
            C.ERR_KEY_NOT_FOUND,
        ) from exc

    falcon_key = None
    if falcon_key_id is not None and falcon_key_version is not None:
        from .node_key_registry import require_key_version
        try:
            falcon_key = require_key_version(
                sender, 'FALCON', falcon_key_id, falcon_key_version,
            )
        except C.ContractError as exc:
            raise PoolConsumeError(
                f'发送方 Falcon 密钥不可用：{exc.message}', exc.code,
            ) from exc

    with transaction.atomic():
        # 取用（行锁 + 状态机 + 未过期 + 长期密钥复核全在 consume_key 里）。
        result = KeyPoolService.consume_key(sender.node_id, receiver.node_id, 'kyber_kem')
        if not result.get('success'):
            raise PoolConsumeError(
                result.get('message') or '没有可用的预分配密钥',
                result.get('code') or C.ERR_POOL_ITEM_UNAVAILABLE,
            )
        item = PreDistributedKey.objects.select_for_update().get(pk=result['key_id'])

        try:
            package = json.loads(item.encrypted_key_data or '{}')
        except (ValueError, TypeError):
            package = {}
        if not isinstance(package, dict) or not package:
            raise PoolConsumeError(
                '这条预分配资源的保护包无法解析（不是合法 JSON 对象）',
                C.ERR_ENVELOPE_TAMPERED,
            )

        envelope, digest = _build_delivery_envelope(
            package=package, batch_id=batch_id, sender=sender, receiver=receiver,
            recipient_key=recipient_key, key_hash=item.key_hash, expires_at=item.expires_at,
        )

        # 落回：这一行从此就是"交给接收方的信封"（`recipient_type` 已由
        # `consume_key` 翻成 'node'），内容换成**可签的节点信封**。
        item.encrypted_key_data = json.dumps(envelope, ensure_ascii=False, sort_keys=True)
        # 保护包的密文摘要与本次交付的摘要必须一致 —— 它进签名，落库留一份好核对。
        item.save(update_fields=['encrypted_key_data'])

        # 建会话（会话号带 key_index：一个池子 N 条 = N 个会话）。
        created = create_initiated_sessions(
            # ⚠️ 会话**必须挂在池号下**，不是调用方给的交付批次号：
            #    `node_session_views._session_of_batch` 是按「信封的 `pool_id` +
            #    `-n{节点}`」找会话的（那是接收方取信封、验签、确认都要用的关联键）。
            #    挂到交付批次号下的话，接收方那边恒报"批次没有对应到会话" ——
            #    加密一路都对，只在最后一步查不到人（实测踩过）。
            sender, {receiver.id: receiver}, [receiver.id], item.pool_id,
            item.expires_at, dispatch='pool_consume', session_type='kyber_kem',
            recipient_key=recipient_key, falcon_key=falcon_key,
            session_id_suffix=f'-k{item.key_index}',
        )
        if not created:
            # 会话没建起来 = 这条资源取用了却没有归属，比"取用失败"更难查
            # （接收方永远等不到会话行）。整段回滚，让这一条留在池子里。
            raise PoolConsumeError(
                f'取用成功但会话未能建立（{item.pool_id}-k{item.key_index}），本次取用已回滚',
                C.ERR_SESSION_STATE_INVALID,
            )

        from .models import SessionKey
        session = SessionKey.objects.filter(
            session_id=f'{item.pool_id}-k{item.key_index}-n{receiver.id}'
        ).first()

        remaining = (
            PreDistributedKey.objects
            .filter(recipient_type='pool', status__in=KeyPoolService.POOL_STATUS_READY_VALUES,
                    expires_at__gt=timezone.now())
            .filter(_pair_q(sender, receiver))
            .count()
        )

    logger.info('预分配取用：%s → %s（%s#%s，会话 %s）',
                sender.node_id, receiver.node_id, item.pool_id, item.key_index,
                session.session_id if session else '?')
    return {
        'item': item,
        'envelope': envelope,
        'digest': digest,
        'session': session,
        'session_id': session.session_id if session else '',
        'recipient_key': recipient_key,
        'remaining': remaining,
    }


def _pair_q(a: Node, b: Node):
    """无序节点对的条件（两个方向都算）。"""
    from django.db.models import Q
    return (
        Q(node1=a, node2=b) | Q(node1=b, node2=a)
    )


def _receiver_registry_key(sender: Node, receiver: Node):
    """接收方**当前可用**的 Kyber 长期密钥行。

    取用时要把它如实写进信封（签名覆盖 `recipient_key_id/version`）——
    取"当前可用那一版"是**正确**的，因为本次交付用的正是它（预分配资源在生成时
    就用它封了，而回收会让整批池项失效 —— 两处判据同源，不会出现"信封写着 A 版、
    实际封的是 B 版"）。
    """
    from .node_key_registry import require_usable_key
    return require_usable_key(receiver, 'KYBER')