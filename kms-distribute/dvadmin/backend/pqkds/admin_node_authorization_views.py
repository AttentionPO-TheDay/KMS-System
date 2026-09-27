# -*- coding: utf-8 -*-
"""管理端「节点鉴权」接口（P3 步骤 10 / D5）。

    GET  /admin/node-authorizations/            列表（可按用户/节点过滤）
    POST /admin/node-authorizations/            授权（幂等：已撤销的会重新激活）
    POST /admin/node-authorizations/<id>/revoke/ 撤销

为什么这些接口放在分发模块而不是管理端 Java
--------------------------------------------
授权关系住在 `falcon_kds`（`user_node_authorizations`），是分发模块自己的数据。
让管理端 Java 跨库去写它，会把"谁拥有这份数据"搞乱；这里只暴露 HTTP 接口，
管理端页面直接调即可。**这与 D7 的方向一致**：身份源在 KMS，业务数据各归其主。

权限怎么判定
------------
不能只靠"能调到这个接口就是管理员" —— 这些接口会**授予他人访问节点的权限**，
是最该收紧的一类操作。因此走与用户接口同一套自省：`roleLevel <= 0` 才算管理员（D9/D13）。
判定发生在**读取任何数据之前**，越权请求连列表都拿不到。
"""

from __future__ import annotations

import json
import logging

from django.db import transaction
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from . import kms_service_client as kms
from .models import Node, UserNodeAuthorization

logger = logging.getLogger(__name__)


def _ok(data=None):
    return JsonResponse({'code': 200, 'message': 'success', 'data': data},
                        json_dumps_params={'ensure_ascii': False})


def _error(message, http_status=400):
    return JsonResponse({'code': http_status, 'message': message, 'data': None},
                        status=http_status, json_dumps_params={'ensure_ascii': False})


def require_admin(view):
    """要求调用者是管理员（`roleLevel <= 0`，见 D13 两级角色）。

    与 `require_kms_user` 的差别只有一条：多一次角色判定。
    之所以单独写而不是加个参数，是因为"管理员接口"与"用户接口"的失败语义不同 ——
    前者被拒时不应泄露任何业务数据，也不该与"未登录"混为一谈。
    """

    def wrapper(request, *args, **kwargs):
        token = kms.extract_bearer_token(request)
        if not token:
            return _error('未登录：缺少 Authorization: Bearer <token>', 401)
        try:
            identity = kms.introspect(token)
        except kms.KmsTokenInvalid as exc:
            return _error(f'登录状态无效：{exc}', 401)
        except kms.KmsServiceError as exc:
            logger.error('KMS 自省失败: %s', exc)
            return _error('身份服务暂时不可用，请稍后重试', 503)

        # 角色层级取不到时**按最小权限处理**：宁可拒绝管理员，
        # 也不能因为读不到 roleLevel 就把接口放开给所有人。
        role_level = identity.get('roleLevel')
        if role_level is None or int(role_level) > 0:
            return _error('需要管理员权限', 403)

        request.kms_identity = identity
        return view(request, *args, **kwargs)

    wrapper.__name__ = getattr(view, '__name__', 'wrapped')
    return wrapper


@csrf_exempt
@require_http_methods(['GET'])
@require_admin
def admin_users(request):
    """账号列表代理（供管理端「用户选择器」用）。

    为什么要代理而不是让浏览器直连主 KMS：那个接口需要 `X-Internal-Token`，
    属于**服务间**凭据，绝不能下发到浏览器。这里以本模块的管理员门控为前置，
    用服务端持有的令牌转发 —— 内部令牌一步都不出服务端。

    账号列表本身可被用来枚举系统里有哪些人，因此这个门控不是可选项。
    """
    keyword = request.GET.get('keyword') or None
    try:
        users = kms.list_users(keyword)
    except kms.KmsServiceError as exc:
        logger.error('取账号列表失败: %s', exc)
        return _error('身份服务暂时不可用，请稍后重试', 503)

    items = [
        {
            'userId': item.get('userId'),
            'userName': item.get('userName'),
            # 管理员/普通用户的分流判据（D9/D13）；前端只用于展示
            'roleLevel': item.get('roleLevel'),
        }
        for item in users
    ]
    return _ok({'items': items, 'total': len(items)})


def _serialize(row: UserNodeAuthorization) -> dict:
    node = row.node
    return {
        'id': row.id,
        'userId': row.user_id,
        'nodeId': node.id,
        'nodeCode': node.node_id,
        'nodeName': node.name,
        'status': row.status,
        'grantedBy': row.granted_by,
        'grantedAt': row.granted_at.isoformat() if row.granted_at else None,
        'revokedAt': row.revoked_at.isoformat() if row.revoked_at else None,
        'remark': row.remark,
    }


@csrf_exempt
@require_http_methods(['GET', 'POST'])
@require_admin
def node_authorizations(request):
    """GET 列表 / POST 授权。"""
    if request.method == 'GET':
        queryset = UserNodeAuthorization.objects.select_related('node').order_by('-granted_at')
        raw_user = request.GET.get('userId')
        if raw_user:
            try:
                queryset = queryset.filter(user_id=int(raw_user))
            except (TypeError, ValueError):
                return _error('userId 必须是整数')
        raw_node = request.GET.get('nodeId')
        if raw_node:
            try:
                queryset = queryset.filter(node_id=int(raw_node))
            except (TypeError, ValueError):
                return _error('nodeId 必须是整数')
        status = request.GET.get('status')
        if status:
            queryset = queryset.filter(status=status)

        items = [_serialize(row) for row in queryset[:500]]
        return _ok({'items': items, 'total': len(items)})

    # ---- POST：授权 ----
    try:
        payload = json.loads(request.body or b'{}')
    except (ValueError, TypeError):
        return _error('请求体不是合法 JSON')
    if not isinstance(payload, dict):
        return _error('请求体应为 JSON 对象')

    raw_user = payload.get('userId') or payload.get('user_id')
    raw_node = payload.get('nodeId') or payload.get('node_id')
    if raw_user in (None, '') or raw_node in (None, ''):
        return _error('缺少 userId 或 nodeId')
    try:
        user_id = int(raw_user)
        node_id = int(raw_node)
    except (TypeError, ValueError):
        return _error('userId / nodeId 必须是整数')

    node = Node.objects.filter(id=node_id).first()
    if node is None:
        return _error(f'节点不存在：{node_id}', 404)

    identity = getattr(request, 'kms_identity', {})
    granted_by = identity.get('userName') or str(identity.get('userId') or '')
    remark = payload.get('remark')

    with transaction.atomic():
        # 幂等：已存在且 active 就原样返回；已撤销的**重新激活**而不是新建一行，
        # 否则同一对 (user, node) 会出现多行，而"到底有没有权限"就取决于遍历顺序了。
        row, created = UserNodeAuthorization.objects.select_for_update().get_or_create(
            user_id=user_id,
            node=node,
            defaults={
                'status': 'active',
                'granted_by': granted_by,
                'granted_at': timezone.now(),
                'remark': remark,
            },
        )
        if not created and row.status != 'active':
            row.status = 'active'
            row.granted_by = granted_by
            row.granted_at = timezone.now()
            row.revoked_at = None
            if remark:
                row.remark = remark
            row.save(update_fields=['status', 'granted_by', 'granted_at', 'revoked_at', 'remark'])

    return _ok({**_serialize(row), 'created': created})


@csrf_exempt
@require_http_methods(['POST'])
@require_admin
def revoke_node_authorization(request, pk):
    """撤销一条授权。

    用**软撤销**（置 `status='revoked'`）而不是删除：撤销是安全事件，
    保留"曾经授权给谁、什么时候收回的"对事后审计很重要。
    用户侧接口只认 `status='active'`，所以撤销立即生效。
    """
    row = UserNodeAuthorization.objects.select_related('node').filter(id=pk).first()
    if row is None:
        return _error(f'授权记录不存在：{pk}', 404)

    identity = getattr(request, 'kms_identity', {})
    if row.status == 'revoked':
        # 重复撤销不算错误（幂等），但要如实告诉调用方它已经是撤销状态
        return _ok({**_serialize(row), 'alreadyRevoked': True})

    row.status = 'revoked'
    row.revoked_at = timezone.now()
    row.save(update_fields=['status', 'revoked_at'])
    logger.info('撤销节点授权: id=%s user=%s node=%s by=%s',
                row.id, row.user_id, row.node_id, identity.get('userName'))
    return _ok(_serialize(row))