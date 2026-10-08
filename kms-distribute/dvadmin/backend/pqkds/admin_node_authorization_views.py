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
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from . import kms_service_client as kms
from .authorization_service import grant_authorization, revoke_authorization
from .kms_service_client import record_chain_event
from .models import Node, NodeAuthorizationRequest, UserNodeAuthorization

logger = logging.getLogger(__name__)


def _ok(data=None, msg=None):
    """成功响应。`msg` 缺省是 `'success'` —— 审批类接口需要说清「这次做了什么」
    （批准了几个方向、是否重新激活），所以允许覆盖；不传时行为与从前一字不差。
    """
    return JsonResponse({'code': 200, 'message': msg or 'success', 'data': data},
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


def _auth_chain_args(row: UserNodeAuthorization, event_type: str):
    """授权事件的链上参数（`record_chain_event` 的位置参数）。

    ⚠️ 与节点侧审批路径（`node_authorization_service.decide_request`）同一口径：
       授权没有对应的"密钥行"，链上 `keyId` 位填**授权行主键**，`nodeId` 位填
       "被授权方→节点"的业务编号。这条拉伸的边界写在 Java 侧 `ChainSyncEvent`
       的注释里（`AUTH_*` 类型下 `keyId` 解释为授权/申请单号）。

    ⚠️ `keyId` 必须是**整数**：链上接口只收整数，字符串会被解析失败吞成
       "存证未成功"（见 `node_self_views` 里 KEY_UPDATED 的同类注释）。
    """
    import hashlib

    owner = ''
    try:
        owner = row.node.node_id if row.node_id else ''
    except Exception:  # noqa: BLE001 —— 关联对象取不到不该让存证本身抛出去
        owner = ''
    material = hashlib.sha256(f'{row.user_id}|{owner}'.encode('utf-8')).hexdigest()
    return (event_type, int(row.pk), 0, f'user:{row.user_id}→{owner}', material)


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
    remark = payload.get('remark')

    with transaction.atomic():
        # 幂等：已存在且 active 就原样返回；已撤销的**重新激活**而不是新建一行，
        # 否则同一对 (user, node) 会出现多行，而"到底有没有权限"就取决于遍历顺序了。
        #
        # ⚠️ 这段逻辑与节点授权审批路径**共用** `authorization_service.grant_authorization`
        #    —— 两处各写一遍必然漂移，而漂移的表现是"同一个动作在不同入口下
        #    留下不同的痕迹"（比如一边重新激活、一边试图新建然后撞唯一约束）。
        result = grant_authorization(
            int(user_id), node, identity=identity, remark=remark or '',
            granted_via='手工',
        )
        row = result['row']

    # 计划 §7 阶段 2 判据④的同类要求：授权变更进链上存证（与审批路径同一口径）。
    # ⚠️ 位置在事务**之外**：存证失败不该回滚一次已经成立的授权。
    # ⚠️ `_auth_chain_args` 只收 (行, 事件类型) —— 多传一个参数会抛
    #    `TypeError: takes 2 positional arguments but 3 were given`，
    #    表现为**整个接口 500**（`code` 变成 undefined），而报错信息里
    #    看不出是哪一步（实测踩到：verify-governance 的手工授权那条挂掉）。
    chain_tx = record_chain_event(*_auth_chain_args(row, 'AUTH_GRANTED')) or ''

    return _ok({
        **_serialize(row),
        'created': result['created'],
        # 如实区分"新建"与"重新激活"：两者对调用方是不同的事实。
        'reactivated': result['reactivated'],
        'chainHash': chain_tx,
    })


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
        return _ok({**_serialize(row), 'alreadyRevoked': True, 'chainHash': ''})

    result = revoke_authorization(row)
    logger.info('撤销节点授权: id=%s user=%s node=%s by=%s',
                row.id, row.user_id, row.node_id, identity.get('userName'))
    # 与授权同一口径：变更进链上存证，位置在事务外、失败不阻断（软撤销自身已提交）。
    chain_tx = record_chain_event(*_auth_chain_args(row, 'AUTH_REVOKED')) or ''
    return _ok({**_serialize(row), 'alreadyRevoked': result['alreadyRevoked'], 'chainHash': chain_tx})


# ---------------------------------------------------------------------------
# 任务书「节点多级授权」：授权申请的审批（管理端）
# ---------------------------------------------------------------------------
# 节点在「节点授权」页发起申请，管理员在「节点分发授权」页的待审批区处置。
#
# ⚠️ 本段的核心纪律（写在最前面，改这里之前先读）：
#   **批准 = 真的写授权行**（默认双向各一行），不是改一个状态字。
#   申请单的 `status='approved'` 不参与任何放行判断 —— 放行判据自始至终是
#   `distribution_service.authorized_node_ids`（只读 `UserNodeAuthorization`）。
#   仓库里那套被下线的权限审批（`kms-ops/mysql/init/35_remove_permission_request_menu.sql`）
#   就是"批了不等于授权"的反面教材：它保留了两套权限语义，出事时说不清
#   "这个操作当时凭什么被允许"。

def _request_admin_payload(row: NodeAuthorizationRequest) -> dict:
    """一条申请 → 审批人需要的形状。

    比节点侧多三样"当场判断"用的信息：这对节点**已有哪些授权行**（含已撤销的 ——
    它决定批准时是"新建"还是"重新激活"，审批人该知道）、以及两个节点是否
    还没绑登录账号（那会让批准必然失败，界面据此禁用按钮而不是等报错）。
    """
    out = {
        'id': row.pk,
        'status': row.status,
        'statusLabel': row.get_status_display(),
        'reason': row.reason,
        'requesterNodeCode': row.requester.node_id,
        'requesterNodeName': row.requester.name,
        'targetNodeCode': row.target.node_id,
        'targetNodeName': row.target.name,
        'createdAt': row.create_datetime.isoformat() if row.create_datetime else None,
        'decidedBy': row.decided_by or '',
        'decidedAt': row.decided_at.isoformat() if row.decided_at else None,
        'decisionRemark': row.decision_remark or '',
        'chainTx': row.chain_tx or '',
        # 批准必然失败的前置条件 —— 摆在列表上，别让管理员点完才知道。
        'requesterUserMissing': not row.requester.sys_user_id,
        'targetUserMissing': not row.target.sys_user_id,
    }
    directions = {
        'forward': (row.requester.sys_user_id, row.target),
        'backward': (row.target.sys_user_id, row.requester),
    }
    for name, (uid, node) in directions.items():
        if not uid:
            out[f'existing{name.capitalize()}'] = {'status': 'none', 'authorizationId': None}
            continue
        existing = UserNodeAuthorization.objects.filter(user_id=int(uid), node=node).first()
        out[f'existing{name.capitalize()}'] = {
            'status': existing.status if existing else 'none',
            'authorizationId': existing.pk if existing else None,
        }
    return out


@csrf_exempt
@require_http_methods(['GET'])
@require_admin
def node_authorization_requests(request):
    """授权申请列表（默认只看待审批）。

    查询参数：`?status=pending|approved|rejected|cancelled|all`、`?limit=`（默认 200，上限 500）。
    """
    queryset = NodeAuthorizationRequest.objects.select_related('requester', 'target')

    status = (request.GET.get('status') or 'pending').strip()
    if status != 'all':
        queryset = queryset.filter(status=status)

    try:
        limit = min(int(request.GET.get('limit') or 200), 500)
    except (TypeError, ValueError):
        limit = 200

    # 待审批排前面（审批人先看要动手的），其余按时间倒序。
    items = [_request_admin_payload(row) for row in queryset.order_by('-create_datetime')[:limit]]
    items.sort(key=lambda r: (r['status'] != 'pending', r['createdAt'] or ''), reverse=False)
    pending = NodeAuthorizationRequest.objects.filter(status='pending').count()
    return _ok({'items': items, 'total': len(items), 'pendingTotal': pending})


@csrf_exempt
@require_http_methods(['POST'])
@require_admin
def decide_node_authorization_request(request, pk):
    """批准 / 驳回一条授权申请。

    请求体：`{"decision": "approve"|"reject", "remark": "...", "bidirectional": true}`

    * `approve` —— 写授权行（默认双向）+ 申请单转 `approved` + 链上存证；
    * `reject`  —— 只转状态，**零权限副作用**（响应里 `granted` 是空的，可断言）；
    * 重复处置 —— 幂等，回 `alreadyDecided=true`，**不重复上链**。

    ⚠️ 上链在事务**提交之后**：存证失败不该回滚一次已经成立的批准。
       拿不到哈希时 `chainHash` 为空串并附 `chainWarning`，**不混成一句成功**。
    """
    from .node_authorization_service import AuthorizationRequestError, decide_request

    try:
        payload = json.loads(request.body or b'{}')
    except (ValueError, TypeError):
        return _error('请求体不是合法 JSON')
    if not isinstance(payload, dict):
        return _error('请求体应为 JSON 对象')

    decision = str(payload.get('decision') or '').strip().lower()
    # `bidirectional` 默认 true：申请表达的是"两个节点互通"。显式传 false 才单授。
    bidirectional = payload.get('bidirectional')
    bidirectional = True if bidirectional is None else bool(bidirectional)

    identity = getattr(request, 'kms_identity', {})
    try:
        result = decide_request(
            pk, decision=decision, identity=identity,
            remark=payload.get('remark') or '', bidirectional=bidirectional,
        )
    except AuthorizationRequestError as exc:
        # 业务码 → HTTP 状态用**冻结契约**里的那一张表（`api_contract.ERROR_HTTP_STATUS`），
        # 不在本模块另写一份映射 —— 两份必然漂移，而漂移的表现是同一个错误
        # 在不同接口上给出不同的状态码。
        from . import api_contract as C
        return _error(exc.message, C.ERROR_HTTP_STATUS.get(exc.code, 400))

    row = result['request']

    chain_tx = ''
    if result['decided'] and result['chain_payload']:
        p = result['chain_payload']
        chain_tx = record_chain_event(
            p['event_type'], p['key_id'], 0, p['node_id'], p['material_hash'],
        ) or ''
        if chain_tx:
            NodeAuthorizationRequest.objects.filter(pk=row.pk).update(chain_tx=chain_tx)
        else:
            logger.warning('授权申请 #%s 的 %s 存证未成功（链不可用或未配置）',
                           row.pk, p['event_type'])

    data = {
        'request': _request_admin_payload(
            NodeAuthorizationRequest.objects.select_related('requester', 'target').get(pk=row.pk)
        ),
        'decided': result['decided'],
        'alreadyDecided': result['alreadyDecided'],
        # 如实区分"新建"与"重新激活"：两个方向可能一个早就存在、另一个才新建，
        # "都是 200"会把"这次到底改变了什么"抹掉。
        'granted': result['granted'],
        'chainHash': chain_tx,
    }
    if result['decided'] and not chain_tx:
        data['chainWarning'] = '已放行，但链上存证未成功（链不可用或未配置）'

    if result['alreadyDecided']:
        return _ok(data, msg=f'该申请已是「{row.get_status_display()}」，未重复处置')
    return _ok(
        data,
        msg=('已批准：' + ('、'.join(result['granted']['created'] + result['granted']['reactivated'])
                           or '授权此前已存在'))
        if decision == 'approve' else '已驳回（未授予任何权限）',
    )