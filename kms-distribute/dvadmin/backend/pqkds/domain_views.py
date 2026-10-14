"""Independent logical domain registry. Empty domains persist; no deletion API."""
import json

from django.db import IntegrityError, transaction
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from .models import Domain
from .user_distribution_views import require_kms_user


@csrf_exempt
@require_http_methods(['GET', 'POST'])
@require_kms_user
def domains(request, identity):
    try:
        admin = identity.get('principalType') in (None, 'ADMIN') and int(identity.get('roleLevel')) <= 0
    except (TypeError, ValueError):
        admin = False
    if not admin:
        return JsonResponse({'code': 403, 'message': '域管理仅管理员可访问'}, status=403)
    if request.method == 'GET':
        return JsonResponse({'code': 200, 'data': list(Domain.objects.values('domain_id', 'name', 'description'))})
    try:
        payload = json.loads(request.body)
        if not isinstance(payload, dict):
            raise ValueError('请求须为 JSON 对象')
        domain_id = payload.get('domain_id', '')
        name = payload.get('name', '')
        description = payload.get('description', '')
        if not all(isinstance(value, str) for value in (domain_id, name, description)):
            raise ValueError('域标识、名称和说明须为文本')
        domain_id, name, description = domain_id.strip(), name.strip(), description.strip()
        if not domain_id or len(domain_id) > 64 or not name or len(name) > 100 or len(description) > 500:
            raise ValueError('域标识须为 1 至 64 字符，名称须为 1 至 100 字符，说明最多 500 字符')
        with transaction.atomic():
            Domain.objects.create(domain_id=domain_id, name=name, description=description)
    except IntegrityError:
        return JsonResponse({'code': 409, 'message': '该域标识已存在'}, status=409)
    except (ValueError, UnicodeDecodeError) as exc:
        return JsonResponse({'code': 400, 'message': str(exc)}, status=400)
    return JsonResponse({'code': 200, 'data': {'domain_id': domain_id, 'name': name, 'description': description}}, status=201)
