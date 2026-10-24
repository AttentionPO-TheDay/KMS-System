import json
import logging

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from . import external_sscl as service

logger = logging.getLogger(__name__)


@csrf_exempt
@require_http_methods(['GET', 'POST'])
def external_node_activation(request):
    """Bearer service authentication; no Cookie, browser role, revision or CSRF handshake."""
    try:
        clients, cipher = service.configuration()
        client = service.authenticate(request, clients)
        if request.method == 'POST':
            if request.content_type != 'application/json' or len(request.body) > 2048:
                raise service.ActivationError('INVALID_ACTIVATION_REQUEST', 400)
            try:
                body = json.loads(request.body)
            except (ValueError, UnicodeError):
                raise service.ActivationError('INVALID_ACTIVATION_REQUEST', 400) from None
            if not isinstance(body, dict) or type(body.get('includePrivateKey', False)) is not bool:
                raise service.ActivationError('INVALID_ACTIVATION_REQUEST', 400)
            fields = set(body) - {'includePrivateKey', 'algorithm'}
            include_private = body.get('includePrivateKey', False)
            algorithm = service.validate_algorithm(body['algorithm']) if 'algorithm' in body else None
            if fields == {'nodeName'}:
                algorithm = algorithm or 'SM2'
                data, status = service.activate(client, body['nodeName'], cipher, algorithm=algorithm)
                if include_private and status in (200, 202) and data['publicKeyRegistrationStatus'] == 'REGISTERED':
                    data.update(service.private_key(client, cipher, name=body['nodeName'], algorithm=algorithm))
            elif fields == {'sysPid'} and include_private:
                material = service.private_key(client, cipher, sys_pid=body['sysPid'], algorithm=algorithm)
                data, status = service.query(client, sys_pid=body['sysPid'], algorithm=algorithm), 200
                data.update(material)
            else:
                raise service.ActivationError('INVALID_ACTIVATION_REQUEST', 400)
        else:
            fields = set(request.GET)
            if fields not in ({'nodeName'}, {'sysPid'}, {'nodeName', 'algorithm'}, {'sysPid', 'algorithm'}):
                raise service.ActivationError('INVALID_ACTIVATION_REQUEST', 400)
            field = 'sysPid' if 'sysPid' in fields else 'nodeName'
            if any(len(request.GET.getlist(name)) != 1 for name in fields):
                raise service.ActivationError('INVALID_ACTIVATION_REQUEST', 400)
            selector = {'sys_pid': request.GET[field]} if field == 'sysPid' else {'name': request.GET[field]}
            if 'algorithm' in fields:
                selector['algorithm'] = service.validate_algorithm(request.GET['algorithm'])
            data, status = service.query(client, **selector), 200
        response = JsonResponse({'code': status, 'msg': '公钥已登记' if data['publicKeyRegistrationStatus'] == 'REGISTERED' else '节点正在初始化', 'data': data}, status=status)
    except service.ActivationError as exc:
        response = JsonResponse({'code': exc.status, 'msg': exc.code, 'data': {'errorCode': exc.code}}, status=exc.status)
    except Exception:
        # Do not expose SQL, private material, credentials or upstream response bodies.
        logger.error('External SSCL activation failed')
        response = JsonResponse({'code': 500, 'msg': 'EXTERNAL_ACTIVATION_FAILED', 'data': {'errorCode': 'EXTERNAL_ACTIVATION_FAILED'}}, status=500)
    response['Cache-Control'] = 'no-store'
    return response
