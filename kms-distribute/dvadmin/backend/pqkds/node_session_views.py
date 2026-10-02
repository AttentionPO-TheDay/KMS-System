# -*- coding: utf-8 -*-
"""节点侧的**取信封**与**会话确认**（文档 §6.5）。

    GET  /node-self/envelopes/                我可解封的节点腿信封
    POST /node-self/sessions/<sid>/confirm/   提交"我已恢复 K"的证明

这三件事为什么必须一起做
------------------------
§6.5 规定会话提升为 established 需要三条齐备：
    ① 接收方验签成功  ② 成功恢复 SM4 会话密钥  ③ 双方完成确认
其中 ② 此前**从未发生过** —— 服务端只封装、入库，然后就停在那里。
（`views.py` 里那几处 decaps 都在前端不调用的旧端点里。）

所以这里补的是 ② 与 ③：
  * `envelopes` 把节点自己那腿信封交给它，**服务端不再代解**；
  * `confirm` 收下节点算出的 `HMAC(K, session_id)`，由服务端比较双方是否一致。

为什么证明用 HMAC 而不是直接把 K 发上来
----------------------------------------
服务端**本来就没有 K** —— 那是本系统"服务端解不开"这条不变量。
若为了确认而要求节点上传 K，等于把这条不变量亲手拆掉：
从此数据库泄露就不再只是元数据泄露，而是全部会话密钥泄露。

改比 HMAC：双方各提交 `HMAC(K, session_id)`，服务端只比较两者是否相等。
相等即证明双方持有同一把 K，而服务端**始终没看到 K 本身**。

⚠️ 这也意味着 `key_recovered` 字段是节点的**声明**，服务端无法独立验证。
   真正起作用的是 proof 的相互匹配 —— 单方随便算一个值必然与对方对不上。
   这与"把没有签名当成签名有效"是同一类问题：不要在库里留下一个
   看起来被验证过、实际没人验证的字段而不加说明。
"""

from __future__ import annotations

import json
import logging

from django.db.models import Q
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .models import Node, PreDistributedKey, SessionKey, SessionKeyConfirmation
from .user_distribution_views import require_kms_user

logger = logging.getLogger(__name__)


def _ok(data=None, msg='操作成功'):
    return JsonResponse({'code': 200, 'msg': msg, 'data': data})


#: 与 `node_self_views` 保持**同一套**返回约定：HTTP 恒为 200，错误放在
#: 业务码里，字段名是 `msg`。
#:
#: ⚠️ 本仓库的 Django 侧有**两套**约定并存：
#:   * `node_self_views` / 本模块 —— `{'code','msg','data'}`，HTTP 200
#:   * `user_distribution_views` / `admin_node_authorization_views` ——
#:     `{'code','message','data'}`，HTTP 用真实状态码
#: 两者都对，但**同一个命名空间下必须只用一种**。
#: 混用（比如字段用 msg、状态码用真值）会让每个调用方都得写
#: `body?.msg || body?.message` 再加一层状态码判断 —— 而漏掉任何一处，
#: 表现都是"错误信息显示成 undefined"，很难追到是这里不统一。
#: 本模块挂在 `/node-self/` 下，所以随 `node_self_views`。
def _error(msg, code=400):
    return JsonResponse({'code': code, 'msg': msg, 'data': None}, status=200)


def _find_node(identity):
    return Node.objects.filter(sys_user_id=identity.get('userId')).first()


@csrf_exempt
@require_http_methods(['GET'])
@require_kms_user
def node_envelopes(request, identity):
    """返回**当前节点自己**那腿信封，供它在本地解封。

    ⚠️ 只返回 envelope 本体与定位信息，**不含任何私钥、也不含明文会话密钥**。
       解封所需的私钥在节点本地的 NodeKeyStore 里（§4.4），服务端没有。

    默认只给未过期的；`includeExpired=1` 才带历史 ——
    过期的信封仍具参考价值，但默认列出来会让界面噪音很大。
    """
    node = _find_node(identity)
    if node is None:
        return _error('当前账号未关联任何节点', 403)

    # 该节点作为**接收方**出现在 `node1` 列。
    # `wrap_for_node` 生成的节点腿信封落库时是 `node1=目标节点, node2=None`
    # （见 `user_distribution_views` 的写法）。这个约定只写在这一处 ——
    # 一旦写错，现象是"节点取不到自己的信封"，看不出是查错了列。
    queryset = (
        PreDistributedKey.objects
        .filter(recipient_type='node', node1=node)
        .order_by('-create_datetime')
    )
    if request.GET.get('includeExpired') not in ('1', 'true', 'True'):
        queryset = queryset.filter(expires_at__gt=timezone.now())

    limit = min(int(request.GET.get('limit') or 100), 500)
    items = []
    for record in queryset[:limit]:
        try:
            envelope = json.loads(record.encrypted_key_data or '{}')
        except (ValueError, TypeError):
            envelope = None
        items.append({
            'poolId': record.pool_id,
            'keyIndex': record.key_index,
            'wrappingAlgorithm': record.wrapping_algorithm or record.algorithm,
            'payloadAlgorithm': record.payload_algorithm,
            'keyHash': record.key_hash,
            'status': record.status,
            'expiresAt': record.expires_at.isoformat() if record.expires_at else None,
            'createdAt': record.create_datetime.isoformat() if record.create_datetime else None,
            # 信封本体：密文而已，只有节点本地那把私钥能解开
            'envelope': envelope,
        })
    return _ok({'items': items, 'total': len(items)})


@csrf_exempt
@require_http_methods(['GET'])
@require_kms_user
def node_sessions(request, identity):
    """当前节点**参与**的会话列表（文档 §10.10 会话管理）。

    为什么要有这个端点
    ------------------
    "让前端调 `/session-keys/` 再自己过滤"是**假的隔离**，而且会静默出错：
      * `/session-keys/` 是分发模块的 ViewSet，返回的是**全系统**会话；
        Node.node1/node2 是外键，序列化出来的是 `Node.name`；
      * 而前端手上只有 `Node.node_id`（业务编号）与 `Node.name`（显示名），
        这两列**不保证相同**。拿 nodeId 去比 name，要么永远不等（页面空白）、
        要么靠名称恰好相同撞对（一旦重名就串号）。
    两种失败都不抛异常，只安静地显示错的东西 —— 所以过滤必须放在服务端，
    判据必须是**外键主键**，不是名字。

    ⚠️ 这里返回的 `senderNode` / `recipientNode` 是**显示名**（node1.name），
       仅供界面展示；隔离已经由上面的 `filter(node1=node) | filter(node2=node)`
       做完了，前端**不需要**再按名字过滤一次。

    只返回元数据：不含 `encrypted_session_key` / `key_exchange_data`
    （密文属于会话双方，列表页没有理由下发）。
    """
    node = _find_node(identity)
    if node is None:
        return _error('当前账号未关联任何节点', 403)

    queryset = (
        SessionKey.objects
        .filter(Q(node1=node) | Q(node2=node))
        .select_related('node1', 'node2')
        .order_by('-create_datetime')
    )
    # 默认只给进行中的；`includeExpired=1` 才带已过期/已撤销的历史
    if request.GET.get('includeExpired') not in ('1', 'true', 'True'):
        queryset = queryset.exclude(status__in=('expired', 'revoked'))

    limit = min(int(request.GET.get('limit') or 200), 500)
    items = [
        {
            'sessionId': s.session_id,
            'senderNode': s.node1.name if s.node1_id else '',
            'recipientNode': s.node2.name if s.node2_id else '',
            'protectionAlgorithm': s.session_type,
            'status': s.status,
            'createdAt': s.create_datetime.isoformat() if s.create_datetime else None,
            'expiresAt': s.expires_at.isoformat() if s.expires_at else None,
            # node1 是会话发起节点（模型上的语义，见 models.py 的 help_text）。
            # 用 id 而非名字比较，与上面的过滤口径一致。
            'isSender': s.node1_id == node.id,
        }
        for s in queryset[:limit]
    ]
    return _ok({'items': items, 'total': len(items)})


@csrf_exempt
@require_http_methods(['POST'])
@require_kms_user
def node_session_confirm(request, session_id, identity):
    """提交"我已恢复会话密钥"的证明，双方一致则把会话提升为 established。

    请求体：`{"proof": "<HMAC-SHA256(K, session_id) 的十六进制>"}`

    流程：
      1. 校验该节点确实是这条会话的一方（否则第三个人也能来"确认"）；
      2. 记录（或更新）本节点的证明；
      3. 若双方证明**都已提交且相等** → 提升为 established。

    ⚠️ 证明不相等时**不提升、也不报错**，而是如实返回"等待对方"或
       "双方证明不一致"。后者是真问题（两边持有的 K 不同），
       但它既可能是封装算法搞混，也可能是有人伪造 ——
       这里不猜原因，只把事实说清楚，让人去查。
    """
    node = _find_node(identity)
    if node is None:
        return _error('当前账号未关联任何节点', 403)

    try:
        payload = json.loads(request.body or b'{}')
    except (ValueError, TypeError):
        return _error('请求体不是合法 JSON')
    if not isinstance(payload, dict):
        return _error('请求体应为 JSON 对象')

    proof = str(payload.get('proof') or '').strip().lower()
    if not proof or not all(c in '0123456789abcdef' for c in proof):
        return _error('proof 必须是十六进制字符串（HMAC-SHA256(K, session_id)）')
    if len(proof) != 64:
        return _error(f'proof 长度应为 64 个十六进制字符（SHA256 输出），收到 {len(proof)}')

    session = SessionKey.objects.filter(session_id=session_id).first()
    if session is None:
        return _error(f'会话不存在：{session_id}', 404)

    # 只有会话双方能确认。少了这一条，任何登录用户都能对别人的会话"确认"，
    # 而它提交的证明必然与真实一方对不上 —— 于是表现为"双方证明不一致"，
    # 把一次越权伪装成一次故障。所以先挡在这里。
    if node.id not in (session.node1_id, session.node2_id):
        return _error('你不是这条会话的一方，无权确认', 403)

    SessionKeyConfirmation.objects.update_or_create(
        session=session,
        node=node,
        defaults={
            'proof': proof,
            'key_recovered': True,
            'confirmed_at': timezone.now(),
        },
    )

    confirmations = list(SessionKeyConfirmation.objects.filter(session=session))
    if len(confirmations) < 2:
        return _ok({
            'sessionId': session_id,
            'status': session.status,
            'confirmedBy': len(confirmations),
            'established': False,
        }, msg='已记录你的确认；等待会话另一方确认')

    # 双方都在了：比较证明
    proofs = {c.proof for c in confirmations}
    if len(proofs) > 1:
        logger.warning(
            '会话 %s 双方确认证明不一致（各自持有的 K 不同）: %s',
            session_id, [(c.node_id, c.proof[:12]) for c in confirmations]
        )
        return _ok({
            'sessionId': session_id,
            'status': session.status,
            'confirmedBy': len(confirmations),
            'established': False,
        }, msg='双方确认已提交但**证明不一致**：两边解出的会话密钥不是同一把，请检查该会话的信封与算法')

    if session.status == 'established':
        return _ok({
            'sessionId': session_id, 'status': session.status,
            'confirmedBy': len(confirmations), 'established': True,
        }, msg='会话已建立（无需重复确认）')

    session.status = 'established'
    session.save(update_fields=['status'])
    logger.info('会话 %s 双方确认一致 → established', session_id)
    return _ok({
        'sessionId': session_id, 'status': 'established',
        'confirmedBy': len(confirmations), 'established': True,
    }, msg='双方确认一致，会话已建立')