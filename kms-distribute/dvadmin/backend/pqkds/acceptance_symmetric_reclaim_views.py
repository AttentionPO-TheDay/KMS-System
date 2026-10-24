"""Fixed internal acceptance task; no caller-supplied business objects."""
import json
import logging

from django.db import transaction
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from .internal_pool_views import _internal_token_ok

logger = logging.getLogger(__name__)


@transaction.non_atomic_requests
@csrf_exempt
@require_POST
def internal_symmetric_reclamation(request):
    if not _internal_token_ok(request):
        return JsonResponse(dict(code=403, msg='内部通道拒绝访问'), status=403)
    try:
        if json.loads(request.body or b'{}') != {}:
            raise ValueError('只接受固定对称密钥回收验收，不允许指定业务对象或参数')
    except (TypeError, ValueError) as error:
        return JsonResponse(dict(code=400, msg=str(error)), status=400)
    try:
        from .acceptance_symmetric_reclaim import run_symmetric_reclamation
        return JsonResponse(dict(code=200, data=run_symmetric_reclamation()))
    except Exception:
        logger.exception('Isolated symmetric reclamation acceptance failed')
        return JsonResponse(dict(code=503, msg='对称密钥回收验收执行失败，结果不可采信'), status=503)
