import json
import re
import uuid


def _keygen_audit_payload(path, data):
    """Separate safe audit DTO; never retain rejected secrets or malformed bodies.

    Only this narrow public-key/issuance surface changes. Requests passed to the
    view retain their original body; audit records use a validated public whitelist.
    """
    if '/node-self/keygen/' not in path and not path.rstrip('/').endswith('/node-self/keys'):
        return data
    if not isinstance(data, dict):
        return {'redacted': True}
    safe = {}
    for name in ('algorithm', 'securityLevel', 'security_level', 'variant'):
        value = data.get(name)
        choices = {'algorithm': {'KYBER', 'FALCON', 'SM2', 'SSCL'},
                   'securityLevel': {'512', '768', '1024', 'sm2p256v1'},
                   'security_level': {'512', '768', '1024', 'sm2p256v1'},
                   'variant': {'512', '768', '1024'}}[name]
        if isinstance(value, (str, int)) and not isinstance(value, bool) and str(value) in choices:
            safe[name] = value
    for name in ('keyId', 'key_id'):
        value = data.get(name)
        if isinstance(value, str) and re.fullmatch(r'[A-Za-z0-9_.-]{1,64}', value):
            safe[name] = value
    for name in ('keyVersion', 'key_version'):
        value = data.get(name)
        if type(value) is int and 1 <= value <= 4294967295:
            safe[name] = value
        elif isinstance(value, str) and re.fullmatch(r'[1-9][0-9]{0,9}', value):
            safe[name] = value
    for name in ('deviceId', 'device_id'):
        value = data.get(name)
        if isinstance(value, str) and re.fullmatch(r'[0-9a-f]{32}', value):
            safe[name] = value
    if type(data.get('rotate')) is bool:
        safe['rotate'] = data['rotate']
    # Public material need not be copied into operation logs; registry owns it.
    if 'publicKey' in data or 'public_key' in data or data.get('publicKeyPresent') is True:
        safe['publicKeyPresent'] = True
    def public_reference(name, value, target):
        try:
            if isinstance(value, str) and str(uuid.UUID(value)) == value:
                target[name] = value
        except (ValueError, AttributeError):
            pass
    for name in ('generationIssuanceId', 'abandonGenerationIssuanceId'):
        public_reference(name, data.get(name), safe)
    generation = data.get('generation')
    if isinstance(generation, dict):
        provenance = {}
        if generation.get('schemeId') in ('KMS_SPLIT_KEM_V1', 'KMS_SPLIT_SIGN_V1'):
            provenance['schemeId'] = generation['schemeId']
        if type(generation.get('schemeVersion')) is int and generation['schemeVersion'] == 1:
            provenance['schemeVersion'] = 1
        for name in ('generationIssuanceId', 'authorizationTicketId'):
            public_reference(name, generation.get(name), provenance)
        safe['generation'] = provenance
    safe['redacted'] = True
    return safe

from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from django.utils.deprecation import MiddlewareMixin
from dvadmin.system.models import OperationLog
from dvadmin.utils.request_util import get_request_user, get_request_ip, get_request_data, get_request_path, get_os, \
    get_browser, get_verbose_name
class ApiLoggingMiddleware(MiddlewareMixin):
    def __init__(self, get_response=None):
        super().__init__(get_response)
        self.enable = getattr(settings, 'API_LOG_ENABLE', None) or False
        self.methods = getattr(settings, 'API_LOG_METHODS', None) or set()
        # ⚠️ KMS-014 修：审计行 id 过去挂在**中间件实例**上（第 13 行原本是
        # `self.operation_log_id = None`）。中间件实例是**进程级**的（启动时
        # 实例化一次），于是这个 id 在请求之间残留：`process_view` 只对 DRF
        # ViewSet（有 `cls.queryset`）新建行，**函数视图**（如 `/node-self/*`
        # 的验签/确认/关闭）永远拿不到自己的 id，响应阶段就用
        # `update_or_create(id=<上一个 ViewSet 请求留下的 id>)` **覆盖别人的
        # 审计行**。实测表现（KMS-014 验收）：篡改被拒（ENVELOPE_TAMPERED）与
        # 越权确认（NOT_SESSION_PARTY）在那之前/之后的请求覆盖掉，审计表里
        # 查不到它们 —— 而"越权、篡改必须有拒绝和审计记录"正是阶段 6 的出口
        # 判据。改成把 id 放在 **request 上**：每个请求各归各行，函数视图
        # 响应阶段 `id=None` → 新建自己的行。
    @classmethod
    def __handle_request(cls, request):
        request.request_ip = get_request_ip(request)
        request.request_path = get_request_path(request)
        request.request_data = _keygen_audit_payload(request.request_path, get_request_data(request))
    def __handle_response(self, request, response):
        body = _keygen_audit_payload(request.path, getattr(request, 'request_data', {}))
        if isinstance(body, dict) and body.get('password', ''):
            body['password'] = '*' * len(body['password'])
        if not hasattr(response, 'data') or not isinstance(response.data, dict):
            response.data = {}
        try:
            if not response.data and response.content:
                content = json.loads(response.content.decode())
                response.data = content if isinstance(content, dict) else {}
        except Exception:
            return
        user = get_request_user(request)
        info = {
            'request_ip': getattr(request, 'request_ip', 'unknown'),
            'creator': user if not isinstance(user, AnonymousUser) else None,
            'dept_belong_id': getattr(request.user, 'dept_id', None),
            'request_method': request.method,
            'request_path': request.request_path,
            'request_body': body,
            'response_code': response.data.get('code'),
            'request_os': get_os(request),
            'request_browser': get_browser(request),
            'request_msg': (
                ('[DEMO:%s] ' % (getattr(request, 'kms_identity', {}).get('userName') or 'NODE'))
                + str(request.session.get('request_msg') or '')
                if getattr(request, 'kms_identity', {}).get('entryMode') == 'DEMO'
                else request.session.get('request_msg')
            ),
            'status': True if response.data.get('code') in [2000, ] else False,
            'json_result': {"code": response.data.get('code'), "msg": response.data.get('msg')},
        }

        if '/node-self/keygen/' in request.path or request.path.rstrip('/').endswith('/node-self/keys'):
            result = {'code': response.data.get('code'), 'msg': '公钥/生成发放请求已处理'}
            error = (response.data.get('data') or {}).get('error_code') if isinstance(response.data.get('data'), dict) else None
            if isinstance(error, str) and re.fullmatch(r'[A-Z_]{1,64}', error):
                result['error_code'] = error
            info['json_result'] = result

        # 处理数据库连接问题
        from django.db import connection
        # KMS-014：id 从 **request** 上取（见 `__init__` 的说明）——函数视图没有
        # 预建行，这里是 None，于是 update_or_create **新建**属于本请求的行，
        # 而不是覆盖上一个请求的审计记录。
        log_id = getattr(request, 'operation_log_id', None)
        try:
            operation_log, creat = OperationLog.objects.update_or_create(defaults=info, id=log_id)
        except Exception as e:
            if 'Server has gone away' in str(e) or '2006' in str(e):
                # 连接断开，关闭并重新连接
                connection.close()
                try:
                    operation_log, creat = OperationLog.objects.update_or_create(defaults=info, id=log_id)
                except Exception as retry_error:
                    # 重试失败，记录错误但不中断响应
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.error(f"操作日志保存失败: {retry_error}")
            else:
                raise

        if not operation_log.request_modular and settings.API_MODEL_MAP.get(request.request_path, None):
            operation_log.request_modular = settings.API_MODEL_MAP[request.request_path]
            try:
                operation_log.save()
            except Exception as e:
                if 'Server has gone away' in str(e) or '2006' in str(e):
                    connection.close()
                    try:
                        operation_log.save()
                    except Exception:
                        pass
        # 对于动态路径（如 /api/pqkds/nodes/320/update_keys/），尝试前缀匹配
        if not operation_log.request_modular:
            pqkds_module_map = {
                '/api/pqkds/nodes/': '节点管理',
                '/api/pqkds/session-keys/': '会话管理',
                '/api/pqkds/blockchain-config/': '区块链管理',
                '/api/pqkds/falcon-keypairs/': '密钥管理',
                '/api/pqkds/system-parameters/': '系统参数',
                '/api/pqkds/logs/': '日志管理',
                '/api/pqkds/stats/': '系统统计',
                '/api/pqkds/blocks/': '区块链管理',
                '/api/pqkds/transactions/': '区块链管理',
                '/api/pqkds/messages/': '消息管理',
                '/api/pqkds/node/': '密钥管理',
            }
            path = getattr(request, 'request_path', '')
            for prefix, modular in pqkds_module_map.items():
                if path.startswith(prefix):
                    operation_log.request_modular = modular
                    try:
                        operation_log.save()
                    except Exception:
                        pass
                    break
    def process_view(self, request, view_func, view_args, view_kwargs):
        if hasattr(view_func, 'cls') and hasattr(view_func.cls, 'queryset'):
            if self.enable:
                if self.methods == 'ALL' or request.method in self.methods:
                    log = OperationLog(request_modular=get_verbose_name(view_func.cls.queryset))
                    try:
                        log.save()
                        # KMS-014：挂到 **request** 上（不是 self 上 —— 见 __init__）。
                        request.operation_log_id = log.id
                    except Exception as e:
                        if 'Server has gone away' in str(e) or '2006' in str(e):
                            from django.db import connection
                            connection.close()
                            try:
                                log.save()
                                request.operation_log_id = log.id
                            except Exception:
                                pass
                        else:
                            raise
        return
    def process_request(self, request):
        self.__handle_request(request)
    def process_response(self, request, response):
        if self.enable:
            if self.methods == 'ALL' or request.method in self.methods:
                self.__handle_response(request, response)
        return response