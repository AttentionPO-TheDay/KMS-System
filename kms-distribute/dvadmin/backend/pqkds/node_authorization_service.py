# -*- coding: utf-8 -*-
"""节点授权**申请**的生命周期编排（任务书「节点多级授权」）。

    create_request()   节点发起申请（同一对节点无序去重，幂等）
    cancel_request()   发起方撤回（仅 pending、仅本人）
    decide_request()   管理员批准 / 驳回

**批准必须真的授予权限** —— 这是本模块唯一重要的设计约束
------------------------------------------------------
`decide_request(decision='approve')` 在一个事务里做两件事：把申请单标 `approved`，
**并写出 `UserNodeAuthorization` 行**（默认双向各一行）。放行判据自始至终只有
`distribution_service.authorized_node_ids` 一处，申请单的状态**不参与**任何放行判断。

仓库里有过教训：`kms-ops/mysql/init/06_permission_request.sql` 那套权限审批的
`approve()` 刻意不调用 `updateRoleLevel`，于是"审批通过"不改变任何权限，
阶段 8 被整体下线（`35_remove_permission_request_menu.sql`）：留着只会形成
**第二套权限语义** —— 出事时没人能说清"这个操作当时到底凭什么被允许"。

为什么去重放在事务里而不是唯一约束
----------------------------------
"同一对节点同时只允许一条 pending"是**无序对**上的约束
（A→B 与 B→A 是同一个意图：两个节点互通）。`unique_together` 表达不了无序对，
而 MySQL 没有部分唯一索引（部分索引在 Django + MySQL 上会**静默不建**，
见 `models.NodeLongTermKey.active_slot` 那段注释的实测）。所以在事务内
`select_for_update` 查两个方向。

方向：为什么批准默认双向
------------------------
接收方取自己的信封**不需要授权**（`node_session_views.node_envelopes` 按
`node1=自己` 查），所以单授 A→B 时 A 能发、B 回不了 —— 而"形成会话"是双向的。
申请单表达的正是"这两个节点互通"，因此默认写两行；管理员手工只授单向仍是允许的
（既有页面做得到），名录会如实显示不对称并允许补齐（见 `node_self_views.node_directory`）。
"""

from __future__ import annotations

import hashlib
import logging
from typing import Any, Dict, Optional

from django.db import IntegrityError, transaction
from django.utils import timezone

from . import api_contract as C
from .authorization_service import grant_authorization
from .models import Node, NodeAuthorizationRequest, UserNodeAuthorization

logger = logging.getLogger(__name__)

#: 申请理由的长度上限（与模型 `reason` 列同宽）。
MAX_REASON_LEN = 200


class AuthorizationRequestError(Exception):
    """申请流程里的**业务拒绝**。带 `code`（`api_contract.ERR_*`）供调用方分支。"""

    def __init__(self, message: str, code: str = C.ERR_INVALID_PARAMETER):
        super().__init__(message)
        self.message = message
        self.code = code


def _pending_key(requester: Node, target: Node) -> str:
    """未决去重键。**无序**：同一对节点不论谁申请，键相同。

    ⚠️ 这一列是"同一对节点同时只有一条 pending"的**数据库级**保证
       （`unique=True` + 离开 pending 时置 NULL）。只在视图里查一遍是不够的 ——
       见 `models.NodeAuthorizationRequest` 的 docstring。
    """
    a, b = sorted((int(requester.pk), int(target.pk)))
    return f'{a}-{b}'


def _close_pending(row: NodeAuthorizationRequest) -> None:
    """把申请带离 pending 状态：置 `NULL` 释放去重键（**唯一允许的写法**）。

    忘了释放的表现是"这一对节点再也申请不了"—— 旧键一直占着唯一索引，
    而报错只是唯一约束冲突，看起来像"重复提交"，很难联想到是终态没清键。
    """
    row.pending_key = None


def _pair_filter(requester: Node, target: Node):
    """无序对的过滤条件（两个方向都算"这一对"）。"""
    from django.db.models import Q
    return Q(requester=requester, target=target) | Q(requester=target, target=requester)


def pending_request_between(a: Node, b: Node) -> Optional[NodeAuthorizationRequest]:
    """这一对节点之间**未决**的申请（任一方向）；没有返回 None。"""
    return (
        NodeAuthorizationRequest.objects
        .filter(_pair_filter(a, b), status='pending')
        .order_by('-create_datetime')
        .first()
    )


def effective_authorizations(requester: Node, target: Node) -> Dict[str, bool]:
    """这对节点之间**当前生效**的授权方向（读的仍是唯一的判据表）。

    @return `{'outgoing': bool, 'incoming': bool}`
      * `outgoing` —— requester 能发给 target（requester.sys_user → target 有 active 行）
      * `incoming` —— target 能发给 requester

    ⚠️ 两个方向**分别判**，不要合成一个"已授权"布尔：管理员手工只授单向是合法的，
       合成之后"能发给对方但对方回不了"这种不对称就看不见了。
    """
    user_ids = {
        'outgoing': requester.sys_user_id,
        'incoming': target.sys_user_id,
    }
    nodes = {'outgoing': target, 'incoming': requester}
    out = {}
    for key, uid in user_ids.items():
        if not uid:
            # 节点没绑登录账号（数据不一致）—— 谈不上授权，如实为 False。
            out[key] = False
            continue
        out[key] = UserNodeAuthorization.objects.filter(
            user_id=int(uid), node=nodes[key], status='active',
        ).exists()
    return out


def create_request(requester: Node, target: Node, reason: str) -> Dict[str, Any]:
    """节点发起申请。返回 `{'request': ..., 'created': bool, 'alreadyGranted': bool}`。

    ⚠️ 幂等：这一对已有 pending 时**返回那一行**，不新建（`created=False`）。
    ⚠️ 两个方向都已 active 时**不建申请**，回 `alreadyGranted=True` ——
       此时申请没有意义，建了只会让管理员批一件已经成立的事。
       注意判据是"**两个方向都** active"：只授了单向时申请仍然是必要的
       （补齐另一个方向），这与 `effective_authorizations` 分开判方向是同一条理由。
    """
    if requester.id == target.id:
        raise AuthorizationRequestError('不能与自己建立会话', C.ERR_INVALID_PARAMETER)
    if _public_status(target) == 'DISABLED':
        raise AuthorizationRequestError(
            f'节点 {target.node_id} 已停用，无法申请与它通信', C.ERR_INVALID_PARAMETER,
        )
    if not requester.sys_user_id or not target.sys_user_id:
        raise AuthorizationRequestError(
            '节点尚未绑定登录账号，无法建立授权关系（请联系管理员重建节点）',
            C.ERR_INVALID_PARAMETER,
        )

    reason = str(reason or '').strip()
    if not reason:
        raise AuthorizationRequestError('请填写申请理由（审批人据此判断）', C.ERR_INVALID_PARAMETER)
    if len(reason) > MAX_REASON_LEN:
        raise AuthorizationRequestError(
            f'申请理由过长（上限 {MAX_REASON_LEN} 字）', C.ERR_INVALID_PARAMETER,
        )

    # 事务 A：查重 + 插入。
    #
    # ⚠️ 并发下"自己先查一遍"拦不住两个标签页同时申请（`select_for_update` 锁的是
    #    **已存在的行**，而此刻两边的行都还不存在）—— 真正的保证是 `pending_key`
    #    上的唯一索引。冲突时**必须**这样兜：
    #
    #      1. 内层 `transaction.atomic()` 形成 savepoint：唯一键冲突只回滚这一条插入，
    #         外层事务仍可用。曾经写成"在同一个 atomic 里 except IntegrityError 再查"，
    #         那是**必然失败**的 —— Django 一旦在 atomic 块里见到 IntegrityError，
    #         就把连接标记为"需要回滚"，后续任何查询都抛
    #         `TransactionManagementError: An error occurred in the current transaction`。
    #         （本仓 `consume_key` 有过同类两层断口，见 PROJECT_PROGRESS §2.x。）
    #      2. 回读放在**外层事务之外**（新事务 = 新快照）。MySQL 默认 REPEATABLE READ，
    #         同一事务里的普通 SELECT 用的是事务开始时的快照 —— 那里面**看不到**
    #         并发提交的那一行，回读会得到 None，把一次正常的并发去重误报成失败。
    created = False
    row = None
    try:
        with transaction.atomic():
            if all(effective_authorizations(requester, target).values()):
                return {'request': None, 'created': False, 'alreadyGranted': True}

            existing = (
                NodeAuthorizationRequest.objects
                .select_for_update()
                .filter(_pair_filter(requester, target), status='pending')
                .order_by('-create_datetime')
                .first()
            )
            if existing is not None:
                return {'request': existing, 'created': False, 'alreadyGranted': False}

            row = NodeAuthorizationRequest.objects.create(
                requester=requester, target=target, status='pending', reason=reason,
                pending_key=_pending_key(requester, target),
            )
            created = True
    except IntegrityError:
        # 只可能是 `pending_key` 的唯一索引：这一对该有别的 pending 了。
        # 具体是哪一条、还流不流得住，交给下面那个新事务去回答。
        created = False

    if not created:
        row = (
            NodeAuthorizationRequest.objects
            .filter(_pair_filter(requester, target), status='pending')
            .order_by('-create_datetime')
            .first()
        )
        if row is None:
            # 撞了唯一键、新事务里又看不到 pending —— 只可能是被抢先建完又立刻处置掉了。
            # 如实报错让调用方重试，**不要**编一个成功（编出来的"申请已提交"点开是空的）。
            raise AuthorizationRequestError(
                '申请未创建成功（并发冲突），请刷新后重试', C.ERR_INVALID_PARAMETER,
            )
        return {'request': row, 'created': False, 'alreadyGranted': False}

    logger.info('节点授权申请：%s → %s（%s）', requester.node_id, target.node_id, reason[:40])
    return {'request': row, 'created': True, 'alreadyGranted': False}


def cancel_request(requester: Node, request_id: int) -> NodeAuthorizationRequest:
    """发起方撤回自己的待审批申请。**只能撤自己发起的、且仍在 pending 的。**"""
    with transaction.atomic():
        row = (
            NodeAuthorizationRequest.objects
            .select_for_update()
            .filter(pk=request_id)
            .first()
        )
        if row is None:
            raise AuthorizationRequestError(
                f'申请不存在：{request_id}', C.ERR_KEY_NOT_FOUND,
            )
        if row.requester_id != requester.id:
            # 别人的申请撤不了 —— 包括"我是这条申请的目标节点"也不行：
            # 目标节点的意见走审批意见，不构成撤回权。
            raise AuthorizationRequestError(
                '只能撤回自己发起的申请', C.ERR_NOT_AUTHORIZED,
            )
        if row.status != 'pending':
            raise AuthorizationRequestError(
                f'该申请已是「{row.get_status_display()}」，不能撤回', C.ERR_SESSION_STATE_INVALID,
            )
        row.status = 'cancelled'
        row.decided_at = timezone.now()
        _close_pending(row)  # 释放去重键，允许以后重新申请
        row.save(update_fields=['status', 'decided_at', 'pending_key'])
    logger.info('节点授权申请已撤回：%s → %s（#%s）',
                requester.node_id, row.target.node_id, row.pk)
    return row


def decide_request(
    request_id: int,
    *,
    decision: str,
    identity: Optional[Dict[str, Any]] = None,
    remark: str = '',
    bidirectional: bool = True,
) -> Dict[str, Any]:
    """管理员批准 / 驳回一条申请。

    @return `{request, decided, alreadyDecided, granted:{created,reactivated}, chain_payload}`
      `chain_payload` 是给调用方上链用的 `(event_type, key_id, node_id, material_hash)`
      —— 本函数**不**自己上链：上链必须在事务**提交之后**做（`record_chain_event`
      失败不该回滚一次已经成立的批准），那是视图层的职责。

    ⚠️ 批准 = 写授权行，不是改一个状态字。见模块 docstring。
    """
    if decision not in ('approve', 'reject'):
        raise AuthorizationRequestError(
            f'decision 只能是 approve / reject，收到 {decision!r}', C.ERR_INVALID_PARAMETER,
        )
    remark = str(remark or '').strip()
    if decision == 'reject' and not remark:
        # 驳回必须给理由：节点侧看到的只有这句话，空着等于让人猜。
        raise AuthorizationRequestError('驳回必须填写理由', C.ERR_INVALID_PARAMETER)

    requester_label = str((identity or {}).get('userName') or (identity or {}).get('userId') or 'admin')

    with transaction.atomic():
        row = (
            NodeAuthorizationRequest.objects
            .select_for_update()
            .select_related('requester', 'target')
            .filter(pk=request_id)
            .first()
        )
        if row is None:
            raise AuthorizationRequestError(f'申请不存在：{request_id}', C.ERR_KEY_NOT_FOUND)
        if row.status != 'pending':
            # 幂等：已处置过的再处置不改动任何东西，如实回报它现在的状态。
            return {
                'request': row, 'decided': False, 'alreadyDecided': True,
                'granted': {'created': [], 'reactivated': []}, 'chain_payload': None,
            }

        granted_created, granted_reactivated = [], []
        if decision == 'approve':
            grants = [(row.requester, row.target)]
            if bidirectional:
                grants.append((row.target, row.requester))
            for owner, peer in grants:
                result = grant_authorization(
                    peer.sys_user_id, owner,
                    identity=identity,
                    remark=f'节点授权申请 #{row.pk} 批准' + (f'：{remark}' if remark else ''),
                    granted_via='审批',
                )
                if result['created']:
                    granted_created.append(f'{peer.node_id}→{owner.node_id}')
                elif result['reactivated']:
                    granted_reactivated.append(f'{peer.node_id}→{owner.node_id}')
            row.status = 'approved'
        else:
            row.status = 'rejected'

        row.decided_by = requester_label
        row.decided_at = timezone.now()
        row.decision_remark = remark or None
        _close_pending(row)  # 离开 pending：释放去重键
        row.save(update_fields=['status', 'decided_by', 'decided_at', 'decision_remark', 'pending_key'])

    event_type = 'AUTH_GRANTED' if decision == 'approve' else 'AUTH_REJECTED'
    chain_payload = {
        'event_type': event_type,
        # ⚠️ `keyId` 位填**申请单主键**（链上惯例是"一把真实密钥行"，授权没有对应
        #    密钥）。这条拉伸的边界写在 Java 侧 `ChainSyncEvent` 的注释里：
        #    AUTH_* 类型下 keyId 解释为申请单号。**不为它造一把假密钥行。**
        'key_id': int(row.pk),
        # nodeId 位放这对节点的业务编号（127 字符上限够用）。
        'node_id': f'{row.requester.node_id}↔{row.target.node_id}',
        # 摘要位放这对关系的哈希，用于去重核对（不传任何材料本身）。
        'material_hash': hashlib.sha256(
            f'{row.requester.node_id}|{row.target.node_id}'.encode('utf-8')
        ).hexdigest(),
    }
    logger.info('节点授权申请 #%s 已%s（by %s）：%s ↔ %s',
                row.pk, '批准' if decision == 'approve' else '驳回',
                requester_label, row.requester.node_id, row.target.node_id)
    return {
        'request': row, 'decided': True, 'alreadyDecided': False,
        'granted': {'created': granted_created, 'reactivated': granted_reactivated},
        'chain_payload': chain_payload,
    }


def _public_status(node: Node) -> str:
    """与 `node_self_views._public_status` 同一口径（三态：ACTIVE/DISABLED/PENDING_INIT）。"""
    s = (node.status or '').lower()
    if s == 'active':
        return 'ACTIVE'
    if s in ('inactive', 'disabled'):
        return 'DISABLED'
    return 'PENDING_INIT'


__all__ = [
    'AuthorizationRequestError', 'MAX_REASON_LEN',
    'create_request', 'cancel_request', 'decide_request',
    'pending_request_between', 'effective_authorizations',
]
