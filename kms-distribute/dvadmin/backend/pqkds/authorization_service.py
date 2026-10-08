# -*- coding: utf-8 -*-
"""通信授权的**写入**收敛点（节点多级授权）。

为什么单独一个模块
------------------
授权行（`UserNodeAuthorization`）此前只有管理端手工授/撤一个写点，逻辑直接
写在视图里。节点授权申请落地后，写点变成三个（手工授权、手工撤销、审批批准），
而它们共享两条必须一致的不变量：

  1. **同一 (user_id, node) 只有一行**（模型有 `unique_together`）。已撤销的
     要**重新激活**那一行，不能新建 —— 新建会撞唯一约束，而"绕过它"的做法
     （比如先删再建）会让"曾经授权给谁、什么时候收回的"这段审计消失；
  2. **撤销是软撤销**（`status='revoked'` + `revoked_at`），不删行 —— 撤销是
     安全事件，事后要能回答"谁在什么时候收回了什么"。

两处各写一遍必然漂移，而漂移的表现是"同一个动作在不同入口下留下不同的痕迹"。

⚠️ 本模块**只写**授权行，不读它做判据。放行判据永远是
   `distribution_service.authorized_node_ids`（唯一读点）。这条边界是刻意的：
   仓库原先那套权限审批被下线，就因为它的审批事件本身被当成了权限依据
   （见 `kms-ops/mysql/init/35_remove_permission_request_menu.sql`）。
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from django.db import transaction
from django.utils import timezone

from .models import Node, UserNodeAuthorization

logger = logging.getLogger(__name__)

#: `UserNodeAuthorization.granted_by` 对"管理员手工授权"的写法。
MANUAL_GRANT_BY_MAX = 64


def _granted_by_label(identity: Optional[Dict[str, Any]], *, via: str) -> str:
    """授权人栏的写法。**区分"手工授的"与"审批授的"** ——
    两者在事后追责时是不同的问题（"谁点的按钮" vs "依据哪张申请单"）。
    审批路径的调用方会把申请单号拼进来（见 `grant_authorization`）。
    """
    name = str((identity or {}).get('userName') or (identity or {}).get('userId') or '').strip()
    return f'{via}:{name}' if name else via


def grant_authorization(
    user_id: int,
    node: Node,
    *,
    identity: Optional[Dict[str, Any]] = None,
    remark: str = '',
    granted_via: str = '手工',
) -> Dict[str, Any]:
    """写一行通信授权（幂等）。**必须在一个已经打开的事务里调用。**

    @return `{'granted': bool, 'created': bool, 'reactivated': bool, 'row': UserNodeAuthorization}`
      * `created`     —— 这次新建了一行；
      * `reactivated` —— 这行早就存在、刚被从 `revoked` 重新激活；
      * `granted`     —— 调用结束时它是 `active`（含"本来就是 active"的幂等情形，
                         此时 created/reactivated 都是 False）。

    ⚠️ 三个标志分开回，是为了让审批响应能如实说出"这次到底改变了什么"：
       两个方向的授权可能一个早就存在、另一个才新建，"都是 200"会把这点抹掉。
    """
    granted_by = _granted_by_label(identity, via=granted_via)
    row, created = UserNodeAuthorization.objects.select_for_update().get_or_create(
        user_id=int(user_id),
        node=node,
        defaults={
            'status': 'active',
            'granted_by': granted_by,
            'granted_at': timezone.now(),
            'remark': remark or None,
        },
    )
    reactivated = False
    if not created and row.status != 'active':
        row.status = 'active'
        row.granted_by = granted_by
        row.granted_at = timezone.now()
        row.revoked_at = None
        if remark:
            row.remark = remark
        row.save(update_fields=['status', 'granted_by', 'granted_at', 'revoked_at', 'remark'])
        reactivated = True

    return {
        'granted': row.status == 'active',
        'created': created,
        'reactivated': reactivated,
        'row': row,
    }


def revoke_authorization(row: UserNodeAuthorization) -> Dict[str, Any]:
    """软撤销一行授权。**必须在一个已经打开的事务里调用。**

    @return `{'revoked': bool, 'alreadyRevoked': bool, 'row': ...}`
      重复撤销不算错误（幂等），但 `alreadyRevoked=True` 如实告诉调用方它本来就是这个状态。
    """
    if row.status == 'revoked':
        return {'revoked': True, 'alreadyRevoked': True, 'row': row}
    row.status = 'revoked'
    row.revoked_at = timezone.now()
    row.save(update_fields=['status', 'revoked_at'])
    return {'revoked': True, 'alreadyRevoked': False, 'row': row}


__all__ = ['grant_authorization', 'revoke_authorization']
