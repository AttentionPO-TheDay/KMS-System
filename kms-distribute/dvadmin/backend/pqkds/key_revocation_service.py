# -*- coding: utf-8 -*-
"""长期密钥回收的**影响面编排**（KMS-007 / 计划 §7 阶段 2「回收时同步禁止」）。

为什么另起一个模块，而不是塞回 `node_key_registry.revoke_public_key`
------------------------------------------------------------------
因为它办不到。`node_key_registry` 是**存储层**，它的职责是把一条记录改成
REVOKED 并清掉物化列 —— 那件事不需要知道池项和会话的存在。而"回收之后
哪些已经发出去的东西会变成废纸"要跨算法、跨表去查，`node_key_registry.py`
自己第 511-520 行的注释已经写明这一点，并把"回收后已建立的会话怎么办"
留给了 KMS-007。这里就是那个落点。

把编排放进存储层的另一个后果是**顺序**会失控：谁先谁后决定了失败时留下
什么状态，而存储层方法不该替调用方做这个决定。

三步的顺序不能换
----------------
1. **先回收密钥本身**（`revoke_public_key`）—— 它同时清空 `Node.<算法>_public_key`，
   这才是让四个业务入口开始拒绝的**唯一**动作；
2. 再失效池项；
3. 最后失效会话。

理由是失败方向：1 失败则什么都没发生（可重试，库里无变化）；反过来先清池项和
会话、再回收密钥，一旦回收失败就是**把正在用的会话杀了而密钥还活着** ——
本该拒绝的没拒绝、本该能用的不能用了，而两部分各自都"成功"返回过。

谁不做这件事（边界，别在这里顺手扩）
------------------------------------
* **用户腿信封**（`UserKeyEnvelope`）不动。它的 `source_key_id` 引用的是
  `kms.keymanage.key_id` —— **另一个库**的旧模型，不是 `NodeLongTermKey`；
  那条线的回收判断已经在主 KMS Java 侧做掉了（`UserPublicKeyService` → `KEY_REVOKED`）。
  在这里按 `NodeLongTermKey.key_id` 去匹配它，匹配上的是**碰巧同号的另一把密钥**，
  那比不匹配更糟。
* **`Node.status`** 不动，理由见 `node_key_registry.revoke_public_key` 的注释
  （整节点状态表达不了"某个算法缺一把主版本"）。
* **不写 `KeyDistributionLog`**。那张表的 action 列表、外键（`falcon_keypair`）
  都是 CL-Falcon 时代的形状，如今唯一的写入者 `kms_adapter.py` 是未挂路由的死代码。
  长期密钥自己的审计线索就在它自己那行上（`status` / `revoked_at` / `revoked_reason`），
  再写一份平行的日志只会产生两本能互相矛盾的账。
  「谁在什么时候点的回收」由 `ApiLoggingMiddleware` 的请求日志回答。

为什么**不**包一个外层事务
--------------------------
三步各自是原子的（`revoke_public_key` 带 `transaction.atomic`，会话失效那个
函数自己也带）。外层再包一层会把失败变成全有全无，看着更整齐，但有两个代价：

  * 会话失效函数**在它自己的原子块内部吞异常**（`session_invalidation_service.py`
    的 try/except 包住了整个查询与写入）。外层再套一层事务，等于让一个"吞掉
    数据库错误的块"参与外层提交 —— 提交什么取决于驱动怎么处置那条出错语句，
    不是一个能靠读代码确定的结果；
  * 本模块的每一步都是**可重入**的（下条），所以"失败后重试"比"整体回滚"
    更简单也更可靠。

重试是安全的，而且**重试能把没做完的补上**
------------------------------------------
已回收的密钥再撤一次是幂等的（`revoke_public_key` 直接返回）；池项只扫
READY/RESERVED、会话只扫活跃状态，所以第二步和第三步在重跑时各自只处理
**还没处理的那些**。因此这里刻意**不**在"已是 REVOKED"时提前 return：
那会让一次"密钥已撤、池项没来得及失效"的半成品状态**永久固化** ——
重试看起来成功了，实际上什么也没补。

返回的 `impact` 计数描述的是**本次调用**实际改了多少条，不是累计量。
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from . import api_contract as C
from .key_pool_service import KeyPoolService
from .models import Node, NodeLongTermKey
from .node_key_registry import revoke_public_key
from .session_invalidation_service import SessionInvalidationService

logger = logging.getLogger(__name__)

#: 调用方没给回收原因时的兜底。**不留空串** —— `revoked_reason` 是事后唯一能
#: 回答"这把为什么被撤"的地方，空着与"原因不明"无法区分。
_DEFAULT_REASON = '节点侧发起回收'


def _as_key_version(value: Any) -> int:
    """把版本号收敛成正整数。**认不出就拒绝，不猜。**

    和 `node_self_views._as_bool` 同一条纪律：这个值决定"撤哪一行"，
    猜错的方向是把**另一把版本**撤掉，而响应会照常返回成功。

    ⚠️ `bool` 必须单独挡：Python 里 `isinstance(True, int)` 为真，
       `int(True)` 得到 1 —— 一个写错的 `keyVersion: true` 会静默变成
       "撤 v1"，而那可能正是生产中的那一版。`0` 同样挡掉（版本号从 1 起）。
    """
    if isinstance(value, bool):
        raise C.ContractError('keyVersion 应为正整数版本号', code=C.ERR_INVALID_PARAMETER)
    if isinstance(value, int):
        version = value
    elif isinstance(value, str) and value.strip().isdigit():
        version = int(value.strip())
    else:
        raise C.ContractError(
            f'keyVersion 应为正整数版本号，收到 {value!r}', code=C.ERR_INVALID_PARAMETER,
        )
    if version < 1:
        raise C.ContractError(
            f'keyVersion 应为正整数版本号，收到 {version}', code=C.ERR_INVALID_PARAMETER,
        )
    return version


def revoke_long_term_key(
    node: Node, algorithm: str, key_id: str, key_version: Any, *, reason: str = '',
) -> Dict[str, Any]:
    """回收一把长期密钥，并如实处理、回报它的影响面。

    ⚠️ `key_id` 与 `key_version` **必须一起显式给出**，服务端不替调用方推断
       "当前那一把"。这与 KMS-006 给 `rotate` 定的纪律是同一条：被撤掉的是
       哪一行，事后只能靠这次请求的入参回答；服务端要是自己挑了"当前版本"，
       审计记录就成了一句无法复核的宣称 —— 而且"当前"在并发下还会变。

    抛 `C.ContractError`：参数非法是 `ERR_INVALID_PARAMETER`，
    指定的那一把不存在是 `ERR_KEY_NOT_FOUND`（都在 `api_contract` 里，
    调用方按 `code` 分支，不要去匹配文案）。
    """
    name = C.canonical_algorithm(algorithm)
    version = _as_key_version(key_version)
    key_id = str(key_id or '').strip()
    if not key_id:
        raise C.ContractError(
            'keyId 不能为空：回收必须指名要撤哪一把', code=C.ERR_INVALID_PARAMETER,
        )

    key = NodeLongTermKey.objects.filter(
        node=node, algorithm=name, key_id=key_id, key_version=version,
    ).first()
    if key is None:
        # 报"不存在"而不是"已回收"：这个入口撤的是**指定的那一行**，
        # 行不存在与行已撤是两件事，混成一句会让调用方以为找对了行。
        raise C.ContractError(
            f'{name} 密钥 {key_id} v{version} 不存在，无法回收',
            code=C.ERR_KEY_NOT_FOUND,
        )

    # 这两条必须在 revoke_public_key **之前**快照：它会把 status 就地改成 REVOKED，
    # 之后再读就分不出"本来就已经撤了"与"这次才撤的"。前者决定要不要上链存证
    # （重复发同一条存证会污染链上记录），后者决定影响面有多大。
    already_revoked = key.status == C.KEY_STATUS_REVOKED
    was_active = key.status == C.KEY_STATUS_ACTIVE

    # 1) 撤密钥本身（含清空 Node.<算法>_public_key）。
    revoke_public_key(key, (reason or '').strip() or _DEFAULT_REASON)

    # 2) 失效池项：那些用这把公钥封过、还没被消费的预分配条目，
    #    现在永远解不开了 —— 留在 READY 集合里只会浪费一次会话，
    #    并把真实故障伪装成偶发问题。
    #
    #    ⚠️ `algorithm=name` 不能省。KMS-007 之前创建的池项没有长期密钥引用
    #       （迁移 0017 刻意不回填），只能按"同节点 + 同算法"退化匹配；
    #       `name` 就是那条退化面的收窄条件。不传的话退化面会落到**该节点
    #       全部算法** —— 撤一把 Kyber 会把这台节点上其它算法的历史池项一并
    #       清掉，正是 D3 要修掉的那类误伤，只是范围小了一号。
    pool_items = KeyPoolService.revoke_pool_items_for_key(
        node.node_id, key_id, version=version, algorithm=name,
    )

    # 3) 失效会话。**精确到这一版密钥**（KMS-016 起）：按会话行上 KMS-011
    #    落库的四列版本引用匹配（接收侧保护密钥 / 发送侧 Falcon 签名密钥），
    #    而不是把该节点的全部活跃会话一并撤销 —— 后者的实测后果是"撤一把
    #    KYBER 把 SM2/SSCL 保护的会话也杀掉"（KMS-016 全量验收 §7 实测踩中）。
    #    历史行（无版本引用）按算法家族退化，如实记日志。与池项那条线的
    #    口径（KMS-007：精确面 + 退化面）保持一致。
    #
    #    ⚠️ `SessionKeyInvalidation.reason` 只能取它 choices 里列出的值。
    #      这里用 `manual_revocation`（"手动撤销"，语义正确且已声明），
    #      **不**新造一个 `key_revoked` —— 那个字段的 choices 里已经有一个
    #      未声明的值（更新路径写的 `node_key_updated`），再造一个只会让
    #      "哪些值真的会出现"更难回答。"撤的是哪把密钥"由本函数的返回值、
    #      `NodeLongTermKey.revoked_reason` 与链上事件回答，不靠这个字段。
    #
    #    ⚠️ 这个函数**吞异常**：内部任何失败都被转成 `{'success': False}`
    #      返回而不抛出。只看"没崩"就当成会话已失效，会得到"密钥已回收、
    #      会话还活着，而接口说一切正常"—— 所以下面必须看 `success`，
    #      且失败时如实回报，不把它算进成功的影响面。
    session_result = SessionInvalidationService.invalidate_sessions_for_node_key_update(
        node, reason='manual_revocation',
        algorithm=name, key_id=key_id, key_version=version,
    )
    sessions_ok = bool(session_result.get('success'))
    sessions = int(session_result.get('invalidated_count') or 0)
    if not sessions_ok:
        logger.error(
            '长期密钥回收后会话失效失败：node=%s %s/%s v%s —— %s（密钥已回收，'
            '会话可能仍处于活跃状态，需要重试本接口）',
            node.node_id, name, key_id, version, session_result.get('message'),
        )

    logger.warning(
        '长期密钥已回收：node=%s %s/%s v%s（原本%s）→ 池项 %s 条、会话 %s 条；'
        '密钥行已存在=%s，原因=%s',
        node.node_id, name, key_id, version,
        '生产版本' if was_active else '非生产版本',
        pool_items, sessions, already_revoked, key.revoked_reason,
    )

    return {
        'revoked': {
            'rowId': key.pk,
            'algorithm': key.algorithm,
            'keyId': key.key_id,
            'keyVersion': key.key_version,
            'status': key.status,
            'publicKeyHash': key.public_key_hash,
            'revokedAt': key.revoked_at.isoformat() if key.revoked_at else None,
            'revokedReason': key.revoked_reason,
            # 原本是不是生产版本：决定"这次回收有没有让某个算法暂时不可用"。
            # 撤一把早就被取代的旧版本是清账，撤生产版本是一次停服级事件，
            # 两者在下游要做的处置完全不同。
            'wasActive': was_active,
            # 本次调用之前它就已经是 REVOKED 了。放在这里是为了让调用方能区分
            # "这次撤的"与"早就撤了"——**尤其**用于上链：只有这次才转入终态的
            # 那一把才该发 KEY_REVOKED 存证，否则重试会把同一条记录重复上链。
            'alreadyRevoked': already_revoked,
        },
        'impact': {
            'poolItems': int(pool_items or 0),
            'sessions': sessions,
            # 会话那一半是否**确实**做成了。为 False 时上面的 `sessions` 是 0，
            # 而真实的活跃会话数可能大于 0 —— 调用方必须看这个标志，
            # 不能拿 `sessions == 0` 当成"没有会话受影响"。
            'sessionsOk': sessions_ok,
            'sessionMessage': session_result.get('message') or '',
        },
    }


__all__ = ['revoke_long_term_key']
