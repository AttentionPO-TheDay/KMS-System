# -*- coding: utf-8 -*-
"""用户侧分发的四个接口（计划 §5.1 / D5–D8、D17）。

    GET  /user-nodes/                     我被授权的节点
    POST /key-pool/distribute-to-user/    核心：生成 N+1 份信封
    GET  /user-symmetric-keys/            我的对称密钥（含剩余有效期）
    GET  /user-symmetric-keys/<id>/       单条详情
    GET  /distribution-batches/           我的分发批次

三条贯穿全文件的硬要求
----------------------
1. **`user_id` 一律取自令牌**（经 KMS 自省），绝不从请求参数取 —— 否则改个
   `?user_id=` 就能看别人的对称密钥。这也是本文件不写 `@permission_classes([AllowAny])`
   的原因：既有视图全是 AllowAny，照抄会把越权口子一并抄过来。
2. **D17 在服务端强制**：`source_key_id` 对应密钥必须是 SM2/SSCL。前端过滤不算数，
   直接构造请求同样要拦住 —— 否则能拿到用格密码公钥封的信封，而那种信封的私钥就在服务端。
3. **节点必须在授权范围内**（D5）。同样必须在服务端校验。

关于"对称密钥查看"的可见范围
----------------------------
只返回**本人**的信封；`encrypted_key_data` 原样返回（那是密文，且只有用户自己的
`d_A` 能解开）。**绝不返回任何明文对称密钥** —— 服务端本来就没有。
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from datetime import timedelta
from functools import wraps
from typing import Any, Dict, List, Optional, Tuple

from django.db import transaction
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from . import kms_service_client as kms
from .envelope_signature import ciphertext_digest, sign_envelope, verify_envelope
from .models import DistributionBatch, Node, PreDistributedKey, SessionKey, UserKeyEnvelope, UserNodeAuthorization
from .sm4_crypto import PAYLOAD_ALGORITHM_SM4, PayloadCipher
from .wrappers import (
    NODE_DEFAULT_WRAPPING,
    NODE_WRAPPING_CHOICES,
    AlgorithmNotAllowed,
    WrapperError,
    assert_user_leg_allowed,
    build_user_envelope,
    envelope_to_json,
    wrap_for_node,
)

logger = logging.getLogger(__name__)

#: 固定 24 小时有效期（D8）。**不做成可配置**：有效期一旦可调，
#: "对称密钥有时限"这条安全属性就会随部署漂移，而用户无从知道当前是多少。
ENVELOPE_TTL_HOURS = 24

#: 单次最多分发给多少个节点（D15）。
MAX_NODES_PER_DISTRIBUTION = 10

#: 每次分发为每个节点准备的密钥条数上限（防止一次点出上万个信封）
MAX_KEYS_PER_DISTRIBUTION = 100


def _ok(data: Any = None, **extra) -> JsonResponse:
    body = {'code': 200, 'message': 'success', 'data': data}
    body.update(extra)
    return JsonResponse(body, json_dumps_params={'ensure_ascii': False})


def _error(message: str, http_status: int = 400, code: Optional[int] = None) -> JsonResponse:
    return JsonResponse(
        {'code': code or http_status, 'message': message, 'data': None},
        status=http_status,
        json_dumps_params={'ensure_ascii': False},
    )


def require_kms_user(view):
    """把请求解析成 `kms.sys_user` 身份后交给视图。

    失败时**区分**三种情况，因为它们对调用方的含义完全不同：
      * 没带令牌 / 令牌无效 → 401，用户需要重新登录；
      * KMS 连不上 → 503，是部署问题，重试可能有用；
      * 其它 → 500。

    视图函数会多收到一个 `identity` 关键字参数（含 `userId`/`userName`/`roleLevel`）。
    """

    @wraps(view)
    def wrapper(request, *args, **kwargs):
        token = kms.extract_bearer_token(request)
        if not token:
            return _error('未登录：缺少 Authorization: Bearer <token>', 401)
        try:
            identity = kms.introspect(token)
        except kms.KmsTokenInvalid as exc:
            return _error(f'登录状态无效：{exc}', 401)
        except kms.KmsServiceError as exc:
            logger.error('KMS 自省失败: %s', exc)
            return _error('身份服务暂时不可用，请稍后重试', 503)
        return view(request, *args, identity=identity, **kwargs)

    return wrapper


def _create_initiated_sessions(user_id, node_map, succeeded_node_ids, batch_id, expires_at):
    """为本次分发成功送达的每个节点登记一条 **initiated** 会话（文档 §6.5）。

    发起方是发起分发的用户 —— 按阶段 2 的 Node↔sys_user 一一映射，
    该用户本身也是一个节点。取不到映射时（管理员发起的场景）**不建会话**：
    会话是"两个节点之间"的东西，没有发起节点就不存在这条边。

    只建 initiated，不建 established —— 理由见调用点的说明：
    验签（§6.3/§6.4）尚未实现，建 established 等于宣称一个没验证过的属性。

    幂等：session_id 由 batch_id + 节点后缀构成并带唯一约束，
    重复执行同一批次不会产生重复会话（走 get_or_create）。
    """
    sender_node = Node.objects.filter(sys_user_id=user_id).first()
    if sender_node is None:
        logger.info('分发批次 %s：发起用户 %s 未映射到节点，不建会话', batch_id, user_id)
        return 0

    created = 0
    for node_db_id in succeeded_node_ids:
        target = node_map.get(node_db_id)
        if target is None or target.id == sender_node.id:
            # 自己和自己不建会话（节点向自己分发的场景没有意义）
            continue
        session_id = f'{batch_id}-n{target.id}'
        try:
            _, was_created = SessionKey.objects.get_or_create(
                session_id=session_id,
                defaults={
                    'node1': sender_node,
                    'node2': target,
                    'session_type': 'kyber_kem',
                    # 会话密钥本体不在服务端 —— 服务端只有包给双方的密文，
                    # 所以这两列如实标注"材料在信封里，不在本表"，
                    # 而不是塞一个占位明文进去（那会让"服务端不存明文"这条不变量失真）。
                    'encrypted_session_key': f'see envelopes of batch {batch_id}',
                    'key_exchange_data': json.dumps({
                        'batch_id': batch_id,
                        'dispatch': 'user_distribution',
                        'note': '会话密钥经信封分发，服务端不持有明文',
                    }, ensure_ascii=False),
                    'status': 'initiated',
                    'expires_at': expires_at,
                },
            )
            if was_created:
                created += 1
        except Exception as exc:  # noqa: BLE001
            # 单节点建会话失败不该让整次分发回滚 —— 信封已经发给它了，
            # 回滚反而会造成"用户以为没发、节点其实收到了"的更糟状态。
            logger.warning('批次 %s 为节点 %s 建会话失败: %s', batch_id, target.node_id, exc)

    if created:
        logger.info('分发批次 %s：登记 %d 条 initiated 会话（发送方 %s）',
                    batch_id, created, sender_node.node_id)
    return created


def _record_distribution_chain_event(source_key_id, key_version, sender_node, target_nodes,
                                     material_digest, batch_id):
    """把本次分发记到链上（文档 §8.6 的 KEY_DISTRIBUTED）。

    <h2>为什么失败不影响分发结果</h2>
    <b>因为分发已经成功了</b> —— 信封已经落库、密钥已经在接收方手里。
    存证是**旁路增强**：链上少一条记录不会让已发生的事变成没发生。
    如果这里抛异常并回滚分发，就变成"链写不进去 ⇒ 用户拿不到密钥"，
    把可用性问题升级成功能问题。

    所以：失败只记日志、**不改分发结论**。但调用方会把结果回显到响应里
    （`chainEvidence` 字段），让"存证没成功"这件事在界面上看得见 ——
    静默吞掉才是真正危险的：审计缺口会变成不可见。

    <h2>为什么记 source_key_id 而不是别的</h2>
    被分发的会话密钥（SM4）不在服务端、也不该上链。链上要回答的是
    "**哪把长期密钥被用于建立会话**"——那正是 source_key_id，
    也是后续做密钥泄漏关联分析时的入口。

    ⚠️ 上链的是**摘要**：`material_digest` 是信封的密文摘要，
    不是密文本身，更不是任何密钥材料。
    """
    if sender_node is None:
        # 没有发送方节点就没有"谁分发的"这个事实。宁可不上链，
        # 也不要编一个 owner 出来 —— 链上的记录一旦写错就撤不回来。
        logger.info('批次 %s：发起方未映射到节点，跳过链上存证', batch_id)
        return None
    node_code = getattr(sender_node, 'node_id', '') or ''
    try:
        tx_hash = kms.record_chain_event(
            'KEY_DISTRIBUTED',
            int(source_key_id),
            int(key_version or 0),
            node_code,
            str(material_digest or ''),
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning('批次 %s 链上存证失败: %s', batch_id, exc)
        return None
    if tx_hash:
        logger.info('批次 %s 已上链存证: keyId=%s tx=%s', batch_id, source_key_id, tx_hash)
    return tx_hash


def _authorized_node_ids(user_id: int) -> List[int]:
    """该用户当前有效的节点授权 ID 列表。"""
    return list(
        UserNodeAuthorization.objects.filter(user_id=user_id, status='active')
        .values_list('node_id', flat=True)
    )


def _safe_json_list(raw) -> List[str]:
    """把库里存的 JSON 数组字段安全解析成列表；坏了就返回空列表。

    批次列表是展示用的，不为一条坏数据把整个列表打成 500。
    """
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
        return [str(x) for x in parsed] if isinstance(parsed, list) else []
    except (ValueError, TypeError):
        return []


def _classify_distribution(user_id: int, target_nodes) -> Tuple[str, List[str], str]:
    """阶段 5（文档 §8.5）：判定本次分发是同域还是跨域。

    返回 `(发起方域, 目标域列表, 'same'|'cross'|'mixed')`。

    发起方域的取法：本系统的分发发起人是 `kms.sys_user`，而"域"是**节点**的属性
    （Node.domain_id，阶段 2 引入）。所以先经 `Node.sys_user_id` 反查发起人
    对应的节点，取它的 domain_id。

    取不到时（管理员发起、或账号未映射到节点）返回空串，并且**整体判为 mixed** ——
    "不知道发起方在哪"时不应擅自断言成"同域"，那会把跨域分发粉饰成同域，
    正好掩盖了这个标记要暴露的东西。
    """
    source_node = Node.objects.filter(sys_user_id=user_id).only('domain_id').first()
    source_domain = (getattr(source_node, 'domain_id', '') or '').strip()

    target_domains = sorted({
        (getattr(n, 'domain_id', '') or '').strip()
        for n in target_nodes
        if (getattr(n, 'domain_id', '') or '').strip()
    })

    if not source_domain or not target_domains:
        return source_domain, target_domains, 'mixed'

    same = [d for d in target_domains if d == source_domain]
    cross = [d for d in target_domains if d != source_domain]
    if cross and same:
        dist_type = 'mixed'
    elif cross:
        dist_type = 'cross'
    else:
        dist_type = 'same'
    return source_domain, target_domains, dist_type


# ---------------------------------------------------------------------------
# GET /user-nodes/
# ---------------------------------------------------------------------------
@csrf_exempt
@require_http_methods(['GET'])
@require_kms_user
def user_nodes(request, identity):
    """当前用户被授权的节点列表（只返回自己的）。"""
    rows = (
        UserNodeAuthorization.objects.filter(user_id=identity['userId'], status='active')
        .select_related('node')
        .order_by('node__node_id')
    )
    items = []
    for row in rows:
        node = row.node
        items.append(
            {
                'nodeId': node.id,
                'nodeCode': node.node_id,
                'nodeName': node.name,
                'status': node.status,
                'grantedAt': row.granted_at.isoformat() if row.granted_at else None,
                'remark': row.remark,
            }
        )
    return _ok({'nodes': items, 'maxSelectable': MAX_NODES_PER_DISTRIBUTION})


# ---------------------------------------------------------------------------
# GET /user-symmetric-keys/  +  /<id>/
# ---------------------------------------------------------------------------
def _envelope_summary(envelope: UserKeyEnvelope) -> Dict[str, Any]:
    remaining = None
    if envelope.expires_at:
        remaining = int((envelope.expires_at - timezone.now()).total_seconds())
    return {
        'id': envelope.id,
        'batchId': envelope.batch_id,
        'keyHash': envelope.key_hash,
        'wrappingAlgorithm': envelope.wrapping_algorithm,
        'sourceKeyId': envelope.source_key_id,
        'status': envelope.status,
        'createdAt': envelope.create_datetime.isoformat() if envelope.create_datetime else None,
        'expiresAt': envelope.expires_at.isoformat() if envelope.expires_at else None,
        # 剩余秒数直接算给前端，避免前端各算一套导致时区/时钟偏差
        'remainingSeconds': remaining,
        'expired': bool(remaining is not None and remaining <= 0),
    }


@csrf_exempt
@require_http_methods(['GET'])
@require_kms_user
def user_symmetric_keys(request, identity):
    """我的对称密钥列表（含剩余有效期）。

    **只返回本人**：过滤条件来自令牌里的 `userId`，与查询参数无关。
    """
    queryset = UserKeyEnvelope.objects.filter(user_id=identity['userId']).order_by('-create_datetime')

    status = request.GET.get('status')
    if status:
        queryset = queryset.filter(status=status)
    # 默认只显示未过期的；显式传 includeExpired=1 才带上历史
    if request.GET.get('includeExpired') not in ('1', 'true', 'True'):
        queryset = queryset.filter(expires_at__gt=timezone.now())

    limit = min(int(request.GET.get('limit') or 100), 500)
    items = [_envelope_summary(item) for item in queryset[:limit]]
    return _ok({'items': items, 'total': len(items), 'ttlHours': ENVELOPE_TTL_HOURS})


@csrf_exempt
@require_http_methods(['GET'])
@require_kms_user
def user_symmetric_key_detail(request, pk, identity):
    """单条详情。

    仍然按 `user_id` 过滤 —— 拿到别人的 id 也查不出来（返回 404 而不是 403：
    不要让攻击者区分"不存在"与"存在但不属于你"）。
    """
    envelope = UserKeyEnvelope.objects.filter(id=pk, user_id=identity['userId']).first()
    if envelope is None:
        return _error('对称密钥不存在', 404)

    detail = _envelope_summary(envelope)

    # 阶段 5（文档 §6.4）：**先验签，再交出密文**。
    #
    # 这里是"恢复 SM4 会话密钥"的前一步 —— 密文从这里发到客户端，
    # 客户端用自己的 d_A 解开。若在此不验签，接收方拿到的可能是伪造成
    # 某发送方的信封，而它照样能解开（封装只保证"只有我能解"，
    # 不保证"是谁发给我的"）。
    #
    # 所以验签不通过**就不给密文**：客户端拿不到密文，自然解不出 K，
    # 会话也就建立不了。这比"发出去再提示签名无效"可靠 ——
    # 提示可以被忽略，而没拿到的东西无法被忽略。
    #
    # ⚠️ 历史信封（本阶段之前签发的）没有 signature 字段。对它们**不拦**，
    #    但也不谎称已验证：如实标注 signatureState，让调用方自己判断。
    #    把"没有签名"当成"签名有效"是安全上最危险的一种默认。
    raw = envelope.encrypted_key_data or ''
    payload = _parse_b64_envelope(raw)
    sig_state, sig_msg = _verify_envelope_signature(payload)
    detail['signatureState'] = sig_state
    detail['signatureMessage'] = sig_msg

    if sig_state == 'invalid':
        # 明确拒发密文。用 200 + 业务码而不是 HTTP 4xx：
        # 前端已有统一错误处理，混用状态码会让它把安全事件显示成"网络异常"。
        return _error(f'信封验签失败，拒绝交出密文：{sig_msg}', 403)

    # `encrypted_key_data` 是**密文**，只有用户自己的 d_A 能解开，可以原样给出。
    # 服务端本来就没有明文对称密钥，所以这里不可能"多给"。
    detail['encryptedKeyData'] = envelope.encrypted_key_data
    return _ok(detail)


def _parse_b64_envelope(raw: str) -> Optional[Dict[str, Any]]:
    """把库里存的信封文本解析成字典；不是 JSON 就返回 None。"""
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else None
    except (ValueError, TypeError):
        return None


def _verify_envelope_signature(payload: Optional[Dict[str, Any]]) -> tuple:
    """验签信封，返回 `(state, message)`。

    state 取值：
      - `'valid'`       签名有效，来自声明的发送方且内容未被篡改
      - `'invalid'`     **有签名但验不过** —— 必须拒绝（可能被伪造或篡改）
      - `'missing'`     本阶段之前签发的历史信封，没有签名字段
      - `'unverifiable'` 有签名，但发送方或它的公钥取不到（无法判定）

    区分这四种而不是简单地 True/False：`missing` 与 `invalid` 的处置
    完全不同 —— 前者是历史遗留、不能因此让用户取不出旧件；
    后者是安全事件，必须拦。把它们混为一谈，要么拦死历史数据，
    要么放过真正的攻击。
    """
    if not payload:
        return 'missing', '信封内容无法解析'
    sig = payload.get('signature')
    if not sig:
        return 'missing', '该信封为历史数据（本阶段之前签发，无签名字段）'

    sender_node_id = payload.get('sender_node_id')
    if not sender_node_id:
        return 'unverifiable', '信封有签名但未标注发送方，无法定位公钥'

    sender = Node.objects.filter(node_id=sender_node_id).first()
    if sender is None or not sender.falcon_sign_public_key:
        return 'unverifiable', f'发送方 {sender_node_id} 的标准 Falcon 公钥不可用'

    # 用与签名时**同一个函数**重建被签字节串（envelope_signature.canonical_payload），
    # 两边字段集不会漂移 —— 手工重建是"签名与验签字段不一致"这类 bug 的常见来源。
    #
    # 密文部分用信封里存下的 `ciphertext_digest`，**不能现算**：
    # 现算依赖"内层密文序列化方式不变"，而序列化实现一旦调整
    # （哪怕只是字段顺序），历史信封会全部验不过 —— 那种失败看起来
    # 像"信被篡改了"，实际是我们的序列化改了，会引发错误的告警。
    signed_view = {
        'batch_id': payload.get('batch_id'),
        'wrapping_algorithm': payload.get('wrapping_algorithm'),
        'payload_algorithm': payload.get('payload_algorithm'),
        'recipient_user_id': payload.get('recipient_user_id'),
        'ciphertext_digest': payload.get('ciphertext_digest'),
        'source_key_id': payload.get('source_key_id'),
        'expires_at': payload.get('expires_at'),
    }
    try:
        ok = verify_envelope(signed_view, sig, sender.falcon_sign_public_key)
    except Exception as exc:  # noqa: BLE001
        logger.warning('验封信封异常（按不可验证处理）: %s', exc)
        return 'unverifiable', f'验签过程异常：{exc}'

    return ('valid', '签名有效') if ok else ('invalid', '签名无效：信封可能被伪造或篡改')


# ---------------------------------------------------------------------------
# GET /distribution-batches/
# ---------------------------------------------------------------------------
@csrf_exempt
@require_http_methods(['GET'])
@require_kms_user
def distribution_batches(request, identity):
    """我的分发批次记录。"""
    queryset = DistributionBatch.objects.filter(user_id=identity['userId']).order_by('-create_datetime')
    limit = min(int(request.GET.get('limit') or 50), 500)
    items = []
    for batch in queryset[:limit]:
        try:
            node_ids = json.loads(batch.node_ids or '[]')
        except (ValueError, TypeError):
            node_ids = []
        items.append(
            {
                'batchId': batch.batch_id,
                'sourceKeyId': batch.source_key_id,
                'wrappingAlgorithm': batch.wrapping_algorithm,
                'nodeIds': node_ids,
                'nodeCount': len(node_ids),
                'nodeSuccessCount': batch.node_success_count,
                'userEnvelopeOk': bool(batch.user_envelope_ok),
                'status': batch.status,
                'createdAt': batch.create_datetime.isoformat() if batch.create_datetime else None,
                # 阶段 5（文档 §8.5）：跨域标记。历史批次没有这三个字段，
                # 如实返回空值而不是编造一个 'same' —— 那会把"未记录"
                # 粉饰成"已确认同域"。
                'sourceDomainId': batch.source_domain_id or '',
                'distributionType': batch.distribution_type or '',
                'targetDomainIds': _safe_json_list(batch.target_domain_ids),
                # 阶段 5（§6.5）：本次分发登记了哪些会话（均为 initiated，未确认）
                'sessionCount': _safe(lambda b=batch: SessionKey.objects.filter(
                    session_id__startswith=b.batch_id + '-').count(), 'batch.sessions'),
            }
        )
    return _ok({'items': items, 'total': len(items)})


# ---------------------------------------------------------------------------
# POST /key-pool/distribute-to-user/   —— 核心
# ---------------------------------------------------------------------------
def _validate_request(payload: Dict[str, Any], user_id: int) -> Tuple[Optional[dict], Optional[JsonResponse]]:
    """把请求校验集中在一处，且**按"越权 → 参数"的顺序**。

    先校验越权、再校验参数格式：这样"你无权访问这个节点"不会被
    "node_ids 格式错误"掩盖掉。
    """
    source_key_id = payload.get('source_key_id') or payload.get('sourceKeyId')
    if source_key_id in (None, ''):
        return None, _error('缺少 source_key_id（你要用哪把非对称密钥来封装）')
    try:
        source_key_id = int(source_key_id)
    except (TypeError, ValueError):
        return None, _error('source_key_id 必须是整数')

    raw_nodes = payload.get('node_ids') or payload.get('nodeIds') or []
    if not isinstance(raw_nodes, list) or not raw_nodes:
        return None, _error('请至少选择一个节点')
    if len(raw_nodes) > MAX_NODES_PER_DISTRIBUTION:
        return None, _error(f'一次最多选择 {MAX_NODES_PER_DISTRIBUTION} 个节点（D15）')
    try:
        node_ids = [int(n) for n in raw_nodes]
    except (TypeError, ValueError):
        return None, _error('node_ids 必须是整数数组')

    # D5：节点必须在**该用户自己的**授权范围内。这是服务端强制，
    # 不依赖前端下拉只显示有权的节点。
    allowed = set(_authorized_node_ids(user_id))
    unauthorized = [n for n in node_ids if n not in allowed]
    if unauthorized:
        # 不回显"哪些节点存在但你没权"，只说没权 —— 避免把节点清单探测出来
        return None, _error(f'你没有以下节点的通信权限：{unauthorized}（共 {len(unauthorized)} 个）', 403)

    count = payload.get('count') or 1
    try:
        count = int(count)
    except (TypeError, ValueError):
        return None, _error('count 必须是整数')
    if count < 1 or count > MAX_KEYS_PER_DISTRIBUTION:
        return None, _error(f'count 必须在 1..{MAX_KEYS_PER_DISTRIBUTION} 之间')

    # 节点腿的封装算法由用户选择（2026-09-26 起）：
    # 抗量子 Kyber / 抗量子 Falcon。不在白名单里就直接拒，
    # 免得脏值一路走到封装层才报错。
    node_wrapping = (
        payload.get('node_wrapping_algorithm')
        or payload.get('nodeWrappingAlgorithm')
        or NODE_DEFAULT_WRAPPING
    )
    node_wrapping = str(node_wrapping).strip().lower()
    if node_wrapping not in NODE_WRAPPING_CHOICES:
        return None, _error(
            f'节点封装算法不支持：{node_wrapping}（可选 {", ".join(NODE_WRAPPING_CHOICES)}）'
        )

    return {
        'source_key_id': source_key_id,
        'node_ids': node_ids,
        'count': count,
        'node_wrapping_algorithm': node_wrapping,
    }, None


@csrf_exempt
@require_http_methods(['POST'])
@require_kms_user
def distribute_to_user(request, identity):
    """核心：把对称密钥分发给选中的节点**以及用户本人**（D6）。

    流程（顺序是有讲究的）：
      1. 解析请求体；
      2. **先问主 KMS 要加密目标点** `P_A` —— 顺便就完成了 D17 的算法校验
         （主 KMS 只对 SM2/SSCL 返回 `ok=true`），拿到不行的答案就地返回，
         一次密钥运算都不做；
      3. 校验节点授权；
      4. 生成载荷密钥 → 给用户封一份 → 给每个节点各一份；
      5. 记批次。

    ⚠️ 目标点是 `P_A = W_A + λ·P_pub`，**不是** `key_value` 里的 `finalPublicKey`。
    用后者封出来的信封**谁都打不开**（§3.2.3）。
    """
    try:
        payload = json.loads(request.body or b'{}')
    except (ValueError, TypeError):
        return _error('请求体不是合法 JSON')
    if not isinstance(payload, dict):
        return _error('请求体应为 JSON 对象')

    user_id = identity['userId']

    # 阶段 7（文档 §8.4）：节点多级授权 —— 发起分发需要 distribute 能力（L2 及以上）。
    #
    # 为什么在这里强制：节点就是 `kms.sys_user`（阶段 2 建立的一一映射），
    # 所以"节点发起分发"走的正是这个入口。此前 permission_level **只存不用**，
    # 管理员设了等级却不产生任何效果 —— 那比没有这个字段更糟，
    # 使用者会以为自己已经限制了权限。
    #
    # 管理员（未映射到节点）不受此限：他们是治理主体，不是业务节点。
    _node = Node.objects.filter(sys_user_id=user_id).only('permission_level').first()
    if _node is not None:
        from .node_permission import CAP_DISTRIBUTE, NodePermissionError, require_capability
        try:
            require_capability(_node, CAP_DISTRIBUTE)
        except NodePermissionError as exc:
            # 给出结构化提示（需要什么能力、当前什么等级），而不是笼统的"无权限"
            return _error(str(exc), 403)

    params, error = _validate_request(payload, user_id)
    if error is not None:
        return error
    source_key_id = params['source_key_id']
    node_ids = params['node_ids']
    count = params['count']
    node_wrapping = params['node_wrapping_algorithm']

    # --- 第一步：向主 KMS 要加密目标点。它同时承担 D17 的算法校验。 ---
    try:
        key_info = kms.user_public_key(source_key_id)
    except kms.KmsServiceError as exc:
        logger.error('取用户公钥失败: keyId=%s err=%s', source_key_id, exc)
        return _error('密钥服务暂时不可用，请稍后重试', 503)

    if not key_info.get('ok'):
        # 这把密钥不能用于分发。主 KMS 已经给出了原因（不存在/已回收/算法不支持），
        # 原样转达比在这里重编一句更准确。
        return _error(key_info.get('errorMessage') or '该密钥不能用于分发', 400)

    # 主 KMS 已经按 D17 收窄过，这里再断言一次：**纵深防御**。
    # 万一日后有人改了主 KMS 的白名单，分发侧仍然拦得住。
    try:
        assert_user_leg_allowed(key_info.get('encrytName') or '')
    except AlgorithmNotAllowed as exc:
        return _error(str(exc), 400)

    recipient_public_key = key_info.get('publicKey')
    if not recipient_public_key:
        return _error('密钥服务未返回加密目标点', 502)

    # 按用户给定的顺序取节点，便于回显时与选择顺序一致
    node_map = {node.id: node for node in Node.objects.filter(id__in=node_ids)}
    missing = [n for n in node_ids if n not in node_map]
    if missing:
        return _error(f'节点不存在：{missing}', 404)

    batch_id = f'dist-{timezone.now().strftime("%Y%m%d%H%M%S")}-{uuid.uuid4().hex[:8]}'
    expires_at = timezone.now() + timedelta(hours=ENVELOPE_TTL_HOURS)
    wrapping_algorithm = (key_info.get('encrytName') or '').upper()

    # 阶段 5（§6.3）：发送方节点 —— 它是对信封**签名**的一方。
    # 按阶段 2 的 Node↔sys_user 一一映射取；管理员发起时取不到，
    # 此时不签名（而非签一个空值），并由下方日志如实记录。
    sender_node = Node.objects.filter(sys_user_id=user_id).first()
    if sender_node is None:
        logger.info('分发批次 %s：发起用户 %s 未映射到节点，信封将不含签名',
                    batch_id, user_id)

    envelopes: List[UserKeyEnvelope] = []
    node_records: List[PreDistributedKey] = []
    node_results: List[Dict[str, Any]] = []
    failed: List[str] = []
    #: 本次分发里最后一份信封的密文摘要 —— 链上存证用它代表"分发了什么"。
    #: 传摘要而非密文：链上只需要能核验是不是同一份东西。
    last_envelope_digest = ''

    try:
        with transaction.atomic():
            for _ in range(count):
                # 每个节点、以及用户本人，各拿一把**独立**的载荷密钥。
                # 共用一把会让任意一个节点被攻破就波及全部收件人。
                payload_key = PayloadCipher.generate_key()
                # 与本仓库既有写法保持一致（key_pool_service.py 也是这么算的）。
                # 存哈希而不存密钥本身：这张表里**不应该**出现任何明文对称密钥。
                key_hash = hashlib.sha256(payload_key).hexdigest()

                # 用户本人的那份（D6：既要发给节点，也要发给用户）—— 用户腿走国密
                user_envelope = build_user_envelope(
                    payload_key, wrapping_algorithm, recipient_public_key
                )

                # 阶段 5（文档 §6.3/§6.4）：发送方用自己的 **标准 Falcon 私钥**签名。
                #
                # 封装保证机密性（只有收件人能解开），签名保证**来源与完整性**
                # （这封信确实来自声明的发送方、且未被中途篡改）。
                # 只做封装不做签名，接收方无法区分真信与伪造信 —— 两者它都能解开。
                #
                # 用**标准** Falcon 而非节点原有的 CL-Falcon 格材料：
                # 后者与标准 DLL 不兼容（实测是 D_id/S_id 矩阵），签不了名。
                # 这也正是文档 §0.5 要求 Falcon 回归标准签名算法的原因。
                #
                # 被签的字段集合由 envelope_signature.SIGNED_FIELDS 唯一决定，
                # 验签侧用同一个函数重建，两边不会漂移。
                #
                # 密文部分签的是**摘要**而非原文：签名会往信封里加 signature 字段，
                # 若签原文，验签时拿存储值反推必然重建不出同一份字节串
                # （自己签的信自己验不过）。摘要只取决于内层密文，与签名本身无关。
                inner_json = envelope_to_json(user_envelope)
                envelope_for_sign = {
                    'batch_id': batch_id,
                    'wrapping_algorithm': wrapping_algorithm,
                    'payload_algorithm': PAYLOAD_ALGORITHM_SM4,
                    'recipient_user_id': user_id,
                    'ciphertext_digest': ciphertext_digest(inner_json),
                    'source_key_id': source_key_id,
                    'expires_at': expires_at.isoformat(),
                }
                last_envelope_digest = envelope_for_sign['ciphertext_digest']
                if sender_node is not None and sender_node.falcon_sign_private_key:
                    _sig = sign_envelope(envelope_for_sign, sender_node.falcon_sign_private_key)
                    if _sig:
                        user_envelope['signature'] = _sig
                        user_envelope['sender_node_id'] = sender_node.node_id
                        user_envelope['signature_algorithm'] = 'Falcon-512'
                        # 把摘要也存进信封：验签侧要用它重建被签字节串，
                        # 而它必须与签名时用的值**逐字节相同**。
                        # 从内层密文现算也行，但那样"摘要算法变了"会让
                        # 历史信封全部验不过 —— 存下来更稳。
                        user_envelope['ciphertext_digest'] = envelope_for_sign['ciphertext_digest']
                    else:
                        # 签不出来就**不写**签名字段 —— 写个空串会让验签侧
                        # 以为"有签名但没通过"，与"根本没签"是两回事。
                        logger.warning('批次 %s：发送方 %s 签名失败，该信封将不含签名',
                                       batch_id, sender_node.node_id)

                envelopes.append(
                    UserKeyEnvelope(
                        batch_id=batch_id,
                        user_id=user_id,
                        key_hash=key_hash,
                        encrypted_key_data=envelope_to_json(user_envelope),
                        wrapping_algorithm=wrapping_algorithm,
                        source_key_id=source_key_id,
                        status='unused',
                        expires_at=expires_at,
                    )
                )

                # --- 节点腿：抗量子（D10 节点侧零改动），封的是**同一把 payload_key** ---
                # 这是 D10 方案 A 成立的根本：两条腿算法不同，但解出来的 K 必须相同，
                # 否则用户与节点根本对不上（计划 §3.1）。
                # 因此这里**绝不能**再 generate_key() 一次 —— 那会让两条腿各持一把 K，
                # 表面上"两边都能解开"，实际双方谁也解不开对方发的消息。
                for node in node_map.values():
                    try:
                        node_envelope, _ = wrap_for_node(payload_key, node, node_wrapping)
                    except WrapperError as exc:
                        # 单个节点封装失败不应让整批失败：如实记下来，
                        # 批次状态由**真实成功数**决定，而不是"选了几个节点"。
                        failed.append(f'{node.node_id}: {exc}')
                        continue

                    node_algorithm = node_envelope.get('wrapping_algorithm') or NODE_DEFAULT_WRAPPING
                    node_records.append(
                        PreDistributedKey(
                            pool_id=batch_id,
                            # ⚠️ 这里必须用**批次内全局递增**的计数，不能用外层循环的 index。
                            # 表上有 (pool_id, key_index) 唯一约束，而一批里
                            # 「份数 × 节点数」会产出多条：若两条都用 index=0 就会撞唯一键，
                            # 报的是 IntegrityError 1062（听起来像数据脏，实际是编号规则错了）。
                            key_index=len(node_records),
                            node1=node,
                            node2=None,
                            algorithm=node_algorithm,
                            wrapping_algorithm=node_algorithm,
                            payload_algorithm=PAYLOAD_ALGORITHM_SM4,
                            source_key_id=source_key_id,
                            recipient_type='node',
                            # 用户发起的场景下节点不在请求里，信封必须**存下来**供节点取用；
                            # 节点间池路径是直接返回给调用方，故那边存 '{}'。
                            encrypted_key_data=json.dumps(node_envelope, ensure_ascii=False),
                            key_hash=key_hash,
                            status='distributed',
                            expires_at=expires_at,
                        )
                    )

            UserKeyEnvelope.objects.bulk_create(envelopes)
            if node_records:
                PreDistributedKey.objects.bulk_create(node_records)

            # 只有**真正封成功的**节点才算进成功数。
            # 谎报的代价很具体：批次列表显示"全部成功"，而节点上什么都没有，
            # 排查时会被引向完全错误的方向。
            succeeded_node_ids = {record.node1_id for record in node_records}
            for node_id in node_ids:
                node = node_map[node_id]
                delivered = node.id in succeeded_node_ids
                node_results.append(
                    {
                        'nodeId': node.id,
                        'nodeCode': node.node_id,
                        'nodeName': node.name,
                        'delivered': delivered,
                        'note': None if delivered else '封装失败，详见 failed',
                    }
                )

            success_count = len(succeeded_node_ids)
            # 阶段 5（文档 §8.5）：跨域标记。
            # 快照而非回查 —— "这次分发当时是不是跨域"是历史事实，
            # 不该因后续部门调动/节点换域而被改写。
            src_domain, target_domains, dist_type = _classify_distribution(
                user_id, [node_map[nid] for nid in node_ids if nid in node_map]
            )
            batch = DistributionBatch.objects.create(
                batch_id=batch_id,
                user_id=user_id,
                source_key_id=source_key_id,
                wrapping_algorithm=wrapping_algorithm,
                node_ids=json.dumps(node_ids),
                node_success_count=success_count,
                user_envelope_ok=True,
                # 用户那份与**全部**节点都成功才算 success；否则如实记 partial
                status='success' if success_count == len(node_ids) else 'partial',
                source_domain_id=src_domain,
                target_domain_ids=json.dumps(target_domains, ensure_ascii=False),
                distribution_type=dist_type,
            )

            # 阶段 5（文档 §6.5）：分发成功后建立会话。
            #
            # ⚠️ 只建 **initiated**，不建 established —— 这个区别是刻意的。
            #
            # 文档 §6.5 规定只有满足三条之后才算会话建立：
            #   ① 接收方验签成功 ② 成功恢复 SM4 会话密钥 ③ 双方完成确认
            # 而第 ① 条依赖 Falcon 对信封签名（§6.3/§6.4），**本轮尚未实现**
            # （协议级改造，见本仓库提交说明）。在没有验证手段的情况下建
            # established 会话，等于**宣称一个没验证过的安全属性** ——
            # 比不建会话更危险：后续用它传数据时，没人知道对面是否真的持有同一把密钥。
            #
            # 所以这里只如实登记"会话已发起"：接收方已拿到信封、
            # 密钥材料已就位，**尚未确认**。待验签流程补齐后再由那条链路提升为
            # established。`SessionKey.status` 的默认值本就是 'initiated'。
            _create_initiated_sessions(user_id, node_map, succeeded_node_ids, batch_id, expires_at)

    except WrapperError as exc:
        logger.error('封装失败: batch=%s err=%s', batch_id, exc)
        return _error(f'封装失败：{exc}', 500)
    except Exception as exc:  # noqa: BLE001
        logger.exception('分发失败: batch=%s', batch_id)
        return _error(f'分发失败：{exc}', 500)

    # 阶段 7（文档 §8.6）：把这次分发记到链上。
    #
    # ⚠️ 位置在事务**之外**：存证失败不该回滚一次已经成功的分发
    #    （信封已落库、密钥已在接收方手里）。详见该函数的说明。
    chain_tx = _record_distribution_chain_event(
        source_key_id=source_key_id,
        key_version=key_info.get('version'),
        sender_node=sender_node,
        target_nodes=node_map,
        material_digest=last_envelope_digest,
        batch_id=batch_id,
    )

    return _ok(
        {
            'batchId': batch.batch_id,
            'sourceKeyId': source_key_id,
            'wrappingAlgorithm': wrapping_algorithm,
            # 节点腿实际用的封装算法（用户选的），回显便于界面与排障确认
            'nodeWrappingAlgorithm': node_wrapping,
            # 回显实际使用的目标点：分发模块与 KMS 的推导不一致时，
            # 这是最快的定位线索（它是公开值，回显无害）
            'recipientPublicKey': recipient_public_key,
            'keyCount': count,
            'nodeResults': node_results,
            'userEnvelopeCount': len(envelopes),
            'failed': failed,
            'expiresAt': expires_at.isoformat(),
            'ttlHours': ENVELOPE_TTL_HOURS,
            'status': batch.status,
            # 链上存证结果。不回显成布尔值而是给哈希：拿不到哈希时，
            # 前端能如实说"已分发，但存证未成功"，而不是把两者混为一谈。
            # 缺失既是可诊断的，也不影响分发本身已成立这个事实。
            'chainHash': chain_tx or '',
        }
    )