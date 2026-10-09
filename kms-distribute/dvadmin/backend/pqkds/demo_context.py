# -*- coding: utf-8 -*-
"""受控 Demo 的入口适配；业务主体仍由 Java 自省，不另造登录体系。

普通请求不读取 Demo Cookie。只有独立回环网关的内部边界标记才进入本模块；
角色参数、Host 名称及 Cookie 本身都不能替代这个边界。变更请求持有 Java 的
会话租约直到数据库提交，切回节点不能与尚未提交的管理员写入擦肩而过。
"""
from __future__ import annotations

import hmac
import json
import logging
import os
import re
import secrets

from django.db import connection
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django_redis import get_redis_connection

from . import kms_service_client as kms

logger = logging.getLogger(__name__)
COOKIE_NAME = 'KMS-Demo-Session'
NODE_ID_RE = re.compile(r'^[A-Za-z0-9_.-]{1,64}$')
SAFE_METHODS = {'GET', 'HEAD', 'OPTIONS'}


def enabled():
    return os.getenv('KMS_DEMO_ENABLED', 'false').lower() == 'true'


def _configured(name, default):
    return {v.strip() for v in os.getenv(name, default).split(',') if v.strip()}


def _error(message, status=403, code='DEMO_FORBIDDEN'):
    return JsonResponse({'code': status, 'msg': message,
                         'data': {'error_code': code}}, status=status)


def internal_authorized(request):
    configured = os.getenv('INTERNAL_TOKEN', '')
    supplied = request.META.get('HTTP_X_INTERNAL_TOKEN', '')
    return bool(configured and supplied and hmac.compare_digest(configured, supplied))


def trusted_demo_request(request):
    configured = os.getenv('INTERNAL_TOKEN', '')
    supplied = request.META.get('HTTP_X_KMS_DEMO_GATEWAY', '')
    return (enabled() and request.META.get('HTTP_X_KMS_ENTRY_MODE') == 'demo'
            and bool(configured and supplied)
            and hmac.compare_digest(configured, supplied)
            and request.get_host() in _configured(
                'KMS_DEMO_ALLOWED_HOSTS', '127.0.0.1:8088,localhost:8088'))


def demo_rpc(action, payload):
    """服务间调用只传会话标识/版本，不向浏览器交内部令牌。"""
    try:
        response = kms.requests.post(
            f'{kms.KMS_LIFECYCLE_BASE}/internal/lifecycle/demo/{action}',
            headers=kms._internal_headers(), json=payload, timeout=kms.DEFAULT_TIMEOUT,
        )
        if response.status_code != 200:
            raise kms.KmsServiceError('Demo 身份服务调用失败')
        data = (response.json() or {}).get('data') or {}
    except (kms.requests.RequestException, ValueError) as exc:
        raise kms.KmsServiceError('Demo 身份服务暂时不可用') from exc
    if not data.get('ok'):
        raise kms.KmsTokenInvalid(data.get('errorMessage') or 'Demo 会话无效或上下文已切换')
    return data


def _demo_identity(request, *, mutation):
    session_id = request.COOKIES.get(COOKIE_NAME, '')
    revision = request.META.get('HTTP_X_KMS_DEMO_REVISION', '')
    if not session_id or len(session_id) > 256:
        raise kms.KmsTokenInvalid('缺少 Demo 会话')
    if not str(revision).isdigit():
        raise kms.KmsTokenInvalid('缺少 Demo 上下文版本，请刷新入口')
    payload = {'sessionId': session_id, 'revision': int(revision)}
    if mutation:
        origins = _configured('KMS_DEMO_ALLOWED_ORIGINS',
                              'http://127.0.0.1:8088,http://localhost:8088')
        if request.META.get('HTTP_ORIGIN', '') not in origins:
            raise kms.KmsTokenInvalid('Demo 变更请求来源不受信任')
        csrf = request.META.get('HTTP_X_KMS_DEMO_CSRF', '')
        if not csrf:
            raise kms.KmsTokenInvalid('缺少 Demo CSRF 凭据')
        payload['csrfToken'] = csrf
        data = demo_rpc('lease/acquire', payload)
        request.demo_lease_id = data.get('leaseId')
        if not request.demo_lease_id:
            raise kms.KmsServiceError('Demo 变更租约未建立')
        identity = data.get('identity') or {}
    else:
        data = demo_rpc('introspect', payload)
        identity = data.get('identity') or data
    if identity.get('entryMode') != 'DEMO' or identity.get('userId') is None:
        raise kms.KmsTokenInvalid('Demo 身份信息不完整')
    request.demo_session_id = session_id
    return identity


def _check_scope(request, identity):
    """本演示不是把仓库所有历史匿名端点开放成管理员 API。"""
    path = request.path
    root = '/api/pqkds/'
    if not path.startswith(root):
        return _error('该端点不属于演示业务')
    relative = path[len(root):]
    principal = identity.get('principalType')
    if principal == 'NODE':
        denied_auth = ('node-self/activate/', 'node-self/challenge/', 'node-self/login/',
                       'node-self/still-exists/')
        if relative.startswith(denied_auth):
            return _error('Demo 不使用激活或设备登录')
        if not relative.startswith(('node-self/', 'user-nodes/', 'distribution-batches/',
                                    'user-symmetric-keys/', 'logs/', 'key-pool/')):
            return _error('演示节点不能访问管理接口')
        if relative.startswith('key-pool/') and request.method not in SAFE_METHODS:
            return _error('节点预分配和取用请走节点自助保护包流程')
        from .models import Node
        from .node_self_views import _public_status
        node = Node.objects.filter(sys_user_id=identity['userId']).first()
        if node is None or node.node_id != identity.get('nodeId'):
            return _error('演示节点映射已失效', 401, 'DEMO_NODE_MISSING')
        status = _public_status(node)
        if status == 'DISABLED':
            return _error('该节点已停用', 403, 'DEMO_NODE_DISABLED')
        if status == 'PENDING_INIT' and relative not in {
                'node-self/', 'node-self/keys/', 'node-self/init/',
                'node-self/demo-init/lease/', 'node-self/demo-init/release/',
                'node-self/keygen/issuances/', 'node-self/keygen/authorizations/'}:
            return _error('请先完成四套基础密钥初始化', 409, 'DEMO_INIT_REQUIRED')
    elif principal == 'ADMIN':
        if identity.get('nodeId'):
            return _error('管理员不能携带节点身份')
        if not relative.startswith(('admin/', 'nodes/', 'logs/', 'stats/', 'key-pool/',
                                    'session-keys/', 'blocks/', 'transactions/',
                                    'security/', 'system-parameters/', 'blockchain-config/')):
            return _error('该端点不属于演示管理员能力')
        forbidden = ('reissue_activation_code', 'generate_falcon', 'generate_gm',
                     'update_keys', 'cleanup_blockchain_data', 'discover_node',
                     'prepare_key_negotiation')
        if any(part in relative for part in forbidden):
            return _error('Demo 不签发激活凭证或代替节点生成密钥')
        if relative.startswith(('blocks/', 'transactions/', 'system-parameters/',
                                'blockchain-config/', 'session-keys/')) and request.method not in SAFE_METHODS:
            return _error('该监管接口在 Demo 中只读')
    else:
        return _error('请从演示入口建立上下文', 401, 'DEMO_CONTEXT_REQUIRED')
    return None


class DemoContextMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.META.get('HTTP_X_KMS_ENTRY_MODE') != 'demo':
            return self.get_response(request)
        if not trusted_demo_request(request):
            return _error('演示入口未启用或请求越过受控边界', 404, 'DEMO_DISABLED')
        mutation = request.method not in SAFE_METHODS
        session_id = request.COOKIES.get(COOKIE_NAME, '')
        try:
            identity = _demo_identity(request, mutation=mutation)
            request.kms_identity = identity
            error = _check_scope(request, identity)
            if error is not None:
                return error
            if not mutation:
                return self.get_response(request)
            # 与角色切换使用同一租约，全部业务写入/提交结束后才释放。
            # ⚠️ 不能包一个新的外层 atomic：原服务在自己的事务提交后才上链，
            # 加外层事务会把那条规则反转成“链有记录、数据库尚未提交”。
            def fence(execute, sql, params, many, context):
                statement = str(sql).lstrip().upper()
                if statement.startswith(('INSERT', 'UPDATE', 'DELETE', 'REPLACE', 'COMMIT')):
                    demo_rpc('lease/validate', {'sessionId': session_id,
                                              'leaseId': request.demo_lease_id})
                return execute(sql, params, many, context)

            with connection.execute_wrapper(fence):
                response = self.get_response(request)
                demo_rpc('lease/validate', {'sessionId': session_id,
                                          'leaseId': request.demo_lease_id})
                return response
        except kms.KmsTokenInvalid as exc:
            return _error(str(exc), 409 if mutation else 401, 'DEMO_CONTEXT_STALE')
        except kms.KmsServiceError as exc:
            logger.warning('Demo 请求身份服务失败: %s', exc)
            return _error('演示身份服务暂时不可用', 503, 'DEMO_SERVICE_UNAVAILABLE')
        finally:
            lease_id = getattr(request, 'demo_lease_id', None)
            if lease_id:
                try:
                    demo_rpc('lease/release', {'sessionId': session_id, 'leaseId': lease_id})
                except (kms.KmsServiceError, kms.KmsTokenInvalid):
                    logger.warning('Demo 会话租约释放失败，将由服务端过期回收')


@require_http_methods(['GET'])
def internal_node_context(request):
    if not enabled() or not internal_authorized(request):
        return _error('内部通道拒绝访问', 403)
    node_id = request.GET.get('nodeId', '')
    if not NODE_ID_RE.fullmatch(node_id):
        return _error('nodeId 格式不合法', 400, 'DEMO_NODE_INVALID')
    from .models import Node
    from .node_self_views import _node_payload
    node = Node.objects.filter(node_id=node_id).first()
    # MySQL 默认排序规则忽略大小写；平台的业务 ID 必须逐字相同，不能
    # 用 node-a 的链接静默选择 Node-A（本地 keyRef 也按精确 ID 区分）。
    if node is None or node.node_id != node_id:
        return _error('节点未登记', 404, 'DEMO_NODE_NOT_REGISTERED')
    if not node.sys_user_id:
        return _error('节点未关联业务账号', 409, 'DEMO_NODE_UNMAPPED')
    data = _node_payload(node)
    data['userId'] = node.sys_user_id
    return JsonResponse({'code': 200, 'data': data})


def _init_key(node_id):
    return 'kms_demo_init:' + node_id


def validate_init_lease(request, node_id):
    from django_redis import get_redis_connection
    supplied = request.META.get('HTTP_X_KMS_DEMO_INIT_LEASE', '')
    redis = get_redis_connection('default')
    raw = redis.get(_init_key(node_id))
    if not supplied or not raw:
        return False
    payload = json.loads(raw)
    if (not hmac.compare_digest(payload['leaseId'], supplied)
            or payload['sessionId'] != request.demo_session_id):
        return False
    # 比较与续期必须同一条原子操作，不能给已过期、被另一会话取得的租约续命。
    return bool(redis.eval("if redis.call('get',KEYS[1]) == ARGV[1] then "
                           "return redis.call('expire',KEYS[1],600) end return 0",
                           1, _init_key(node_id), raw))


@csrf_exempt
@require_http_methods(['POST'])
def demo_init_lease(request):
    identity = getattr(request, 'kms_identity', {})
    if not trusted_demo_request(request) or identity.get('principalType') != 'NODE':
        return _error('需要演示节点上下文')
    node_id = identity['nodeId']
    key = _init_key(node_id)
    redis = get_redis_connection('default')
    raw = redis.get(key)
    if raw:
        payload = json.loads(raw)
        if payload['sessionId'] != request.demo_session_id:
            return _error('另一演示会话正在初始化该节点，请稍后重试', 409, 'DEMO_INIT_BUSY')
    else:
        payload = {'leaseId': secrets.token_urlsafe(32), 'sessionId': request.demo_session_id}
        if not redis.set(key, json.dumps(payload), nx=True, ex=600):
            return _error('该节点正在初始化，请稍后重试', 409, 'DEMO_INIT_BUSY')
    return JsonResponse({'code': 200, 'data': {'leaseId': payload['leaseId']}})


@csrf_exempt
@require_http_methods(['POST'])
def demo_init_release(request):
    identity = getattr(request, 'kms_identity', {})
    if not trusted_demo_request(request) or identity.get('principalType') != 'NODE':
        return _error('需要演示节点上下文')
    try:
        payload = json.loads(request.body or b'{}')
    except ValueError:
        return _error('请求体不是合法 JSON', 400)
    key = _init_key(identity['nodeId'])
    redis = get_redis_connection('default')
    raw = redis.get(key)
    if raw:
        stored = json.loads(raw)
        if (stored['sessionId'] == request.demo_session_id
                and hmac.compare_digest(stored['leaseId'], str(payload.get('leaseId', '')))):
            redis.eval("if redis.call('get',KEYS[1]) == ARGV[1] then "
                       "return redis.call('del',KEYS[1]) end return 0", 1, key, raw)
    return JsonResponse({'code': 200, 'data': {'released': True}})
