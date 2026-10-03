# -*- coding: utf-8 -*-
"""节点侧的**取信封**、**验签/解封回执**与**会话确认**（文档 §6.5）。

    GET  /node-self/envelopes/                    我可解封的节点腿信封
    POST /node-self/sessions/<sid>/versions/      这条会话该用哪两版密钥（KMS-011）
    POST /node-self/envelopes/<id>/verify/        回执：我在这台设备上验签通过（KMS-011）
    POST /node-self/envelopes/<id>/recover/       回执：我在这台设备上解封成功（KMS-011）
    POST /node-self/sessions/<sid>/confirm/       提交"我已恢复 K"的证明（KMS-012 起走状态机）
    POST /node-self/sessions/<sid>/close/         关闭会话（终态，不可恢复）

这几件事为什么必须一起做
------------------------
§6.5 规定会话提升为 established 需要三条齐备：
    ① 接收方验签成功  ② 成功恢复 SM4 会话密钥  ③ 双方完成确认
其中 ② 此前**从未发生过** —— 服务端只封装、入库，然后就停在那里。
（`views.py` 里那几处 decaps 都在前端不调用的旧端点里。）

所以这里补的是 ② 与 ③：
  * `envelopes` 把节点自己那腿信封交给它，**服务端不再代解**；
  * `confirm` 收下节点算出的 `HMAC(K, session_id)`，由服务端比较双方是否一致。

KMS-011 补的是 ① 与 ②的**回执**：解封发生在接收节点的浏览器里（私钥只在
本地，服务端做不到也不该做），所以 verify / recover 两个端点是**节点如实
回报"我在本机完成了哪一步"**，服务端据此把会话推进到
`recipient_verified` / `key_recovered`（`SESSION_TRANSITIONS` 里那两条边
此前**没有任何写入点**）。推进只走状态机的合法边 —— 先 `recover` 后
`verify` 会被拒，因为 `initiated → key_recovered` 不是一条允许的边。

KMS-012 补的是 ③与"建立"这一步的**门**：`confirm` 不再直接写
`established`，而是经 `_maybe_establish` 走 `SESSION_TRANSITIONS`
（唯一能到 established 的边是 `key_recovered → established`）——
证明可以**随时提交、顺序独立**，但"建立"必须等验签与解封的回执都到齐；
终态会话不再接受确认（`SESSION_TERMINAL`）。另补 `close`（双方可关、
终态不可恢复）与会话列表的双方确认数。

⚠️ 回执是**节点的声明**，与 confirm 的 proof 是同一性质：服务端无法独立
   验证"它真的解开了"。真正起作用的是后面双方 proof 的相互匹配 ——
   单方随便算一个值必然与对方对不上、提升不了。这两个状态的价值是
   **审计**（"验签过""解封过"各有一条时间线），不是信任锚。

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
import re
from typing import Optional

from django.db.models import Count, Q
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from . import api_contract as C
from .distribution_service import _canonical_inner_json
from .envelope_signature import ciphertext_digest, verify_node_envelope
from .models import Node, NodeLongTermKey, PreDistributedKey, SessionKey, SessionKeyConfirmation
from .node_key_registry import require_key_version, require_usable_key
from .user_distribution_views import require_kms_user
from .kms_service_client import record_chain_event

logger = logging.getLogger(__name__)

#: 取信封时要按登记表（`NodeLongTermKey`）判可用性的算法集合。
#: 信封算法经 `canonical_algorithm` 归一后落在这四个里的，说明它靠节点的长期
#: 密钥解封：Kyber/SM2/SSCL 是保护算法；FALCON 是历史 `falcon_lattice`
#: 归一后的落点。其它取值（如 `AES` 老会话遗留）**跳过判定** ——
#: 登记表不为它们保存行，拿去判等于用一把不相干的密钥下结论。
_GATED_ALGORITHMS = tuple(C.PROTECTION_ALGORITHMS) + tuple(C.SIGNATURE_ALGORITHMS)

#: hex 形状（与 node_self_views._HEX_RE 同一条判法：先认 hex，再认 base64）。
_HEX_RE = re.compile(r'[0-9a-fA-F]+')


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
def _error(msg, code=400, error_code=None):
    """`error_code` 是可编程的 `api_contract.ERR_*`（如 `KEY_REVOKED`），放在 `data` 里。

    **不换约定** —— 把 `code` 改成字符串会静默破坏所有既有调用方对 `code === 200`
    的判断（与 `node_self_views._error` 同一条兼容决定，见 doc/kms-callsite-inventory.md §七）。
    "哪一种失败"必须可编程区分：取信封被拒时，调用方看 `data.error_code` 就知道
    是"密钥已回收"还是别的，不必匹配中文文案 —— 文案会改，码不会。
    """
    return JsonResponse(
        {'code': code, 'msg': msg, 'data': {'error_code': error_code} if error_code else None},
        status=200,
    )


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

    ⚠️ KMS-007：交出信封 = 据此建立**新会话**，所以在组装响应之前，会按这批
       信封实际用到的算法判长期密钥还能不能用（判据 = 登记表）。已回收/已过期
       时**拒发**，错误码放在 `data.error_code`（`KEY_REVOKED` / `KEY_EXPIRED`）。
       详见下方闸门的注释。
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
    records = list(queryset[:limit])

    # 闸门（KMS-007）：把信封交出去 = 节点据此建立**新会话**（计划 §7 阶段 2 的
    # "新会话"），所以在组装响应**之前**，先对这批信封实际用到的算法逐个判长期
    # 密钥是否还能用于新工作。
    #
    # 不做这一步会怎样：本接口不读任何密钥材料，密钥被回收在响应里**完全看不出来** ——
    # 节点照常拿到信封、照常解封；若回收时物化列没被清（清列只发生在被回收的那把
    # 原本是 ACTIVE 时），它甚至能解出 K 并把会话推成 established。一把登记表里已
    # 判死的密钥继续产生新会话，而服务端全程只有 200 —— 判据③要的正是让这种情形
    # 返回明确错误码，而不是静默照常。
    #
    # ⚠️ 只判**这批信封里出现过的算法**，不判"节点名下所有算法"：
    #    判后者会让一次不相干算法的回收把其它算法的信封一并锁死；
    #    判前者才与"这些信封靠哪把密钥解封"对齐。
    # ⚠️ 归一后不在 `_GATED_ALGORITHMS` 里的取值跳过（`canonical_algorithm`
    #    对不认识的输入原样大写返回、不抛异常，所以这里必须自己按集合过滤）。
    # ⚠️ 拒绝只覆盖 `KEY_REVOKED` / `KEY_EXPIRED` —— 判据③要的是"回收后有明确
    #    错误码"；`KEY_NOT_FOUND`（登记表里压根没有该算法的行）**放行**：那是
    #    "从未登记过"或历史回填缺行，不是回收事件，把既有行为升级成新拒绝
    #    不属于本次范围（否则历史 `falcon_lattice` 信封会把节点直接锁在门外）。
    # 判的是 `for_new_work`（默认 True，只认在产版本）：即使节点还留着更早的
    # RETIRED 版本，回收之后也不再用它开新会话；这正是"回收禁止新会话"。
    # 错误出口沿用本文件约定：HTTP 200 + 业务码，可编程码放 `data.error_code`。
    algorithms = []
    for record in records:
        algorithm = C.canonical_algorithm(record.wrapping_algorithm or record.algorithm)
        if algorithm in _GATED_ALGORITHMS and algorithm not in algorithms:
            algorithms.append(algorithm)

    for algorithm in algorithms:
        try:
            require_usable_key(node, algorithm)
        except C.ContractError as exc:
            if exc.code not in (C.ERR_KEY_REVOKED, C.ERR_KEY_EXPIRED):
                continue
            logger.error('节点 %s 取信封被拒：%s 长期密钥不可用 code=%s err=%s',
                         node.node_id, algorithm, exc.code, exc.message)
            return _error(exc.message, C.ERROR_HTTP_STATUS.get(exc.code, 400),
                          error_code=exc.code)

    items = []
    for record in records:
        try:
            envelope = json.loads(record.encrypted_key_data or '{}')
        except (ValueError, TypeError):
            envelope = None
        # KMS-011：把"这条信封对应哪条会话、我是不是收件方"一并给出。
        # 判 `node2`（接收方）而不是"参与" —— 发送方自己也看得到这条信封
        # （它就在列表里），但取信/回执只对接收方有意义。
        session = _session_of_batch(record.pool_id, node)
        items.append({
            'envelopeId': record.pk,
            'poolId': record.pool_id,
            'keyIndex': record.key_index,
            'wrappingAlgorithm': record.wrapping_algorithm or record.algorithm,
            'payloadAlgorithm': record.payload_algorithm,
            'keyHash': record.key_hash,
            'status': record.status,
            'expiresAt': record.expires_at.isoformat() if record.expires_at else None,
            'createdAt': record.create_datetime.isoformat() if record.create_datetime else None,
            # 会话定位与身份：null 表示这个批次不是以"节点到节点会话"建的
            # （例如旧流程的节点腿信封）。页面据此提示"该批次没有对应会话"，
            # 而不是给一个点了会 404 的按钮。
            'sessionId': session.session_id if session else None,
            'sessionStatus': session.status if session else None,
            'isRecipient': bool(session and session.node2_id == node.id),
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
    page = list(queryset[:limit])
    # KMS-012：双方确认数（"x/2"）。一条聚合查询取全部页内会话的计数 ——
    # 逐行查会 N+1，而列表页的会话数本来就可能上百。
    counts = dict(
        SessionKeyConfirmation.objects
        .filter(session__in=page)
        .values_list('session_id')
        .annotate(n=Count('id'))
    )
    items = [
        {
            'sessionId': s.session_id,
            'senderNode': s.node1.name if s.node1_id else '',
            'recipientNode': s.node2.name if s.node2_id else '',
            'protectionAlgorithm': s.session_type,
            'status': s.status,
            # KMS-011：这条会话关联的具体密钥版本（计划 §7 阶段 4 第 1 条）。
            # 历史会话没有这些列 → null；页面**如实显示"—"**，不编。
            'recipientKeyId': s.recipient_key_id,
            'recipientKeyVersion': s.recipient_key_version,
            'falconKeyId': s.falcon_key_id,
            'falconKeyVersion': s.falcon_key_version,
            'createdAt': s.create_datetime.isoformat() if s.create_datetime else None,
            'expiresAt': s.expires_at.isoformat() if s.expires_at else None,
            # node1 是会话发起节点（模型上的语义，见 models.py 的 help_text）。
            # 用 id 而非名字比较，与上面的过滤口径一致。
            'isSender': s.node1_id == node.id,
            # KMS-011：我是不是接收方、这一步能不能由我做。页面按它决定
            # 显示"处理（取信→验签→解封）"还是"等待对方处理"——
            # 而不是让用户点了才发现 403。
            'isRecipient': s.node2_id == node.id,
            # KMS-012：双方确认数（0..2）。页面显示"x/2 已确认"；
            # 两个都确认但状态还是 key_recovered，说明证明不一致或状态机没放行，
            # 页面据此提示去查而不是干等。
            'confirmedCount': int(counts.get(s.id, 0)),
        }
        for s in page
    ]
    return _ok({'items': items, 'total': len(items)})


def _as_envelope_pk(raw):
    """信封 ID（`PreDistributedKey` 主键）解析：只收 ≥1 的整数或纯数字串。

    不做 `int()` 兜底 —— `int('1.9')` 抛异常还算好，`int(1.9)` 得 1 是
    "以为查的是 1.9 实际查的是 1"，与 `node_key_registry._as_version`
    同一条纪律。认不出就拒，让调用方知道自己传错了，而不是替它猜一个。
    """
    if isinstance(raw, bool) or raw is None:
        raise C.ContractError(f'信封 ID 应为正整数，收到 {raw!r}', code=C.ERR_INVALID_PARAMETER)
    if isinstance(raw, int):
        value = raw
    elif isinstance(raw, str) and raw.strip().isdigit():
        value = int(raw.strip())
    else:
        raise C.ContractError(f'信封 ID 应为正整数，收到 {raw!r}', code=C.ERR_INVALID_PARAMETER)
    if value < 1:
        raise C.ContractError(f'信封 ID 应为正整数，收到 {value}', code=C.ERR_INVALID_PARAMETER)
    return value


def _resolve_envelope_for(node, envelope_pk):
    """把信封 ID 解析成**发给这个节点**的那一条池行；否则抛 ContractError。

    两个拒绝必须分开，因为处置完全不同：
      * `ENVELOPE_NOT_FOUND`（404）—— 没这条记录，核对 ID 与批次历史；
      * `NOT_ENVELOPE_RECIPIENT`（403）—— 记录在，但收件人不是当前节点。

    ⚠️ 孤立来看，"不是发给你的"与"不存在"都可以答 404（不泄露存在性）。
       但本仓库已有 `NOT_ENVELOPE_RECIPIENT` 码与 `ERR_NOT_ENVELOPE_RECIPIENT`
       的提示文案（api_contract），且这是**节点对节点**的封闭系统：
       信封 ID 只在双方与分发记录里出现，枚举价值有限。所以按码分开报，
       页面据此给出"这不是发给你的信"而不是"记录不存在"。
    """
    record = PreDistributedKey.objects.filter(pk=envelope_pk).first()
    if record is None:
        raise C.ContractError(f'信封不存在：{envelope_pk}', code=C.ERR_ENVELOPE_NOT_FOUND)
    if record.recipient_type != 'node' or record.node1_id != node.id:
        raise C.ContractError(
            '该信封不是发给当前节点的，无权处理', code=C.ERR_NOT_ENVELOPE_RECIPIENT,
        )
    return record


def _envelope_payload(record):
    """一条池行 → 信封字典（解析失败返回 None，由调用方按"不可解析"处理）。"""
    text = record.encrypted_key_data or '{}'
    try:
        parsed = json.loads(text)
    except (ValueError, TypeError):
        return None
    return parsed if isinstance(parsed, dict) else None


def _load_envelope_json(record):
    """信封 JSON 原文（摘要重算要用**库里的原始文本**，不能用重新序列化的结果）。

    ⚠️ 这是本模块最容易做错的一步：摘要算的是"内层密文那几项的紧凑 JSON"，
       而 `json.dumps` 对 dict 重新序列化会按插入序输出 —— 与入库时的
       `sort_keys=True` 口径不同，重算出来的摘要与信封里存的对不上，
       报出来是 `ENVELOPE_TAMPERED`（像被篡改），实际只是读取方自己序列化错了。
    """
    return record.encrypted_key_data or '{}'


@csrf_exempt
@require_http_methods(['POST'])
@require_kms_user
def node_session_versions(request, session_id, identity):
    """这条会话**该用哪两版密钥**验收/解封（KMS-011）。

    返回 `{recipientKeyId, recipientKeyVersion, falconKeyId, falconKeyVersion}`
    —— 都是**分发时写进会话行的那一份**（不是"当前生产版本"，也不是页面
    自己从 batch_id 拼出来的猜测值）。缺值时如实返回 null，不编。

    <h2>为什么 fid 要用 POST 而不是塞进会话列表</h2>
    会话列表（`node_sessions`）是"列我参与的全部会话"，逐条附上版本会在
    历史会话（没有这些列）上输出一堆 null，页面分不清"历史数据"与
    "数据丢了"。按需查一条，缺值就是缺值。

    <h2>为什么要归一化 falcon 公钥</h2>
    接收方要拿**发送方那一版**公钥去本机验签，而浏览器密钥库里的公钥一律
    是**小写 hex**（与 `node_self_views._public_key_hex` 的"比对形式"同形）。
    服务端登记表里存的是节点上传的原样字节串 —— 现在恰好都是 hex，
    但**编码是登记时的约定，不是长期保证**。所以这里按同一套规则归一：
    hex 原样小写，base64 解码后转 hex，转不动返回空串（页面据此显示
    "无法比对"，而不是拿一段看起来像公钥的东西去比、然后永远不相等）。

    ⚠️ 顺序错一格的后果写在 `_public_key_hex`：**先认 hex 再认 base64** ——
       一段 hex 串往往也能被 base64 解码（得到等长错字节、不报错）。
    """
    node = _find_node(identity)
    if node is None:
        return _error('当前账号未关联任何节点', 403)

    session = SessionKey.objects.filter(session_id=session_id).first()
    if session is None:
        return _error(f'会话不存在：{session_id}', 404, error_code=C.ERR_SESSION_NOT_FOUND)
    if session.node2_id != node.id:
        # 只有**接收方**需要这两版：发送方自己知道自己签的是什么。
        # 第三方（包括发送方之外的人）不该拿到这条映射 —— 它把"谁的信封
        # 用哪把密钥保护"这件事暴露给无关节点。
        return _error('只有该会话的接收方需要取这两版密钥', 403,
                      error_code=C.ERR_NOT_SESSION_PARTY)

    sender = session.node1
    sender_falcon_public_key = ''
    if session.falcon_key_id and session.falcon_key_version:
        try:
            signing_key = require_key_version(
                sender, 'FALCON', session.falcon_key_id, session.falcon_key_version,
                for_new_work=False,   # 验收旧信封：准 RETIRED 也要能查出来（解旧信封那条路）
            )
        except C.ContractError as exc:
            # 会话列里记的那一版查不到（被删/被改）——如实报，不换成"当前版本"。
            return _error(
                f'会话记录的发送方 Falcon 版本查不到：{exc.message}',
                C.ERROR_HTTP_STATUS.get(exc.code, 400), error_code=exc.code,
            )
        sender_falcon_public_key = _public_key_hex(signing_key)

    return _ok({
        'sessionId': session.session_id,
        'status': session.status,
        'senderNodeId': sender.node_id if sender else '',
        'senderNodeName': sender.name if sender else '',
        # 保护算法（库内拼写，如 kyber_kem / gm_sm2）—— 接收方要拿它去拼 keyRef
        # （浏览器密钥库的引用是 `node/{id}/{规范算法名}/{keyId}/{版本}`）。
        # 不给的话页面只能从信封的 wrapping_algorithm 反推，两份映射必然漂移。
        'protectionAlgorithm': session.session_type,
        'recipientKeyId': session.recipient_key_id,
        'recipientKeyVersion': session.recipient_key_version,
        'falconKeyId': session.falcon_key_id,
        'falconKeyVersion': session.falcon_key_version,
        # 发送方那一版 Falcon 公钥（小写 hex），接收方拿它与本机参与验签。
        'falconPublicKey': sender_falcon_public_key,
        # 会话 ID：接收方算 HMAC proof 要原样用它做消息（不是从 URL 再解析一遍）。
        'proofMessage': session.session_id,
    })


def _public_key_hex(record) -> str:
    """公钥的比对形式（小写 hex）；转不动返回空串。与 node_self_views 同规则。"""
    import base64 as _b64
    import binascii

    raw = str(getattr(record, 'public_key', '') or '').strip()
    if not raw:
        return ''
    if _HEX_RE.fullmatch(raw):
        return raw.lower()
    try:
        return _b64.b64decode(raw, validate=True).hex()
    except (binascii.Error, ValueError):
        logger.warning('节点 %s 的 %s 公钥既不是 hex 也不是 base64，无法给出比对形式',
                       getattr(record, 'node_id', '?'), getattr(record, 'algorithm', '?'))
        return ''


def _advance_session(session, target, *, allow_from=()):
    """按 `SESSION_TRANSITIONS` 把会话推到 `target`；非法边抛 ContractError。

    返回 True 表示真的推进了；False 表示**已经在这个状态**（幂等重试）。

    ⚠️ "已经走过去了"（比如 `key_recovered` 的会话再收到"验签通过"）**不能**
       交给本函数处理：那不是一条合法边，本函数会拒。回执端点自己判
       "状态已越过这一步"并如实回 ok —— 中间状态只增不减。把那条判断
       留在调用方是有意的：状态机表（`SESSION_TRANSITIONS`）是唯一契约，
       别在这里另造一个"状态次序"的隐式概念，那正是分散判断会漏掉的东西。

    非法边给 `ERR_SESSION_STATE_INVALID`（不是笼统的 400）：
    "先解封后验签"与"参数写错"是两回事，页面据此显示"这一步的顺序不对"。
    """
    current = session.status
    if current == target:
        return False
    if current not in allow_from:
        raise C.ContractError(
            f'会话当前状态是 {current}，不能推进到 {target}'
            f'（允许的前置状态：{"、".join(allow_from) or "无"}）',
            code=C.ERR_SESSION_STATE_INVALID,
        )
    if not C.session_transition_allowed(current, target):
        # 兜底：allow_from 与状态机表不一致时以表为准 —— 表是唯一契约。
        raise C.ContractError(
            f'非法状态流转：{current} → {target}', code=C.ERR_SESSION_STATE_INVALID,
        )
    session.status = target
    session.save(update_fields=['status'])
    return True


@csrf_exempt
@require_http_methods(['POST'])
@require_kms_user
def node_envelope_verify(request, envelope_pk, identity):
    """接收方回报"我在本机验签通过"（KMS-011，§6.5 的第 ① 条）。

    请求体可空（`{}`）—— 版本引用不在这里传，服务端从**会话行**读
    （那才是分发时的事实记录）；信封靠 URL 里的 ID 定位。

    <h2>服务端验的与节点验的不是同一件事</h2>
    节点在本机用**发送方那一版 Falcon 公钥**验签（`node_session_versions`
    给出公钥），这一步只有它能做 —— 私钥在它那儿。本端点做的是：
      1. 该信封确实是发给它的；
      2. 服务端**自己再独立验一次**（用会话记录的发送方 Falcon 版本），
         验不过就拒（`SIGNATURE_INVALID`）—— 服务端能算的，绝不只信回执；
      3. 验过了才按状态机把会话推到 `recipient_verified`。

    第 2 步不是重复劳动：`verify_node_envelope` 与服务端验签用的是同一份
    规范实现，它能抓住"接收方拿错公钥却回报成功"与"信封在传输中被改"。
    真正的信任锚仍然是后面双方 proof 的相互匹配。

    ⚠️ 幂等：会话已是 `key_recovered`/`established` 时再回报"验签通过"，
       如实回 ok（这一步确实发生过），**不回退状态** —— 中间状态只增不减。
    """
    node = _find_node(identity)
    if node is None:
        return _error('当前账号未关联任何节点', 403)

    try:
        envelope_pk = _as_envelope_pk(envelope_pk)
        record = _resolve_envelope_for(node, envelope_pk)
    except C.ContractError as exc:
        return _error(exc.message, C.ERROR_HTTP_STATUS.get(exc.code, 400), error_code=exc.code)

    envelope = _envelope_payload(record)
    if envelope is None:
        return _error('该信封的内容无法解析（不是合法 JSON 对象）',
                      error_code=C.ERR_ENVELOPE_TAMPERED)
    signature = str(envelope.get('signature') or '').strip()
    if not signature:
        # 历史信封（KMS-009 之前签发的）没有签名 —— 拒，而不是"放行并记一笔"。
        # 回执的语义是"验签通过"，没有签名就没有可验的东西；
        # 声称验过等于把"没有签名"当成"签名有效"。
        return _error('该信封没有签名（历史数据），无法回报"验签通过"',
                      error_code=C.ERR_SIGNATURE_REQUIRED)

    session = _session_of_batch(record.pool_id, node)
    if session is None:
        return _error(f'批次 {record.pool_id} 没有对应到发给当前节点的会话',
                      404, error_code=C.ERR_SESSION_NOT_FOUND)

    if not session.falcon_key_id or not session.falcon_key_version:
        return _error('会话没有记录发送方的 Falcon 版本（历史会话），无法验收',
                      409, error_code=C.ERR_KEY_VERSION_MISMATCH)

    sender = session.node1
    try:
        signing_key = require_key_version(
            sender, 'FALCON', session.falcon_key_id, session.falcon_key_version,
            for_new_work=False,
        )
    except C.ContractError as exc:
        return _error(exc.message, C.ERROR_HTTP_STATUS.get(exc.code, 400), error_code=exc.code)

    # 摘要自洽（与 KMS-010 分发口同一顺序：先摘要、后验签 —— 序列化漂移
    # 与伪造必须分开报）。重算要用**库里的原文**，见 `_load_envelope_json`。
    canonical = C.canonical_algorithm(
        session.session_type or envelope.get('wrapping_algorithm') or ''
    )
    if canonical not in C.PROTECTION_ALGORITHMS:
        # 会话类型认不出（历史值）——按信封自己的 wrapping_algorithm 再试一次；
        # 仍然认不出就拒：没有保护算法就无法重建内层口径，摘要无从重算。
        return _error(
            f'会话/信封的保护算法认不出：{session.session_type!r}',
            error_code=C.ERR_ALGORITHM_NOT_ALLOWED,
        )
    expected_digest = ciphertext_digest(_canonical_inner_json(envelope, canonical))
    declared_digest = str(envelope.get('ciphertext_digest') or '').strip()
    if declared_digest != expected_digest:
        return _error(
            '信封的密文摘要与服务端重算的不一致：内容在落库之后被改过，'
            '或两侧的规范化序列化口径漂移了',
            error_code=C.ERR_ENVELOPE_TAMPERED,
        )

    if not verify_node_envelope(envelope, signature, signing_key.public_key):
        return _error(
            f'服务端独立验签未通过：签名与发送节点 {sender.node_id} 的 FALCON 密钥 '
            f'{signing_key.key_id} v{signing_key.key_version} 不匹配，或信封内容被改动过',
            C.ERROR_HTTP_STATUS[C.ERR_SIGNATURE_INVALID], error_code=C.ERR_SIGNATURE_INVALID,
        )

    try:
        # 允许的前置：initiated（正常推进）。已经是 recipient_verified 时
        # 走下面的幂等分支；已经越过这一步（key_recovered/established）时
        # **不回退** —— `_advance_session` 会拒这条边，所以单独判一次。
        advanced = _advance_session(
            session, C.SESSION_RECIPIENT_VERIFIED,
            allow_from=(C.SESSION_INITIATED,),
        )
    except C.ContractError as exc:
        if exc.code != C.ERR_SESSION_STATE_INVALID or (
            session.status not in (C.SESSION_RECIPIENT_VERIFIED, C.SESSION_KEY_RECOVERED,
                                   C.SESSION_ESTABLISHED)
        ):
            return _error(exc.message, C.ERROR_HTTP_STATUS.get(exc.code, 400),
                          error_code=exc.code)
        # 已经在这条线的后面了：如实回 ok，不动状态（中间状态只增不减）。
        advanced = False

    # KMS-014：验签通过 → 链上留痕 ENVELOPE_VERIFIED。
    # ⚠️ 只在**真的推进了**这一步时发（advanced=True）—— 重复回执不重复上链。
    #    与 KMS-007 对回收的口径一致：同一次动作在链上留多条记录，
    #    "验签过几次"就没有可信答案了。
    chain_tx = record_session_chain_event('ENVELOPE_VERIFIED', session) if advanced else None
    if advanced:
        # KMS-014：证据轨迹（监管页五态的数据源；关闭后仍要读得出走没走过这步）。
        session.record_evidence('verified', tx=chain_tx or '')
        session.save(update_fields=['lifecycle_evidence'])

    return _ok({
        'envelopeId': record.pk,
        'sessionId': session.session_id,
        'status': session.status,
        'advanced': advanced,
        'falconKeyId': signing_key.key_id,
        'falconKeyVersion': signing_key.key_version,
        # 与 KEY_UPDATED / KEY_DISTRIBUTED 同一口径：回哈希而不是布尔值；
        # 拿不到时是空串，页面据此如实说"已验签，但存证未成功"。
        'chainHash': chain_tx or '',
    }, msg='验签通过（服务端已独立复核）' if advanced else '这条会话已越过验签这一步，本次未做改动')


@csrf_exempt
@require_http_methods(['POST'])
@require_kms_user
def node_envelope_recover(request, envelope_pk, identity):
    """接收方回报"我在本机解封成功"（KMS-011，§6.5 的第 ② 条）。

    ⚠️ **服务端无法独立验证这一步**：解封用的私钥只在接收节点本地，
    服务端也没有 K（那是不变量）。所以这里接受的是**节点的声明** ——
    与 confirm 的 proof 同性质：单方声明不构成安全属性，真正的锚是
    后面双方 proof 匹配。库里的 `key_recovered` 状态是**审计事实**
    （"它回报说解封了"），不是信任锚。

    ⚠️ 顺序由状态机强制：只有 `recipient_verified`（或已到
       `key_recovered`，幂等）才能推进。`initiated → key_recovered`
       不是合法边 —— 先解封后验签的回报会被 `SESSION_STATE_INVALID` 拒掉，
       这正是不许跳过证据的落点。
    """
    node = _find_node(identity)
    if node is None:
        return _error('当前账号未关联任何节点', 403)

    try:
        envelope_pk = _as_envelope_pk(envelope_pk)
        record = _resolve_envelope_for(node, envelope_pk)
    except C.ContractError as exc:
        return _error(exc.message, C.ERROR_HTTP_STATUS.get(exc.code, 400), error_code=exc.code)

    session = _session_of_batch(record.pool_id, node)
    if session is None:
        return _error(f'批次 {record.pool_id} 没有对应到发给当前节点的会话',
                      404, error_code=C.ERR_SESSION_NOT_FOUND)

    try:
        advanced = _advance_session(
            session, C.SESSION_KEY_RECOVERED,
            allow_from=(C.SESSION_RECIPIENT_VERIFIED,),
        )
    except C.ContractError as exc:
        if exc.code != C.ERR_SESSION_STATE_INVALID or (
            session.status not in (C.SESSION_KEY_RECOVERED, C.SESSION_ESTABLISHED)
        ):
            # `initiated`（没先验签就解封）落到这里 —— 这正是"不许跳过证据"
            # 的拒绝，如实报 SESSION_STATE_INVALID 并说明该先做什么。
            return _error(exc.message, C.ERROR_HTTP_STATUS.get(exc.code, 400),
                          error_code=exc.code)
        advanced = False

    if advanced:
        # KMS-014：证据轨迹记下这一步（**无链上事件** —— 解封是节点单方声明、
        # 服务端无法独立复核，见 models.SessionKey.lifecycle_evidence 的说明；
        # tx 留空，不假装它上过链）。
        session.record_evidence('recovered')
        session.save(update_fields=['lifecycle_evidence'])

    # KMS-012：双方确认可以**先于**这一步提交（发起方分发完就能确认、
    # 接收方也可以先交证明再回来解封）。那两笔确认一直在库里等着 ——
    # 这里补一次提升机会，让"证据齐了"立刻兑现，而不是要用户再点一次确认。
    #
    # ⚠️ 只在这里补，不在 verify 里补：合法的建立路径是
    #    `key_recovered → established`，而 verify → recipient_verified 时
    #    状态机本来就还不允许（也**不该**允许 —— 那会让"没解封也建立"成真）。
    establish_state = 'waiting'
    establish_tx = None
    try:
        establish_state, _, establish_tx = _maybe_establish(session)
    except Exception as exc:  # noqa: BLE001
        # 补一次提升是**尽力而为**：它失败了不该让"解封已登记"变成一次 500。
        logger.warning('会话 %s 解封后补提升失败（不影响解封登记）: %s', session.session_id, exc)

    return _ok({
        'envelopeId': record.pk,
        'sessionId': session.session_id,
        'status': session.status,
        'advanced': advanced,
        # 补提升的结果如实回报：established 表示双方确认早就齐了、这一刻兑现。
        'established': establish_state == 'established',
        # KMS-014：若这次补提升真的建立了会话，把它的链上哈希一并回传
        # （申请方据此知道"建立"这一步的存证情况）；未建立时是空串。
        'chainHash': establish_tx or '',
        # 口径提示（给页面看）：这一步是节点的声明，安全性来自后面的双方 proof。
        'note': '服务端不持有会话密钥，本状态依据的是节点回报；真正的建立条件是双方 proof 一致',
    }, msg='解封成功已登记' if advanced else '这条会话此前已解封，本次未做改动')


def _session_of_batch(batch_id: str, node: Node):
    """按批次号找"发给这个节点"的会话（`{batch_id}-n{node.id}`）。

    ⚠️ 会话 ID 由 `distribution_service.create_initiated_sessions` 按
       `f'{batch_id}-n{target.id}'` 生成，pk 是**主键**（不是业务编号）。
       这里与那条命名规则**耦合**；一旦规则改动，两边要一起改。
       （会话行上同时记了各自那条信封的批次关联，反查也可行，但那需要
       再多一列；命名规则是本仓库既有约定，先用它，并把耦合写在这里。）
    """
    return SessionKey.objects.filter(session_id=f'{batch_id}-n{node.id}').first()


# ---------------------------------------------------------------------------
# KMS-014：三个会话类事件的链上存证（计划 §6 第 329 行、§7 阶段 6）
# ---------------------------------------------------------------------------
# ENVELOPE_VERIFIED / SESSION_ESTABLISHED / SESSION_CLOSED 是计划要求的
# 七个链上事件里的后三个（前四个由 KMS-006/007/008 接通）。它们的落点就是
# 本模块已经建成的三处：verify 端点、`_maybe_establish`、close 端点。
#
# ⚠️ 顺序是硬约束：Java 侧的入口白名单（`InternalLifecycleController.chainEvent`）
#    必须先认得这三个事件，PQKDS 侧发才有意义 —— 顺序反了的话
#    `record_chain_event` 只返回 None，表现为"存证没成功"，而白名单文案
#    只在容器日志里能看到。
_SESSION_CHAIN_EVENT_TYPES = frozenset({
    'ENVELOPE_VERIFIED', 'SESSION_ESTABLISHED', 'SESSION_CLOSED',
})


def record_session_chain_event(event_type: str, session: SessionKey) -> Optional[str]:
    """把一次会话类事件记到链上；任何失败只记日志、返回 None（旁路增强）。

    三个字段的口径与 KEY_DISTRIBUTED（KMS-008）**逐字一致** —— 链上回读时
    "谁的哪把钥匙"必须只有一个答案：

      * `keyId`   —— **被用于建立会话的那把长期密钥**（接收方那一行
        `NodeLongTermKey`）的整数主键。Java 接口只收整数，业务字符串
        key_id 会被解析失败吞成"存证未成功"。
      * `nodeId`  —— 该密钥的**归属节点**（接收节点）。链上记录一旦在这里
        分叉（比如会话事件记发送方），回读时就无法回答"谁受影响"。
      * `materialHash` —— 那一行的 `public_key_hash`（存储形式公钥的
        sha256）。链上只需要能核验"是不是同一份材料"，不需要材料本身。

    ⚠️ 事务边界：调用点必须在**状态推进已提交之后**（本模块几个端点的
       推进各自独立 save），与 KMS-006/007 同一条纪律 —— 存证失败不改
       会话结论；把网络调用包进事务还会一直占着连接。
    ⚠️ 锚定取不到（历史会话没有两版引用、或登记行已不在）时**不上链**，
       记一条 warning：宁可留一个可见的审计缺口，也不要编一个 keyId 上链 ——
       链上的记录写错就撤不回来了。
    """
    if event_type not in _SESSION_CHAIN_EVENT_TYPES:
        # 防御性：这个 helper 只服务会话类事件。写错事件名混进来会让
        # "哪些事件由这里产生"变得不可读（那些事件各有自己的落点与白名单）。
        logger.warning('record_session_chain_event 收到非会话类事件 %r，跳过', event_type)
        return None

    algorithm = C.canonical_algorithm(session.session_type or '')
    key_row = None
    if session.recipient_key_id and session.recipient_key_version:
        # 接收方 = session.node2（`create_initiated_sessions` 建行时
        # node1=发送方、node2=接收方，见 distribution_service 的注释）。
        key_row = NodeLongTermKey.objects.filter(
            node=session.node2,
            algorithm=algorithm,
            key_id=session.recipient_key_id,
            key_version=session.recipient_key_version,
        ).first()
    if key_row is None:
        logger.warning(
            '会话 %s（%s）：找不到接收方长期密钥行（alg=%s key_id=%s v%s），'
            '本次**不上链** —— 宁可留一个可见的审计缺口，也不编一个 keyId',
            session.session_id, event_type, algorithm or '(认不出)',
            session.recipient_key_id, session.recipient_key_version,
        )
        return None

    try:
        tx = record_chain_event(
            event_type,
            int(key_row.pk),
            int(key_row.key_version or 0),
            session.node2.node_id,
            str(key_row.public_key_hash or ''),
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning('会话 %s 的 %s 链上存证失败: %s', session.session_id, event_type, exc)
        return None
    if tx:
        logger.info('会话 %s 已上链存证: %s keyId=%s tx=%s',
                    session.session_id, event_type, key_row.pk, tx)
    return tx


def _confirmation_state(session):
    """双方的确认状态：`(count, proofs_equal)`。

    两个数分开返回而不是合并成一个布尔：调用方对"只有一方确认"与
    "两方确认但证明不一致"的**文案与处置完全不同**（前者等对方，
    后者是真问题），合并后必然要在别处重新拆开 —— 那正是分散判断的开始。
    """
    confirmations = list(SessionKeyConfirmation.objects.filter(session=session))
    if len(confirmations) < 2:
        return len(confirmations), None
    return len(confirmations), len({c.proof for c in confirmations}) == 1


def _maybe_establish(session):
    """双方证明已齐且一致时，按状态机把会话提升为 `established`。

    返回 `(state, detail, chain_tx)`，state ∈ {'established', 'waiting',
    'mismatch', 'state'}：
      * `waiting`   —— 只有一方确认（或还没有）；
      * `mismatch`  —— 两方确认了但 proof 不同（两边持有的 K 不是同一把）；
      * `state`     —— 证明齐了，但会话还没走到 `key_recovered`（验签/解封的回执
                       还没齐）—— 状态机不允许跳过，如实拒绝提升；
      * `established` —— 提升成功（或本来就已建立）。

    `chain_tx` 是 SESSION_ESTABLISHED 的链上交易哈希（KMS-014；只有**本次
    真的提升了**才有值，其余情况为 None）—— 调用方把它如实回给页面。

    ⚠️ 后三种都**不是错误**：confirm 本身是一次合法的提交，只是"建立"这个
       动作还不到时候。调用方按各自上下文给文案，不要把 'state' 报成 500/400 ——
       用户没做错什么，缺的是另一个端点上的两步回执。

    ⚠️ 提升只走 `SESSION_TRANSITIONS` 里 `key_recovered → established` 这一条边
       （KMS-012 的核心）：`initiated → established` 的直跳在这里被拒，
       不再依赖"顺序对了就不会发生"。
    """
    count, proofs_equal = _confirmation_state(session)
    if count < 2:
        return 'waiting', f'已确认 {count}/2', None
    if not proofs_equal:
        logger.warning(
            '会话 %s 双方确认证明不一致（各自持有的 K 不同）', session.session_id,
        )
        return 'mismatch', '双方证明不一致', None
    if session.status == C.SESSION_ESTABLISHED:
        # "早已建立"不重复上链：那一条在**第一次**建立时已经发过。
        # 无条件重发会让链上出现多条 SESSION_ESTABLISHED，
        # "这条会话建立过几次"就没有可信答案了（与 KMS-007 回收同口径）。
        return 'established', '早已建立', None
    try:
        _advance_session(session, C.SESSION_ESTABLISHED,
                         allow_from=(C.SESSION_KEY_RECOVERED,))
    except C.ContractError as exc:
        # 状态机还没走到 key_recovered：证明齐了也不能建。
        logger.info('会话 %s 双方确认已齐，但状态机不允许提升：%s', session.session_id, exc.message)
        return 'state', exc.message, None
    logger.info('会话 %s 双方确认一致 → established', session.session_id)
    # KMS-014：建立 → 链上留痕 + 证据轨迹。状态推进已提交（上面 save 完），
    # 存证在事务之外、失败只记日志（旁路增强）。
    chain_tx = record_session_chain_event('SESSION_ESTABLISHED', session)
    session.record_evidence('established', tx=chain_tx or '')
    session.save(update_fields=['lifecycle_evidence'])
    return 'established', '', chain_tx


@csrf_exempt
@require_http_methods(['POST'])
@require_kms_user
def node_session_close(request, session_id, identity):
    """关闭会话（KMS-012 / §16.4）。**终态，不可恢复**。

    双方都可以关闭：发起方放弃一次没建立起来的会话、或任一方结束通信，
    都是正常动作。关闭后要再通信只能**重新分发** —— 这条口径必须写进
    响应与页面文案：`SESSION_CLOSED` 在 `SESSION_TRANSITIONS` 里没有出边。

    ⚠️ 会话密钥的**本地副本**由调用方（页面）在关闭成功后自行删除 ——
       服务端不知道谁的本机存了什么，替它删是做不到的；能保证的是
       这条会话此后不接受任何确认或状态变更。
    """
    node = _find_node(identity)
    if node is None:
        return _error('当前账号未关联任何节点', 403)

    session = SessionKey.objects.filter(session_id=session_id).first()
    if session is None:
        return _error(f'会话不存在：{session_id}', 404, error_code=C.ERR_SESSION_NOT_FOUND)
    if node.id not in (session.node1_id, session.node2_id):
        return _error('你不是这条会话的一方，无权关闭', 403, error_code=C.ERR_NOT_SESSION_PARTY)

    if session.status in C.SESSION_TERMINAL_STATUSES:
        # 已经是终态（关闭/过期/撤销）—— 幂等回 ok 但**不改任何字段**：
        # 重试一次关闭不该失败，但"它是什么时候因为什么进终态的"不能被改写。
        return _ok({
            'sessionId': session.session_id,
            'status': session.status,
            'advanced': False,
        }, msg=f'会话已处于终态（{session.status}），本次未做改动')

    try:
        advanced = _advance_session(
            session, C.SESSION_CLOSED,
            allow_from=(C.SESSION_INITIATED, C.SESSION_RECIPIENT_VERIFIED,
                        C.SESSION_KEY_RECOVERED, C.SESSION_ESTABLISHED),
        )
    except C.ContractError as exc:
        return _error(exc.message, C.ERROR_HTTP_STATUS.get(exc.code, 400), error_code=exc.code)

    # KMS-014：关闭是终态事件 → 链上留痕 SESSION_CLOSED。
    # 上面的终态幂等分支与这段的 `advanced=False` 都不上链 ——
    # 重复关闭不重复写，"关闭过几次"在链上只有一个可信答案。
    chain_tx = record_session_chain_event('SESSION_CLOSED', session) if advanced else None
    if advanced:
        # 证据轨迹：关闭后 status 只剩 closed，"走到过哪一步"靠这条轨迹回答
        # —— 这正是监管页五态存在的理由。
        session.record_evidence('closed', tx=chain_tx or '')
        session.save(update_fields=['lifecycle_evidence'])

    return _ok({
        'sessionId': session.session_id,
        'status': session.status,
        'advanced': advanced,
        'chainHash': chain_tx or '',
        'note': '关闭是终态：该会话不再接受确认或状态变更；要重新通信请重新分发',
    }, msg='会话已关闭（终态）')


@csrf_exempt
@require_http_methods(['POST'])
@require_kms_user
def node_session_confirm(request, session_id, identity):
    """提交"我已恢复会话密钥"的证明；双方一致**且状态机允许**时才提升为 established。

    请求体：`{"proof": "<HMAC-SHA256(K, session_id) 的十六进制>"}`

    流程（KMS-012 起）：
      1. 终态（closed/expired/revoked）直接拒 —— 不收"死后确认"；
      2. 校验该节点确实是这条会话的一方（否则第三个人也能来"确认"）；
      3. 记录（或更新）本节点的证明；
      4. 双方证明**都已提交且相等**时，按 `SESSION_TRANSITIONS` 尝试提升 ——
         唯一能到 established 的边是 `key_recovered → established`。

    ⚠️ 顺序独立、但**提升不跳过证据**：证明可以随时提交（revoke 之后、
       解封之前都行），可"建立"必须等验签与解封两件回执都到齐。
       KMS-011 之前这里直接写 `status='established'` ——
       `initiated → established` 的直跳靠"顺序对了就不会发生"堵着；
       现在由状态机表拒绝，响应里如实给出 `blockedBy`。

    ⚠️ 证明不相等时**不提升、也不报错**（`mismatch`）：那是真问题
       （两边持有的 K 不同），但它既可能是封装算法搞混，也可能是伪造 ——
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
        return _error(f'会话不存在：{session_id}', 404, error_code=C.ERR_SESSION_NOT_FOUND)

    # 终态：不再接受任何确认。放在身份校验**之前**还是之后都有道理 ——
    # 选之前，是因为"这条会话已经死了"对任何调用方都是同一个答复，
    # 而先答 403 会把注意力引向"我是不是没权限"。
    if session.status in C.SESSION_TERMINAL_STATUSES:
        return _error(
            f'会话已处于终态（{session.status}），不再接受确认',
            C.ERROR_HTTP_STATUS.get(C.ERR_SESSION_TERMINAL, 409),
            error_code=C.ERR_SESSION_TERMINAL,
        )

    # 只有会话双方能确认。少了这一条，任何登录用户都能对别人的会话"确认"，
    # 而它提交的证明必然与真实一方对不上 —— 于是表现为"双方证明不一致"，
    # 把一次越权伪装成一次故障。所以先挡在这里。
    if node.id not in (session.node1_id, session.node2_id):
        return _error('你不是这条会话的一方，无权确认', 403, error_code=C.ERR_NOT_SESSION_PARTY)

    SessionKeyConfirmation.objects.update_or_create(
        session=session,
        node=node,
        defaults={
            'proof': proof,
            'key_recovered': True,
            'confirmed_at': timezone.now(),
        },
    )

    state, detail, establish_tx = _maybe_establish(session)
    confirmed_by = _confirmation_state(session)[0]

    if state == 'established':
        return _ok({
            'sessionId': session_id,
            'status': session.status,
            'confirmedBy': confirmed_by,
            'established': True,
            # KMS-014：本次真的建立时的链上哈希（"早已建立"与"证据不齐"时是空串 --
            # 那两种情况没有可回的新哈希，页面据此如实显示）。
            'chainHash': establish_tx or '',
        }, msg='双方确认一致，会话已建立' if detail != '早已建立' else '会话已建立（无需重复确认）')
    if state == 'mismatch':
        return _ok({
            'sessionId': session_id,
            'status': session.status,
            'confirmedBy': confirmed_by,
            'established': False,
            'reason': C.ERR_PROOF_MISMATCH,
        }, msg='双方确认已提交但**证明不一致**：两边解出的会话密钥不是同一把，请检查该会话的信封与算法')
    if state == 'state':
        # 证明齐了、也一致，但证据链不完整（验签/解封的回执没到）——
        # **不提升**，把卡在哪一步如实说出来（`blockedBy` 可编程判断）。
        return _ok({
            'sessionId': session_id,
            'status': session.status,
            'confirmedBy': confirmed_by,
            'established': False,
            'blockedBy': C.ERR_SESSION_STATE_INVALID,
        }, msg=f'确认已记录，但暂不能建立：{detail}（需要接收方先完成验签与解封）')

    return _ok({
        'sessionId': session_id,
        'status': session.status,
        'confirmedBy': confirmed_by,
        'established': False,
    }, msg='已记录你的确认；等待会话另一方确认')