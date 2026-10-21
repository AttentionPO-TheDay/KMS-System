"""Authenticated, fixed algorithm checks; accepts no key material or executable input."""
import json
import threading

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .acceptance_pq import CASES, run_checks
from .user_distribution_views import require_kms_user

_running = threading.Lock()


def _response(data, status=200):
    response = JsonResponse(data, status=status)
    response['Cache-Control'] = 'no-store, private, max-age=0'
    response['Pragma'] = 'no-cache'
    response['Vary'] = 'Authorization, Cookie'
    return response


@csrf_exempt
@require_http_methods(['POST'])
@require_kms_user
def node_self_acceptance_pq(request, identity):
    try:
        if len(request.body) > 256:
            raise ValueError()
        payload = json.loads(request.body)
        if not isinstance(payload, dict) or set(payload) != {'caseId'} or payload['caseId'] not in CASES:
            raise ValueError()
    except (ValueError, TypeError):
        return _response({'code': 400, 'msg': '仅接受固定算法测试 caseId，不接受密钥或参数覆盖'}, 400)
    if not _running.acquire(blocking=False):
        return _response({'code': 429, 'msg': '算法测试正在执行，请稍后重试'}, 429)
    try:
        evidence = run_checks(payload['caseId'])
        return _response({'code': 200, 'data': evidence})
    except Exception:
        # Never echo exception strings, local values or native buffers.
        return _response({'code': 503, 'msg': '算法测试执行异常，未取得完整证据'}, 503)
    finally:
        _running.release()
