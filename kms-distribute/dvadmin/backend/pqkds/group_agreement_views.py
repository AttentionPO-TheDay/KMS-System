import json
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from .user_distribution_views import require_kms_user
from . import group_agreement_service as service


def _reply(operation):
    try:
        return JsonResponse({'code': 200, 'msg': '操作完成', 'data': operation()})
    except service.AgreementError as exc:
        return JsonResponse({'code': exc.code, 'msg': str(exc), 'data': {'error_code': 'GROUP_AGREEMENT_REJECTED'}})


def _body(request, allowed):
    if len(request.body) > 16384:
        raise service.AgreementError('请求体过大')
    try:
        payload = json.loads(request.body or b'{}')
    except (ValueError, TypeError) as exc:
        raise service.AgreementError('请求体不是合法JSON') from exc
    if not isinstance(payload, dict) or set(payload) - set(allowed):
        raise service.AgreementError('请求字段不合法，不允许上传密钥或贡献明文')
    return payload


@csrf_exempt
@require_http_methods(['GET', 'POST'])
@require_kms_user
def agreements(request, identity):
    def run():
        node = service.actor(identity)
        if request.method == 'POST':
            return service.create(node, _body(request, ['participantNodeIds']))
        return {'selfNodeId': node.node_id, 'peers': service.peers(node), 'items': service.listing(node)}
    return _reply(run)


@csrf_exempt
@require_http_methods(['GET', 'POST'])
@require_kms_user
def agreement(request, agreement_id, identity):
    def run():
        node = service.actor(identity)
        if request.method == 'GET':
            return service.detail(agreement_id, node)
        payload = _body(request, ['action', 'commitment', 'packets', 'proof', 'transcriptHash'])
        action = payload.pop('action', None)
        fields = {'commit': {'commitment'}, 'exchange': {'packets'},
                  'confirm': {'proof', 'transcriptHash'}, 'close': set()}
        if not isinstance(action, str) or action not in fields or set(payload) != fields[action]:
            raise service.AgreementError('操作字段不合法')
        return service.operate(agreement_id, node, action, payload)
    return _reply(run)
