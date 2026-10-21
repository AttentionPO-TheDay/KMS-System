"""Internal-only fixed anomaly fixture; never accepts business key/node IDs."""
import json
import logging
from django.db import transaction
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from .internal_pool_views import _internal_token_ok

logger = logging.getLogger(__name__)


@transaction.non_atomic_requests
@csrf_exempt
@require_http_methods(['POST'])
def internal_abnormal_revocation(request):
    if not _internal_token_ok(request):
        return JsonResponse(dict(code=403, msg='内部通道拒绝访问'), status=403)
    try:
        payload = json.loads(request.body or b'{}')
        if payload != {}:
            raise ValueError('只接受固定异常回收验收，不允许指定业务对象或执行参数')
    except (TypeError, ValueError) as error:
        return JsonResponse(dict(code=400, msg=str(error)), status=400)
    try:
        from .acceptance_revoke import run_abnormal_revocation
        return JsonResponse(dict(code=200, data=run_abnormal_revocation()))
    except Exception:
        logger.exception('Isolated abnormal revocation acceptance failed')
        return JsonResponse(dict(code=503, msg='异常回收验收执行失败，结果不可采信'), status=503)
