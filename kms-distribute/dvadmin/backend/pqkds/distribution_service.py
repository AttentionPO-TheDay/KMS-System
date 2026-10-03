# -*- coding: utf-8 -*-
"""节点到节点分发的**编排层**（KMS-008 / 计划 §7 阶段 3 的请求模型）。

这一层负责什么
--------------
把"发送方节点 → 接收方节点"的一次分发，按**请求里显式指定的那一版接收方公钥**
封装成一份信封，并把由此产生的四样副作用一次做完：

    1. 落一条 `PreDistributedKey`（接收方取信封的入口就是查这张表）；
    2. 建一条 `DistributionBatch`（批次历史 / 链上存证的批次号）；
    3. 建一条 `initiated` 会话（双方据此继续 stage 4 的验签与确认）；
    4. 在事务**提交之后**补一条 `KEY_DISTRIBUTED` 链上存证。

为什么另起一个模块，而不是继续写进视图
--------------------------------------
视图层的 `distribute_to_user` 把编排、用户腿、节点腿、响应组装混在一个
两百行的函数里；KMS-008 需要在**不改变旧流程**的前提下长出第二条路径，
把新逻辑再塞进去会让"哪条路径做了什么"彻底看不出来。

更要紧的是**可测性**：本模块不出 HTTP 就能被 `tests/test_node_key_registry.py`
直接调用（与 KMS-007 的 `key_revocation_service` 同一条路数）。视图层只剩
参数解析与响应组装。

搬进来的三条助手
----------------
`create_initiated_sessions` / `record_distribution_chain_event` /
`classify_distribution` 原本是 `user_distribution_views` 的私有函数，
但它们是**新旧两条路径共用的副作用**。新服务若反过来从视图模块 import 它们，
依赖方向就成了"服务层 → 视图层"，而视图层又要 import 本模块组成响应 ——
那是一个循环的前身。所以移到这里，由视图层 import 本模块。

这次**不做**什么（KMS-009/010 的边界）
-------------------------------------
* 不在**节点侧**生成 SM4：本次仍由服务端生成、服务端封装（过渡实现），
  但**按请求指定的那一版公钥**封 —— 这正是 KMS-009 要接手的那个位置；
* 不做 Falcon 签名（KMS-010 补齐验签后，"没有签名就不能发送"才落得下）；
* 不写用户腿信封：新模型是节点到节点，没有"发起用户自己的那一份"，
  旧用户腿接口保留一段迁移期但已标记 deprecated。
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import timedelta
from typing import Any, Dict, List, Optional, Tuple

from django.db import transaction
from django.utils import timezone

from . import api_contract as C
from . import kms_service_client as kms
from .envelope_signature import ciphertext_digest
from .models import DistributionBatch, Node, PreDistributedKey, SessionKey, UserNodeAuthorization
from .node_key_registry import require_key_version
from .sm4_crypto import PAYLOAD_ALGORITHM_SM4, PayloadCipher
from .wrappers import NODE_WRAPPING_BY_CANONICAL, wrap_with_public_key

logger = logging.getLogger(__name__)

#: 信封默认有效期（小时）。旧用户腿流程把它**写死**成 24（D8：有效期一旦可调，
#: "对称密钥有时限"这条属性就会随部署漂移，而用户无从知道当前是多少）。
#: 新请求模型允许调用方显式给出 `expiresInHours`（§16.2 把有效期列为契约字段），
#: 但**限幅**——上限见下，理由同样是"不允许无期限的会话密钥"。
DEFAULT_EXPIRES_HOURS = 24

#: 有效期上限（7 天）。超过它直接拒绝而不是截断：
#: 截断会让"用户以为设了 30 天、实际只有 7 天"，而没有任何一处会告诉他。
MAX_EXPIRES_HOURS = 168


def _as_expires_hours(raw: Any) -> int:
    """把请求里的 `expiresInHours` 收敛成 1..MAX 的整数。**认不出就拒绝，不猜。**

    与 `node_self_views._as_bool`、`key_revocation_service._as_key_version` 同一条纪律：
    `bool` 要单独挡（`isinstance(True, int)` 为真，`int(True)` 得到 1 ——
    一个写错的 `expiresInHours: true` 会静默变成"1 小时"）。
    """
    if raw is None or raw == '':
        return DEFAULT_EXPIRES_HOURS
    if isinstance(raw, bool):
        raise C.ContractError(
            f'expiresInHours 应为 1..{MAX_EXPIRES_HOURS} 的整数：{raw!r}',
            code=C.ERR_INVALID_PARAMETER,
        )
    if isinstance(raw, int):
        hours = raw
    elif isinstance(raw, str) and raw.strip().isdigit():
        hours = int(raw.strip())
    else:
        raise C.ContractError(
            f'expiresInHours 应为 1..{MAX_EXPIRES_HOURS} 的整数：{raw!r}',
            code=C.ERR_INVALID_PARAMETER,
        )
    if not 1 <= hours <= MAX_EXPIRES_HOURS:
        raise C.ContractError(
            f'expiresInHours 应在 1..{MAX_EXPIRES_HOURS} 之间，收到 {hours}'
            f'（{DEFAULT_EXPIRES_HOURS} 是默认值）',
            code=C.ERR_INVALID_PARAMETER,
        )
    return hours


def authorized_node_ids(user_id: int) -> List[int]:
    """该用户当前有效的节点授权 ID 列表（**主键**，不是业务编号）。

    这里返回的是 `UserNodeAuthorization.node_id` 存的东西 —— 那是个外键
    （`ForeignKey(Node)`，无 `to_field`），所以是 `Node.pk`。
    调用方拿它去比 `node.id`；写成业务编号比会**恒不命中却不报错**，
    表现是"明明授权了却说你没权限"。
    """
    return list(
        UserNodeAuthorization.objects.filter(user_id=user_id, status='active')
        .values_list('node_id', flat=True)
    )


def create_initiated_sessions(sender_node, node_map, succeeded_node_ids, batch_id,
                              expires_at, *, dispatch: str = 'user_distribution',
                              session_type: str = 'kyber_kem') -> int:
    """为本次分发成功送达的每个节点登记一条 **initiated** 会话（文档 §6.5）。

    发起方是**发送节点**。取不到发送节点时（管理员发起的旧流程）**不建会话**：
    会话是"两个节点之间"的东西，没有发起节点就不存在这条边。

    只建 initiated，不建 established —— 理由见调用点的说明：
    验签（§6.3/§6.4）尚未实现，建 established 等于宣称一个没验证过的属性。

    幂等：session_id 由 batch_id + 节点后缀构成并带唯一约束，
    重复执行同一批次不会产生重复会话（走 get_or_create）。

    @param dispatch      写进 `key_exchange_data` 的"哪条分发路径建的"（排障入口）
    @param session_type  会话类型。KMS-008 起传**本次实际用的保护算法拼写**
                        （kyber_kem / gm_sm2 / gm_sscl）—— 该字段在
                        `node_session_views` 里就是以 `protectionAlgorithm` 的名义
                        下发的，旧流程一律硬编码 kyber_kem 是既有失真，新路径不再沿用。
    """
    if sender_node is None:
        logger.info('分发批次 %s：发起方未映射到节点，不建会话', batch_id)
        return 0

    created = 0
    for node_db_id in succeeded_node_ids:
        target = node_map.get(node_db_id)
        if target is None or target.id == sender_node.id:
            # 自己和自己不建会话（节点向自己分发的场景没有意义）
            continue
        session_id = f'{batch_id}-n{target.id}'
        try:
            _, was_created = SessionKey.objects.get_or_create(
                session_id=session_id,
                defaults={
                    'node1': sender_node,
                    'node2': target,
                    'session_type': session_type,
                    # 会话密钥本体不在服务端 —— 服务端只有包给双方的密文，
                    # 所以这两列如实标注"材料在信封里，不在本表"，
                    # 而不是塞一个占位明文进去（那会让"服务端不存明文"这条不变量失真）。
                    'encrypted_session_key': f'see envelopes of batch {batch_id}',
                    'key_exchange_data': json.dumps({
                        'batch_id': batch_id,
                        'dispatch': dispatch,
                        'note': '会话密钥经信封分发，服务端不持有明文',
                    }, ensure_ascii=False),
                    'status': 'initiated',
                    'expires_at': expires_at,
                },
            )
            if was_created:
                created += 1
        except Exception as exc:  # noqa: BLE001
            # 单节点建会话失败不该让整次分发回滚 —— 信封已经发给它了，
            # 回滚反而会造成"用户以为没发、节点其实收到了"的更糟状态。
            logger.warning('批次 %s 为节点 %s 建会话失败: %s', batch_id, target.node_id, exc)

    if created:
        logger.info('分发批次 %s：登记 %d 条 initiated 会话（发送方 %s）',
                    batch_id, created, sender_node.node_id)
    return created


def record_distribution_chain_event(event_type: str, key_id: int, key_version: int,
                                    owner_node_code: str, material_digest: str,
                                    batch_id: str) -> Optional[str]:
    """把一次分发记到链上（文档 §8.6 的 KEY_DISTRIBUTED）。

    <h2>为什么失败不影响分发结果</h2>
    <b>因为分发已经成功了</b> —— 信封已经落库、密钥已经在接收方手里。
    存证是**旁路增强**：链上少一条记录不会让已发生的事变成没发生。
    如果这里抛异常并回滚分发，就变成"链写不进去 ⇒ 接收方拿不到密钥"，
    把可用性问题升级成功能问题。

    所以：失败只记日志、**不改分发结论**。但调用方会把结果回显到响应里
    （`chainHash` 字段），让"存证没成功"这件事在界面上看得见 ——
    静默吞掉才是真正危险的：审计缺口会变成不可见。

    <h2>三个字段的口径（KMS-006/007 已确立，新路径沿用）</h2>
    * `key_id` —— **被用于建立会话的那把长期密钥**的整数主键。新流程里
      它就是**接收方**那一行 `NodeLongTermKey`（保护 SM4 的正是它）；
      旧流程传的是用户腿的 `kms.keymanage.key_id`。
    * `node_id` —— **keyId 的归属节点**（新流程 = 接收节点）。这条不变量
      与 KEY_UPDATED / KEY_REVOKED 一致，别在这里改成发送方：链上的
      "哪台机器的哪把钥匙"一旦分叉，回读时就无法回答"谁受影响"。

      ⚠️ Java 侧 `UpdatedelChainConsumer` 目前对 KEY_DISTRIBUTED 只记一条
         info、不做状态变更（那是对的：分发不是状态变迁）。所以这里传
         pqkds 的整数主键不会被拿去查 updatedel 的 `keymanage` 表。
    * `material_digest` —— 信封密文的 SHA256 摘要，不是密文本身，
      更不是任何密钥材料。

    ⚠️ 上链的是**摘要**：链上只需要能核验"是不是同一份东西"。
    """
    if not owner_node_code:
        # 没有归属节点就没有"谁的哪把钥匙"这个事实。宁可不上链，
        # 也不要编一个 owner 出来 —— 链上的记录一旦写错就撤不回来。
        logger.info('批次 %s：缺少密钥归属节点，跳过链上存证', batch_id)
        return None
    try:
        tx_hash = kms.record_chain_event(
            event_type,
            int(key_id),
            int(key_version or 0),
            owner_node_code,
            str(material_digest or ''),
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning('批次 %s 链上存证失败: %s', batch_id, exc)
        return None
    if tx_hash:
        logger.info('批次 %s 已上链存证: %s keyId=%s tx=%s',
                    batch_id, event_type, key_id, tx_hash)
    return tx_hash


def classify_distribution(source_node, target_nodes) -> Tuple[str, List[str], str]:
    """阶段 5（文档 §8.5）：判定本次分发是同域还是跨域。

    返回 `(发起方域, 目标域列表, 'same'|'cross'|'mixed')`。

    发起方域的取法：本系统的分发发起人是 `kms.sys_user`，而"域"是**节点**的属性
    （Node.domain_id，阶段 2 引入）。旧流程按 userId 反查节点，新流程的发起方
    本来就是节点，所以本函数直接收节点 —— 取不到节点时（管理员发起）返回空串。

    取不到时**整体判为 mixed** —— "不知道发起方在哪"时不应擅自断言成"同域"，
    那会把跨域分发粉饰成同域，正好掩盖了这个标记要暴露的东西。
    """
    source_domain = (getattr(source_node, 'domain_id', '') or '').strip()

    target_domains = sorted({
        (getattr(n, 'domain_id', '') or '').strip()
        for n in target_nodes
        if (getattr(n, 'domain_id', '') or '').strip()
    })

    if not source_domain or not target_domains:
        return source_domain, target_domains, 'mixed'

    same = [d for d in target_domains if d == source_domain]
    cross = [d for d in target_domains if d != source_domain]
    if cross and same:
        dist_type = 'mixed'
    elif cross:
        dist_type = 'cross'
    else:
        dist_type = 'same'
    return source_domain, target_domains, dist_type


def create_node_distribution(sender: Node, receiver: Node, *,
                             protection_algorithm: str,
                             recipient_key_id: Any,
                             recipient_key_version: Any,
                             expires_hours: Any = None) -> Dict[str, Any]:
    """发送节点 → 接收节点的一次分发：按**指定版本**封装并落全套副作用。

    这是 KMS-008「新请求契约」的服务端落点。与旧 `distribute_to_user` 的差别：

    | | 旧（用户腿） | 新（节点间） |
    |---|---|---|
    | 要 `source_key_id` | 要（用户自己的解封密钥） | **不要** |
    | 用哪把接收方公钥 | 物化列 = "当前生产版本" | **请求指定的那一版** |
    | 为谁封 | 用户本人 + 各节点 | 只有接收节点 |
    | 有效期 | 固定 24 小时 | 请求可给，限 1..168 |

    ⚠️ `protection_algorithm` 用**规范名**（SM2 / SSCL / KYBER）—— 与 §16 契约、
       §7 阶段 3 的写作一致；换算成封装拼写（gm_sm2 / kyber_kem …）只在
       `wrappers.NODE_WRAPPING_BY_CANONICAL` 一处发生。

    抛 `C.ContractError`：
      * 算法不在保护白名单（含 FALCON）→ `ALGORITHM_NOT_ALLOWED`；
      * 有效期越界/认不出 → `INVALID_PARAMETER`；
      * 接收方那一版不可用 → `require_key_version` 的四种码，原样透出。

    返回 dict（不是 HTTP 响应）：`{batch, batch_id, key_hash, digest,
    recipient_key, session_count, chain_hash, expires_at}`。
    """
    canonical = C.canonical_algorithm(protection_algorithm)
    if canonical not in C.PROTECTION_ALGORITHMS:
        # Falcon 走到这里也要给**这条**解释：它不是"不认识的算法"，
        # 而是职责不同 —— 它是签名算法，包不了 SM4（计划 §3）。
        raise C.ContractError(
            f'{protection_algorithm or "(空)"} 不能作为保护算法：'
            f'可选 {"/".join(C.PROTECTION_ALGORITHMS)}；Falcon 只用于签名与验签',
            code=C.ERR_ALGORITHM_NOT_ALLOWED,
        )
    wrapping = NODE_WRAPPING_BY_CANONICAL[canonical]
    hours = _as_expires_hours(expires_hours)

    # 指定哪版就查哪版 —— 查询先于封装发生，这是"版本真进了请求"的判据。
    key = require_key_version(receiver, canonical, recipient_key_id, recipient_key_version)

    payload_key = PayloadCipher.generate_key()
    # ⚠️ 材料取自**登记行**（那一版），不是接收方的物化列 ——
    #    物化列只有"当前生产版本"，用它就回到了"选了 v1、实际封 v2"的老问题。
    #    两者存储形式相同（KYBER base64 / SM2·SSCL hex），所以同一套解码路径可用。
    envelope, key_hash = wrap_with_public_key(
        payload_key, key.public_key, wrapping, recipient_node_id=receiver.node_id,
    )
    envelope_json = json.dumps(envelope, ensure_ascii=False)
    digest = ciphertext_digest(envelope_json)

    batch_id = f'dist-{timezone.now().strftime("%Y%m%d%H%M%S")}-{uuid.uuid4().hex[:8]}'
    expires_at = timezone.now() + timedelta(hours=hours)

    with transaction.atomic():
        PreDistributedKey.objects.create(
            pool_id=batch_id,
            key_index=0,
            # `node1` = 收件节点（`node_session_views` 取信封就是按
            # `node1=<自己> AND recipient_type='node'` 查的）。
            node1=receiver,
            node2=None,
            algorithm=wrapping,
            wrapping_algorithm=wrapping,
            payload_algorithm=PAYLOAD_ALGORITHM_SM4,
            # 新模型没有"用户来源密钥"。留 NULL 而不是编一个 0：
            # 0 会被下游当成一把真的 key_id 去查。
            source_key_id=None,
            recipient_type='node',
            encrypted_key_data=envelope_json,
            key_hash=key_hash,
            status='distributed',
            expires_at=expires_at,
            # KMS-007 为"这一项是用哪把长期密钥封的"补的两列 —— 新流程里
            # 它从"生成时顺手记下的"升级为"**请求指定的、封装实际用的**那一版"，
            # 于是回收时的精确失效天然命中，不需要任何退化匹配。
            long_term_key_id=key.key_id,
            long_term_key_version=key.key_version,
        )

        src_domain, target_domains, dist_type = classify_distribution(sender, [receiver])
        batch = DistributionBatch.objects.create(
            batch_id=batch_id,
            user_id=sender.sys_user_id,
            # 同上：新模型没有用户来源密钥。
            source_key_id=None,
            wrapping_algorithm=wrapping,
            node_ids=json.dumps([receiver.id]),
            node_success_count=1,
            # 没有用户腿，这一列如实记 False（旧流程它表示"用户那份也成功了"）。
            user_envelope_ok=False,
            status='success',
            source_domain_id=src_domain,
            target_domain_ids=json.dumps(target_domains, ensure_ascii=False),
            distribution_type=dist_type,
        )

        session_count = create_initiated_sessions(
            sender, {receiver.id: receiver}, [receiver.id], batch_id, expires_at,
            dispatch='node_distribution', session_type=wrapping,
        )

    # 上链在事务**提交之后**（与 KMS-006/007 同口径）：存证失败不该回滚一次
    # 已经成立的分发 —— 信封已经落库、接收方已经能取到它。
    chain_hash = record_distribution_chain_event(
        'KEY_DISTRIBUTED',
        key.pk,
        key.key_version,
        receiver.node_id,
        digest,
        batch_id,
    )

    return {
        'batch': batch,
        'batch_id': batch_id,
        # 回显本次用的两个拼写：规范名（请求口径）与封装拼写（库内口径）。
        # 分开回显是因为它们**不是一回事**（KYBER ↔ kyber_kem），
        # 排障时"请求说的"与"库里记的"对不上是最常见的困惑。
        'protection_algorithm': canonical,
        'wrapping_algorithm': wrapping,
        'key_hash': key_hash,
        'digest': digest,
        'recipient_key': key,
        'session_count': session_count,
        'chain_hash': chain_hash,
        'expires_at': expires_at,
    }


__all__ = [
    'DEFAULT_EXPIRES_HOURS',
    'MAX_EXPIRES_HOURS',
    'authorized_node_ids',
    'create_initiated_sessions',
    'record_distribution_chain_event',
    'classify_distribution',
    'create_node_distribution',
]
