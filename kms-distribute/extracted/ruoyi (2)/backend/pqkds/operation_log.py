"""
PQKDS 操作日志工具
为每个API操作设置可读的操作说明，供 ApiLoggingMiddleware 记录到 OperationLog.request_msg
"""
import logging

logger = logging.getLogger(__name__)


def set_request_msg(request, msg: str):
    """设置请求的操作说明，供中间件写入操作日志"""
    if not hasattr(request, 'session') or request.session is None:
        # DRF APIRequestFactory 等测试场景下可能没有 session
        return
    try:
        request.session['request_msg'] = msg
    except Exception:
        pass
