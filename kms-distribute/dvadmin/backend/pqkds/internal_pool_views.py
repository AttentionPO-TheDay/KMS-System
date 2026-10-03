# -*- coding: utf-8 -*-
"""阶段 6（文档 §7.6）：长期密钥回收后，连带失效依赖它的预分配池项。

    POST /internal/pool/revoke-by-key/

调用方：主 KMS（Java）在回收/轮换长期密钥后调用，把仍为 READY/RESERVED 的
相关池项置为 REVOKED。

为什么必须做这件事
----------------
池项里的密文是用**某个长期公钥**封的。那把长期密钥一旦被回收，
对应池项就再也解不开了 —— 但它仍会显示为 READY，等着某次会话去取，
然后在解密时才失败。让这种「注定失败」的条目留在可用集合里，
既浪费一次会话，也会把确定性故障伪装成偶发问题。

鉴权
----
沿用本仓库既有的内部通道约定：`X-Internal-Token` 头 + 与 Go↔Java
同一把、由 compose 注入的令牌（见 kms_service_client 与
InternalLifecycleController 的说明）。**不对外开放**，网关不为其配置路由。
"""

from __future__ import annotations

import logging

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .key_pool_service import KeyPoolService

logger = logging.getLogger(__name__)


def _internal_token_ok(request) -> bool:
    """校验内部令牌。

    Token 从环境变量读（compose 注入），**没有硬编码默认值** ——
    留默认值等于给所有部署发同一把公开钥匙。
    """
    import os

    expected = (os.environ.get('INTERNAL_TOKEN') or '').strip()
    if not expected:
        logger.error('INTERNAL_TOKEN 未配置，拒绝所有内部调用')
        return False
    provided = (request.headers.get('X-Internal-Token') or '').strip()
    # 定长比较，避免按字符提前返回带来的时序侧信道
    import hmac
    return hmac.compare_digest(provided, expected)


@csrf_exempt
@require_http_methods(['POST'])
def revoke_pool_by_key(request):
    """把依赖某节点长期密钥的可用池项置为 REVOKED。

    请求体：
        `{"node_id": "NODE-A", "key_id": 12, "version": 3, "algorithm": "KYBER"}`

    * `key_id` + `version` 用于**精确匹配**创建时回填的长期密钥引用
      （KMS-007 D3）。此前这两项只出现在日志文案里，实际匹配只看 `node_id` ——
      撤一把密钥会把该节点全部可用池项清空，日志却印得像是精确失效的。
    * `algorithm`（**规范名**，如 `KYBER` / `FALCON`，可选但**强烈建议传**）
      把"没有长期密钥引用"的历史行（迁移 0017 之前创建）的退化匹配收窄到
      该算法的拼写家族。**不传时退化面是该节点全部算法的历史行** ——
      那是本端点的旧行为，会误伤其它算法；调用方若拿不出算法名，
      请把这一点当作已知的粗粒度失效对待（日志里会点名说明）。

    响应：  `{"code": 200, "data": {"revoked": <条数>}}`
    """
    if not _internal_token_ok(request):
        return JsonResponse({'code': 401, 'msg': '内部令牌无效'}, status=401)

    import json

    try:
        payload = json.loads(request.body or b'{}')
    except (ValueError, TypeError):
        return JsonResponse({'code': 400, 'msg': '请求体不是合法 JSON'}, status=400)

    node_id = (payload.get('node_id') or '').strip()
    if not node_id:
        return JsonResponse({'code': 400, 'msg': '缺少 node_id'}, status=400)

    try:
        n = KeyPoolService.revoke_pool_items_for_key(
            node_id,
            payload.get('key_id'),
            payload.get('version'),
            # 规范名（'KYBER' / 'FALCON'…）。传 None 时退化面落到该节点全部
            # 算法（见 docstring）—— 这里不替调用方猜一个算法名，
            # 猜错的方向是"清掉另一算法的历史池项"，且不报错。
            algorithm=payload.get('algorithm'),
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception('连带失效池项失败: node=%s', node_id)
        return JsonResponse({'code': 500, 'msg': f'失效失败：{exc}'}, status=500)

    return JsonResponse({'code': 200, 'msg': 'OK', 'data': {'revoked': n}})
