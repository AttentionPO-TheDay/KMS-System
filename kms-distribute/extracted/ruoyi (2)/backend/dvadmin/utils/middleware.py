import json
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
        self.operation_log_id = None
    @classmethod
    def __handle_request(cls, request):
        request.request_ip = get_request_ip(request)
        request.request_data = get_request_data(request)
        request.request_path = get_request_path(request)
    def __handle_response(self, request, response):
        body = getattr(request, 'request_data', {})
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
            'request_msg': request.session.get('request_msg'),
            'status': True if response.data.get('code') in [2000, ] else False,
            'json_result': {"code": response.data.get('code'), "msg": response.data.get('msg')},
        }

        # 处理数据库连接问题
        from django.db import connection
        try:
            operation_log, creat = OperationLog.objects.update_or_create(defaults=info, id=self.operation_log_id)
        except Exception as e:
            if 'Server has gone away' in str(e) or '2006' in str(e):
                # 连接断开，关闭并重新连接
                connection.close()
                try:
                    operation_log, creat = OperationLog.objects.update_or_create(defaults=info, id=self.operation_log_id)
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
                        self.operation_log_id = log.id
                    except Exception as e:
                        if 'Server has gone away' in str(e) or '2006' in str(e):
                            from django.db import connection
                            connection.close()
                            try:
                                log.save()
                                self.operation_log_id = log.id
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