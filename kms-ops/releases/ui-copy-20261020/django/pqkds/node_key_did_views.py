import json
import re

from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .user_distribution_views import require_kms_user
from .models import NodeKeyDidRecord, NodeLongTermKey
from . import node_key_did as service


@csrf_exempt
@require_http_methods(['GET', 'POST'])
@require_kms_user
def node_self_key_did(request, identity):
    from .node_self_views import _find_node, _ok, _error, _public_status
    node = _find_node(identity)
    if node is None:
        return _error('当前账号未关联节点', 403)
    if not service.enabled():
        return _error('当前服务器尚未启用本页面的 DID 上链', 503, error_code='NODE_KEYGEN_DID_DISABLED')
    if request.method == 'GET':
        sys_pid = request.GET.get('sysPid', '')
        if not re.fullmatch('[0-9a-f]{182}', sys_pid):
            return _error('请输入完整 SysPid')
        record = NodeKeyDidRecord.objects.filter(key__node=node, sys_pid=sys_pid).first()
        if record is None:
            return _error('未找到本节点对应的 SysPid 记录', 404)
        result = service.process(record)  # Query NEVER prepares or submits.
    else:
        if _public_status(node) == 'DISABLED':
            return _error('该节点已停用，不能提交上链', 403)
        try:
            body = json.loads(request.body or b'{}')
        except (ValueError, TypeError):
            return _error('请求体不是合法 JSON')
        if (not isinstance(body, dict) or set(body) != {'algorithm', 'keyId', 'keyVersion'}
                or type(body['keyVersion']) is not int or body['keyVersion'] < 1
                or not isinstance(body['algorithm'], str) or not isinstance(body['keyId'], str)):
            return _error('继续上链只接受本节点的 algorithm、keyId、keyVersion')
        key = NodeLongTermKey.objects.filter(
            node=node, algorithm=body['algorithm'], key_id=body['keyId'], key_version=body['keyVersion']).first()
        if key is None:
            return _error('未找到本节点对应的密钥记录', 404)
        result = service.register(key)
    return _ok(result, msg='DID 已确认' if result['status'] == 'CONFIRMED' else 'DID 状态已更新，请查看核验结果')
