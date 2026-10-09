# -*- coding: utf-8 -*-
"""节点自助接口（阶段 2）。

    GET  /node-self/          我在 KMS 里对应的节点（含初始化状态）
    GET  /node-self/keys/     本节点已登记的长期密钥（含历史版本，供页面与服务端对账）
    POST /node-self/keys/     登记一个算法的公钥（私钥永不上行）
    POST /node-self/keys/revoke/  回收指定的一把长期密钥，并处理它的影响面
    POST /node-self/init/     节点首次登录后初始化四套基础密钥

为什么是"自助"
--------------
文档 §2.1：系统的业务使用主体是**区块链节点**。节点由管理员创建后获得登录资格，
**首次登录时**完成密码学初始化（§3.1）。所以"初始化"这个动作的发起者是节点自己，
不是管理员 —— 管理员建节点时只建账号，不生成密钥。

身份来源
--------
`user_id` **一律取自令牌自省**（复用 `user_distribution_views.require_kms_user`），
绝不从请求参数取。否则构造一个带 `?node_id=` 的请求就能替任意节点触发初始化。

节点定位靠 `Node.sys_user_id`（阶段 2 新增的一一映射字段），不是靠用户名 ——
用户名只是登录入口，且 `node_id` 超过 30 字符时会被截断+哈希（见
`node_account_service._node_user_name`），拿它反查不可靠。
"""

from __future__ import annotations

import base64
import binascii
import json
import logging
import re

from django.db import IntegrityError, transaction
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from . import api_contract as C
from .distribution_service import authorized_node_ids, create_node_distribution
from .key_revocation_service import revoke_long_term_key
from .models import Node, NodeLongTermKey
from .node_service import NodeService
from .node_permission import (
    CAP_DISTRIBUTE,
    CAP_GENERATE,
    LEVEL_LABELS,
    NodePermissionError,
    capabilities_of,
    normalize_level,
    require_capability,
)
from .user_distribution_views import require_kms_user
from .kms_service_client import record_chain_event

logger = logging.getLogger(__name__)

#: 状态码 → 中文。**只此一份**：`api_contract.KEY_STATUS_CHOICES` 是冻结契约里的状态表，
#: 前端另抄一份就会漂移，而漂移只表现为文案对不上，不会有任何一处报错。
_STATUS_LABELS = dict(C.KEY_STATUS_CHOICES)

_HEX_RE = re.compile(r'[0-9a-fA-F]+')

#: 一次能选/能提交的节点数上限。名录的 `maxSelectable` 与授权申请的批量提交
#: **共用这一处** —— 两处各写一个数必然漂移，而漂移的表现是"页面让你选 10 个、
#: 提交却报超过上限"，看起来像服务端算错了。
NODE_DIRECTORY_MAX_SELECT = 10

#: 一次上传的预分配保护包条数上限。页面按它分批（每批 50）——
#: 上限存在的理由是**单次请求的验签是逐条同步做的**：一批大到几千条会让
#: 响应时间不可控，而分批上传是渐进填池的正常做法（补传成本很低）。
MAX_POOL_ITEMS_PER_BATCH = 200

#: 池号形状：`pool_<16~32 位十六进制>`。由**节点侧**生成（它进签名），
#: 服务端只校验形状 —— 形状不对时早拒，别让一条永远进不了池子的批次白生成。
_POOL_ID_RE = re.compile(r'^pool_[0-9a-fA-F]{16,32}$')

#: 交付批次号形状：与 `envelope-signing.newBatchId` 逐字符同形
#: （`dist-<yyyyMMddHHmmss>-<8位hex>`）。服务端只有这一个来源，前端不再自己拼。
_DIST_BATCH_RE = re.compile(r'^dist-\d{14}-[0-9a-fA-F]{8}$')

_SHA256_RE = re.compile(r'^[0-9a-f]{64}$')

#: 预分配资源的有效期上界（小时）。任务书 §20 的示例是 24h；给到 720h（30 天）
#: 与密钥池页的既有上限一致 —— 更长的"预分配"已经不是短期会话密钥了。
_MAX_POOL_EXPIRY_HOURS = 720


def _as_future_expiry(raw):
    """把请求里的有效期解析成**未来**的时间点（`USE_TZ=False`，见 models）。

    收绝对的 ISO 时间串（与 `distributions` 端点同一形状）：签名要覆盖它，
    所以必须是调用方在签名前就定下的值。这里只校验"是个未来时间、且不超过上界"。
    """
    from datetime import datetime as _dt, timedelta as _td
    if raw in (None, ''):
        raise ValueError('缺少 expiresAt（有效期，ISO 时间串）')
    text = str(raw).strip()
    parsed = None
    try:
        parsed = _dt.fromisoformat(text.replace('Z', '+00:00'))
    except ValueError:
        raise ValueError(f'expiresAt 不是合法的 ISO 时间串：{text!r}')
    if timezone.is_aware(parsed):
        # 本仓 `USE_TZ=False`（见 models 顶部说明）：带时区的时间与 naive 的
        # `timezone.now()` 相比会直接抛错，所以统一转成 naive 本地时间。
        parsed = timezone.make_naive(parsed)
    now = timezone.now()
    if parsed <= now:
        raise ValueError('expiresAt 必须是将来的时间（这是"短期"会话密钥资源的有效期）')
    if parsed > now + _td(hours=_MAX_POOL_EXPIRY_HOURS):
        raise ValueError(f'expiresAt 超出上界（最多 {_MAX_POOL_EXPIRY_HOURS} 小时）')
    return parsed


def _public_key_hex(record) -> str:
    """公钥的**比对形式**：一律小写 hex，与节点本地密钥库里的记录同形。

    为什么要转换而不原样下发
    ------------------------
    存储形式按算法分两种（见 `node_service.store_node_public_key`：Kyber 存
    **base64**，其余存 hex），而节点本地一律是 hex。生成页要拿服务端这把与
    本机那把**逐字节**比对，若原样下发存储形式，**Kyber 会恒定"对不上"**——
    它的表现是"服务端记的不是你本机那把"，看着像密钥被换过或本机被人动过，
    实际只是编码不同。这类假警报比不报警更糟：用户会去重新初始化。

    转不动时返回空串（**不猜**）：页面据此显示"服务端记录无法比对"，
    那才是实情。返回一段看起来像公钥的东西会被拿去比对，且永远不相等。
    """
    raw = str(record.public_key or '').strip()
    if not raw:
        return ''
    if record.algorithm != 'KYBER':
        return raw.lower()
    # 先认 hex 再认 base64，顺序不能反：hex 的字母表是 base64 的子集，
    # 一段 hex 串往往也能被 base64 解码（得到的是另一串字节，且不报错）。
    if _HEX_RE.fullmatch(raw):
        return raw.lower()
    try:
        return base64.b64decode(raw, validate=True).hex()
    except (binascii.Error, ValueError):
        logger.warning('节点 %s 的 Kyber 公钥既不是 hex 也不是 base64，无法比对', record.node_id)
        return ''


def _ok(data=None, msg='操作成功'):
    return JsonResponse({'code': 200, 'msg': msg, 'data': data})


def _error(msg, code=400, error_code=None):
    """本命名空间的错误响应：HTTP 恒 200，业务码在 `code`。

    `error_code` 是可编程的 `api_contract.ERR_*`（如 `KEY_VERSION_MISMATCH`），
    放在 `data` 里。**不换约定** —— 把 `code` 改成字符串会静默破坏所有既有
    调用方对 `code === 200` 的判断（见 doc/kms-callsite-inventory.md §七）。
    "哪一种失败"必须可编程区分，所以按那份文档的兼容决定往 `data` 里**加**字段，
    而不是改 `code` 的类型。
    """
    return JsonResponse(
        {'code': code, 'msg': msg, 'data': {'error_code': error_code} if error_code else None},
        status=200,
    )


def _iso(value):
    """时间戳按 ISO 下发；空值一律 None（前端据此显示"—"而不是 1970）。"""
    return value.isoformat() if value else None


def _as_bool(value, field: str = 'rotate') -> bool:
    """严格布尔解析。**不做真值猜测**。

    只认 `True`/`False` 与 `'true'`/`'false'`/`'1'`/`'0'`（去空白、不分大小写）；
    字段缺省（None / ''）算 False。**出现但认不出**的值直接报错。

    为什么不容错：这个标志决定的是"生成新密钥"还是"更新同一把密钥"，
    两条路的落库完全不同。把认不出的值猜成 False，最坏的结果是一次更新
    被当成新登记（多出一个 keyId）；猜成 True，最坏的结果是**生产版本被
    换掉而请求返回成功**。两个方向都不该由服务端"猜"，要么调用方说清楚，
    要么拒绝 —— 拒绝的代价只是一次重试。
    """
    if value is None or value == '':
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and value in (0, 1):
        return bool(value)
    text = str(value).strip().lower()
    if text in ('true', '1'):
        return True
    if text in ('false', '0'):
        return False
    raise C.ContractError(
        f'{field} 应为布尔值（true/false），收到 {value!r}',
        code=C.ERR_INVALID_PARAMETER,
    )


#: 对外暴露的初始化状态。内部 status 有 registered/kyber_uploaded/... 多个中间态，
#: 但前端只需要知道"能不能用"，所以收敛成三态，避免把内部状态机泄漏到 UI。
def _public_status(node: Node) -> str:
    s = (node.status or '').lower()
    if s == 'active':
        return 'ACTIVE'
    if s in ('inactive', 'disabled'):
        return 'DISABLED'
    return 'PENDING_INIT'


def _node_payload(node: Node) -> dict:
    from .chain_backend import get_chain_backend, chain_write_state
    return {
        'nodeId': node.node_id,
        'chainBackend': get_chain_backend(),
        'chainWriteState': chain_write_state(),
        'name': node.name,
        'status': _public_status(node),
        'rawStatus': node.status,
        'permissionLevel': node.permission_level,
        # 阶段 7（§8.4）：把"这个等级能做什么"一并下发。
        # 前端据此隐藏/禁用入口，而不是自己维护一份等级表 ——
        # 两份表必然漂移，而漂移的表现是"界面能点、后端拒绝"。
        'capabilities': sorted(capabilities_of(node.permission_level)),
        'levelLabel': LEVEL_LABELS.get(normalize_level(node.permission_level), ''),
        'domainId': node.domain_id,
        'nodeType': node.node_type,
        'initializedAt': node.initialized_at.isoformat() if node.initialized_at else None,
        # §4.4 设备绑定：密钥绑在哪台设备上。
        # 前端拿它与**本机**的 deviceId 比对，判断"我是不是那台设备"——
        # 新设备登录时本地没有私钥，靠这个才能发现，否则界面看不出任何异常。
        'keyDeviceId': node.key_device_id or '',
        # 四套密钥各自是否就绪 —— 首次初始化引导页用它显示进度
        # ⚠️ KMS-015：Falcon 就绪判定读**规范列优先**（镜像列 `falcon_public_key`
        #    已停写；存量节点可能只有旧列，所以保留兜底）。
        #    与 `initialize_base_keys` 的就绪判定同一口径，两处别漂移。
        'keys': {
            'kyber': bool(node.kyber_public_key),
            'falcon': bool(node.falcon_sign_public_key or node.falcon_public_key),
            'sm2': bool(node.gm_public_key),
            'sscl': bool(node.sscl_public_key),
        },
    }


def _long_term_key_payload(k: NodeLongTermKey) -> dict:
    """一行长期密钥 → 页面需要的形状。逐行调用，公钥只换算一次。"""
    public_key = _public_key_hex(k)
    from .chain_backend import is_fabric_did, chain_write_state
    chain_binding = None
    if is_fabric_did():
        from .chain_binding_service import get_binding_status
        chain_binding = get_binding_status(k)
    return {
        'algorithm': k.algorithm,
        # 密钥可用与链上确认是两个事实；尚无配置时也不能显示成“上链成功”。
        'chainBinding': chain_binding,
        'chainWriteState': chain_write_state(),
        'keyId': k.key_id,
        'keyVersion': k.key_version,
        'status': k.status,
        # 状态文案与「这把还能干什么」都由服务端下发，取自 `api_contract`。
        # 前端**不另写一份**中文表与可用性判断：两份必然漂移，而漂移的表现是
        # "界面写着可用、实际已被取代"—— 用户据此做的判断全是错的，
        # 且没有任何一处会报错。
        'statusLabel': _STATUS_LABELS.get(k.status, k.status),
        'allowsNewWork': k.allows_new_work,
        'allowsUnwrap': k.allows_unwrap,
        'securityLevel': k.security_level,
        'deviceId': k.device_id,
        # 公钥是公开量，可以自由下发。给的是**比对形式**（小写 hex）：
        # 页面拿它与本机密钥库里的 `publicKey` 逐字节比，判断
        # "服务端记的那把，是不是我本机这把"。两者同形是这段比对能成立的
        # 前提，编码换算（Kyber 的 base64↔hex）收在 `_public_key_hex` 里。
        'publicKey': public_key,
        'publicKeyHash': k.public_key_hash,
        # 字节数而非字符串长度，也不是截断值：字节数才能与 Kyber 变体
        # （800/1184/1568）对上；截断后的串看起来仍像一把公钥、会被拿去比对，
        # 而它永远比不相等。要完整正文用上面那个字段。
        'publicKeyBytes': len(public_key) // 2,
        'legacy': k.legacy,
        'legacySource': k.legacy_source,
        'effectiveAt': _iso(k.effective_at),
        'expiresAt': _iso(k.expires_at),
        'revokedAt': _iso(k.revoked_at),
        'revokedReason': k.revoked_reason,
        'createdAt': _iso(k.create_datetime),
        'updatedAt': _iso(k.update_datetime),
    }


def _long_term_keys_payload(node: Node, limit: int = 200) -> list:
    """本节点长期密钥的全部行，新的在前 —— 供生成页做「本地 vs 服务端」对账。

    刻意**不过滤状态**：页面要能显示"上一版已被取代""这一版已回收"。
    只回 ACTIVE 的话，用户看到的是"我的密钥凭空少了一把"，而不是"它被换掉了"。

    排序用 `-id` 而不是 `-key_version`：跨 key_id 比版本号没有意义
    （旧密钥的 v3 可能比新密钥的 v1 更早登记），与 `node_key_registry.require_usable_key`
    同一口径。
    """
    rows = (NodeLongTermKey.objects
            .filter(node=node)
            .order_by('algorithm', '-id')[:limit])
    return [_long_term_key_payload(k) for k in rows]


def _find_node(identity) -> Node | None:
    """把登录身份映射到节点。取不到返回 None（由调用方给出明确错误）。"""
    user_id = identity.get('userId')
    if user_id is None:
        return None
    return Node.objects.filter(sys_user_id=user_id).first()


@csrf_exempt
@require_http_methods(['GET'])
@require_kms_user
def node_self(request, identity):
    """当前登录账号对应的节点及其初始化状态。"""
    node = _find_node(identity)
    if node is None:
        # 管理员账号（未映射到任何节点）访问这里会走到这一支。
        # 这不是错误状态，而是"这个账号不是节点"—— 由前端据此决定视图分流。
        return _ok({'mapped': False, 'node': None})
    return _ok({'mapped': True, 'node': _node_payload(node)})


@csrf_exempt
@require_http_methods(['GET', 'POST'])
@require_kms_user
def node_self_keys(request, identity):
    """本节点已登记的长期密钥：GET 取列表 / POST 登记公钥（文档 §4.4）。

    GET  —— 列出 `NodeLongTermKey` 的全部行（含被取代/已回收的历史版本）。
            生成页要按算法显示"服务端现在记的是哪一把、上一版是什么"，
            在此之前这个信息只能从 `Node.<算法>_public_key` 那一列反推 ——
            那是物化视图，只有一个值，答不出历史。
    POST —— 登记或**更新**一个算法的公钥。私钥在节点浏览器产生并留在那里，
            服务端只收公钥 —— 这是本接口与旧「服务端生成四套密钥」路径的根本
            区别（旧路径见 `initialize_base_keys` 的说明）。
            `rotate: true` 表示"同一把逻辑密钥（同 keyId）的新版本"，即更新
            （更新页与 `verify-keyupdate-rotate.mjs` 走这条）；此时 keyId 与
            keyVersion 必须一起给出，服务端不替调用方推断版本。缺省 false 是
            "这是我当前的公钥"：初始化页重报、生成页登记新密钥都走它。

    ⚠️ 两个方法**共用一条路由**：Django 里同一 path 写两条 `path()` 条目，
       第二条永远不会被匹配到（第一条先命中）—— 那种"接口加了但没生效"
       不报任何错，只会 405。所以在这里按 method 分派。

    ⚠️ POST 入口处显式拒绝私钥样式的字段名：与其信任调用方，不如在入口挡一道。
       一旦私钥进来，它就已经落进服务端日志与请求记录，**撤不回来**。
    """
    node = _find_node(identity)
    if node is None:
        return _error('当前账号未关联任何节点，无法登记密钥', 403)

    if request.method == 'GET':
        # 读自己的状态在停用后也应当可用：停用的是"产生新密钥"的能力。
        return _ok({'nodeId': node.node_id, 'keys': _long_term_keys_payload(node)})

    if _public_status(node) == 'DISABLED':
        return _error('该节点已被停用，无法登记密钥', 403)

    try:
        payload = json.loads(request.body or b'{}')
    except (ValueError, TypeError):
        return _error('请求体不是合法 JSON')
    if not isinstance(payload, dict):
        return _error('请求体应为 JSON 对象')

    forbidden = sorted(
        k for k in payload
        if str(k).lower() in {'privatekey', 'secretkey', 'private_key', 'secret_key', 'sk', 'private'}
    )
    if forbidden:
        return _error(
            '本接口只接受公钥，请求体中出现私钥字段：' + '、'.join(forbidden)
            + '。私钥应在节点侧保管，不得上传。'
        )

    algorithm = payload.get('algorithm')
    public_key = payload.get('publicKey') or payload.get('public_key')
    if not algorithm or not public_key:
        return _error('缺少 algorithm 或 publicKey')

    # 更新意图（KMS-006）。默认 False = "这是我当前的公钥"（登记/幂等重报）。
    # 认不出的值一律拒绝而不是猜 —— 猜错的方向恰好是最坏的那个（见 _as_bool）。
    try:
        rotate = _as_bool(payload.get('rotate'))
    except C.ContractError as exc:
        return _error(exc.message, error_code=exc.code)

    if identity.get('entryMode') == 'DEMO' and _public_status(node) == 'PENDING_INIT':
        from .demo_context import validate_init_lease
        if not validate_init_lease(request, node.node_id):
            return _error('初始化租约已失效，请重新进入初始化', 409,
                          error_code='DEMO_INIT_LEASE_REQUIRED')
        # 部分成功后只能重报同一把；不能因重试把另一浏览器已登记的钥匙换掉。
        existing = NodeLongTermKey.objects.filter(
            node=node, algorithm=algorithm, status=C.KEY_STATUS_ACTIVE).first()
        if existing and (
                existing.key_id != (payload.get('keyId') or payload.get('key_id'))
                or existing.key_version != payload.get('keyVersion', payload.get('key_version'))
                or _public_key_hex(existing) != str(public_key).lower()):
            return _error('该算法已登记，请复用对应的本地材料，不得重复初始化', 409,
                          error_code=C.ERR_KEY_VERSION_MISMATCH)

    try:
        service = NodeService(node.node_id)
        result = service.store_node_public_key(
            algorithm, public_key,
            payload.get('securityLevel') or payload.get('security_level'),
            payload.get('deviceId') or payload.get('device_id'),
            key_id=payload.get('keyId') or payload.get('key_id'),
            # ⚠️ 用 `.get(..., default)` 而不是 `or`：`keyVersion: 0` 会被 `or`
            # 吞成"没提供"，于是服务端**静默**按 v1 登记 —— 节点本地是 v0 的
            # 记账、服务端是 v1，两边都不报错。0 应当走到下面被拒。
            key_version=payload.get('keyVersion', payload.get('key_version')),
            rotate=rotate,
            demo_context=identity if identity.get('entryMode') == 'DEMO' else None,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception('节点 %s 登记公钥异常', node.node_id)
        return _error(f'登记公钥失败：{exc}', 500)

    if not result.get('success'):
        # 设备不一致是**可处置**的状态（重新初始化 / 换回原设备），
        # 不是参数错。用一个专门的业务码把它与普通参数错误分开，
        # 好让前端能给出对应的操作入口，而不是只弹一句红字。
        # `error_code` 是 `api_contract.ERR_*`（keyId 冲突、版本不符、参数非法……），
        # 前端按它分支，不要去匹配 msg 文案。
        return _error(
            result.get('message') or '登记公钥失败',
            409 if result.get('device_mismatch') else 400,
            error_code=result.get('code'),
        )

    node.refresh_from_db()

    # 计划 §7 阶段 2 判据④：更新事件进审计与链上。
    #
    # ⚠️ 位置在事务**之外**（`store_node_public_key` 里的原子块已提交）：
    #    存证失败不该回滚一次已经成立的更新 —— 密钥已经换好、旧版本已经降级，
    #    那些事实不因为链上少一条记录而改变。`record_chain_event` 失败只返回
    #    None 并记日志（旁路增强），所以这里拿到的是"空"而不是异常。
    chain_tx = ''
    if result.get('rotated'):
        chain_tx = record_chain_event(
            'KEY_UPDATED',
            # 用 NodeLongTermKey 的整数主键作链上 keyId（见 store_node_public_key
            # 的返回说明）：链上接口只收整数，字符串 key_id 会被解析失败吞成
            # "存证未成功"。非空 nodeId 把它与分发事件的 Java keyId 区分开。
            int(result.get('key_pk') or 0),
            int(result.get('key_version') or 0),
            node.node_id,
            # 上链只传摘要，不传公开材料本身（少写一点，链上就少暴露一点）。
            str(result.get('public_key_hash') or ''),
        ) or ''
        if chain_tx:
            logger.info('节点 %s 更新存证已上链: keyId=%s v%s tx=%s',
                        node.node_id, result.get('key_id'),
                        result.get('key_version'), chain_tx)

    return _ok(
        {
            'node': _node_payload(node),
            # 回传落库后的身份：节点据此核对"服务端记下的就是我本地那把"。
            # 只在成功时给，失败时 data 里是 error_code（两种形状不会混）。
            'algorithm': result.get('algorithm'),
            'keyId': result.get('key_id'),
            'keyVersion': result.get('key_version'),
            'keyStatus': result.get('status'),
            # 与分发响应同一口径（`chainHash`，见 user_distribution_views）：
            # 回哈希而不是布尔值。拿不到哈希时页面能如实说"已更新，但存证未成功"，
            # 而不是把两者混为一谈 —— 审计缺口必须是**可见的**。
            'chainHash': chain_tx,
        },
        msg=result.get('message') or '公钥已登记',
    )


@csrf_exempt
@require_http_methods(['POST'])
@require_kms_user
def node_self_revoke_key(request, identity):
    """回收本节点的一把长期密钥，并连带处理它的影响面（KMS-007）。

    这是节点侧「密钥回收」菜单的**落点**。在此之前那个菜单删的是另一个服务
    里的 `keymanage` 旧行（`DELETE /lifecycle/keymanage/{keyId}`），而
    `NodeLongTermKey` 那一行**原样不动** —— 页面显示"已回收"，节点手上的密钥
    还是那一把，四个业务入口照旧拿它干活。与 KMS-006 之前更新页的问题同源。

    ⚠️ `keyId` 与 `keyVersion` **必须一起显式给出**，服务端不替调用方推断
       "当前那一把" —— 与 `POST /node-self/keys/` 的 `rotate` 同一条纪律。
       被撤掉的是哪一行，事后只能靠这次请求的入参回答。

    影响面（`data.impact`）如实回报，**不做粉饰**：

      * `poolItems` —— 连带失效的预分配池项条数；
      * `sessions` —— 连带撤销的活跃会话数；
      * `sessionsOk` —— 会话那一半是否**确实**做成了。⚠️ 会话失效服务内部
        吞异常（失败返回 `{'success': False}` 而不抛出），失败时 `sessions`
        会是 0 而真实的活跃会话数可能大于 0。调用方（页面）**必须看这个标志**，
        不能把 `sessions == 0` 当成"没有会话受影响"。

    可重入：密钥已撤、池项与会话的重跑都只处理还没处理的部分，所以
    "失败后重试"能把没做完的补上，不会重复计数。

    ⚠️ **不碰任何私钥列**（`falcon_sign_private_key` 等）。装上可用性检查之后
       它们不再是判定依据，而清掉只会毁掉取证线索；私钥如何在后端彻底消失
       是另一件事（KMS-015）。
    """
    node = _find_node(identity)
    if node is None:
        return _error('当前账号未关联任何节点，无法回收密钥', 403)

    if _public_status(node) == 'DISABLED':
        return _error('该节点已被停用，无法回收密钥', 403)

    try:
        payload = json.loads(request.body or b'{}')
    except (ValueError, TypeError):
        return _error('请求体不是合法 JSON')
    if not isinstance(payload, dict):
        return _error('请求体应为 JSON 对象')

    # ⚠️ `keyVersion` 用 `.get(...)` 而不是 `or`：`keyVersion: 0` 会被 `or`
    #    吞成"没提供"，于是报出一句与实情无关的"缺少参数"。0 应当走到
    #    版本号校验里被明确拒掉（与 `node_self_keys` 的注释同一条理由）。
    algorithm = payload.get('algorithm')
    key_id = payload.get('keyId', payload.get('key_id'))
    key_version = payload.get('keyVersion', payload.get('key_version'))
    if not algorithm or not key_id or key_version is None:
        return _error('缺少 algorithm / keyId / keyVersion')

    try:
        result = revoke_long_term_key(
            node, algorithm, key_id, key_version,
            reason=payload.get('reason') or '',
        )
    except C.ContractError as exc:
        # 按 `api_contract.ERROR_HTTP_STATUS` 给业务码，而不是一律 400：
        # `KEY_NOT_FOUND`（撤了一个不存在的行）与 `INVALID_PARAMETER`（参数写错）
        # 对页面是两种提示。这个表是错误码与状态的**唯一**对应关系，别在这里另写一份。
        return _error(exc.message, C.ERROR_HTTP_STATUS.get(exc.code, 400),
                      error_code=exc.code)
    except Exception as exc:  # noqa: BLE001
        logger.exception('节点 %s 回收密钥异常', node.node_id)
        return _error(f'回收密钥失败：{exc}', 500)

    revoked = result['revoked']
    impact = result['impact']

    # 计划 §7 阶段 2 判据④：回收事件进审计与链上。
    #
    # ⚠️ 位置在事务**之外**（`revoke_public_key` 的原子块已提交）：存证失败
    #    不该回滚一次已经成立的回收 —— 密钥已经撤了、物化列已经清了，那些事实
    #    不因为链上少一条记录而改变。`record_chain_event` 失败只返回 None
    #    并记日志（旁路增强），所以这里拿到的是"空"而不是异常。
    #
    # ⚠️ 只在**本次才转入 REVOKED** 时发存证。重试（上一次池项/会话没做完）
    #    会再次走到这里，若无条件上链，同一次回收会在链上留下多条 KEY_REVOKED ——
    #    链上记录一旦重复，"回收了几次"就没有可信答案了。
    chain_tx = ''
    if not revoked['alreadyRevoked']:
        chain_tx = record_chain_event(
            'KEY_REVOKED',
            # 与 KEY_UPDATED 同口径：链上 keyId 用 NodeLongTermKey 的整数主键
            # （链上接口只收整数，字符串 key_id 会在 Java 侧解析失败，
            # 表现为"存证未成功"而不报错）。非空 nodeId 把它与分发事件区分开。
            int(revoked['rowId'] or 0),
            int(revoked['keyVersion'] or 0),
            node.node_id,
            # 上链只传摘要，不传公开材料本身。
            str(revoked['publicKeyHash'] or ''),
        ) or ''
        if chain_tx:
            logger.info('节点 %s 回收存证已上链: %s/%s v%s tx=%s',
                        node.node_id, revoked['algorithm'], revoked['keyId'],
                        revoked['keyVersion'], chain_tx)

    msg = (f"已回收 {revoked['algorithm']}/{revoked['keyId']} v{revoked['keyVersion']}："
           f"连带失效池项 {impact['poolItems']} 条、会话 {impact['sessions']} 条")
    if not impact['sessionsOk']:
        # 不把失败说成"0 个会话受影响" —— 那是两件不同的事，而后者会让人
        # 以为不用管。这里把实情写进 msg，页面上必须看得见。
        msg += f"；⚠️ 会话失效未成功（{impact['sessionMessage']}），请重试"

    return _ok(
        {
            'revoked': revoked,
            'impact': impact,
            # 与更新、分发同一口径（`chainHash`）：回哈希而不是布尔值。
            # 拿不到哈希时页面能如实说"已回收，但存证未成功"，
            # 而不是把两者混为一谈 —— 审计缺口必须是**可见的**。
            'chainHash': chain_tx,
        },
        msg=msg,
    )


@csrf_exempt
@require_http_methods(['POST'])
@require_kms_user
def node_self_init(request, identity):
    """
    节点首次初始化的**收尾**：校验四套基础公钥齐备，然后把节点置为 ACTIVE。

    ⚠️ 本接口**不生成任何密钥**（职责已在 §4.4 阶段一改掉，但这段 docstring
       直到 KMS-005 才跟上）。四套密钥由节点浏览器本地生成、逐个经
       `POST /node-self/keys/` 上报；这里只做"四套齐了吗"的判定与状态收尾。
       早先这里在服务端生成并落库四套**私钥**，还与文档 §0/§4「私钥留在节点侧」
       直接冲突 —— 实测 `dvadmin_pqkds_nodes` 里曾存着 Falcon 私钥 1.43MB。
       相应地也不再是 15~25 秒的长任务（那个耗时来自 Falcon 生成），
       现在的耗时只来自收尾时的一次上链请求。

    幂等：已 ACTIVE 的节点直接返回，不重复处理。
    失败：保持 PENDING_INIT，允许补齐缺的公钥后再次调用（四套必须全成才算完成）。

    ⚠️ **不要**用 `transaction.atomic()` 包裹。历史原因（
    `generate_falcon_keys_v2()` 在长耗时计算前主动 `connection.close()`，
    事务内关连接会丢弃整个未提交事务，表现为"接口返回 success 但库里只留下一半"）
    已随密钥生成搬走而消失；现在的原因是**收尾里有一次外部的上链请求**
    （`upload_node_registration`）—— 把网络调用包进事务会一直占着连接，
    且上链失败会把已经正确的状态一起回滚。上链失败只记日志，不影响初始化结论。
    """
    node = _find_node(identity)
    if node is None:
        return _error('当前账号未关联任何节点，无法执行初始化', 403)

    if _public_status(node) == 'DISABLED':
        return _error('该节点已被停用，无法初始化', 403)

    if identity.get('entryMode') == 'DEMO' and _public_status(node) == 'PENDING_INIT':
        from .demo_context import validate_init_lease
        if not validate_init_lease(request, node.node_id):
            return _error('初始化租约已失效，请重新进入初始化', 409,
                          error_code='DEMO_INIT_LEASE_REQUIRED')

    try:
        service = NodeService(node.node_id)
        result = service.initialize_base_keys()
    except Exception as exc:  # noqa: BLE001
        logger.exception('节点 %s 初始化异常', node.node_id)
        return _error(f'初始化失败：{exc}', 500)

    if not result.get('success'):
        return _error(result.get('message') or '初始化失败', 500)

    node.refresh_from_db()
    return _ok(
        {
            'alreadyInitialized': bool(result.get('already_initialized')),
            'completed': result.get('completed'),
            'node': _node_payload(node),
        },
        msg=result.get('message') or '初始化完成',
    )


# ---------------------------------------------------------------------------
# KMS-008：节点间分发的新请求契约（§16 的 peers / distributions 两条）
# ---------------------------------------------------------------------------
# 为什么这两条落在本模块、而不是 `user_distribution_views`：
#   * 它们属 `/node-self/*` 命名空间，本命名空间的响应约定是
#     **HTTP 恒 200、业务码在 `code`、可编程码在 `data.error_code`**（见本文件 `_error`），
#     与 `user_distribution_views._error`（真 HTTP 状态码）**不是一套**；
#   * 复用的 `_long_term_key_payload` / `_find_node` 都定义在本文件，
#     放对面会造成两个视图模块互相 import。
#
# ⚠️ 两条都收**业务编号**（`Node.node_id`，如 `KRB-S2U57I1`），不是主键 ——
#    与 `/user-nodes/` 回的 `nodeId`（那是主键）**不同**，页面传参时别混。
#    混了的表现是"节点明明在，接口说它不存在"。
@csrf_exempt
@require_http_methods(['GET'])
@require_kms_user
def node_peer_keys(request, peer_node_id, identity):
    """查**对端节点**可用于接收保护的长期密钥（§16.1）。

    发送方要显式选"用接收方的哪一版公钥封"，就需要先看到有哪些版本可选。
    返回的形状复用本文件 `_long_term_keys_payload`（与 `/node-self/keys/` 同形：
    `algorithm/keyId/keyVersion/status/statusLabel/allowsNewWork/publicKeyHash/
    effectiveAt/expiresAt/...`），**只含公开量** —— 那一份里本来就没有私钥。

    <h2>为什么要归属校验</h2>
    "公钥是公开量"不等于"谁都能枚举"。不校验的话，任一节点可以拿别人的节点编号
    把**全部节点**的密钥版本、状态、有效期逐个拉走 —— 那是一条不经过授权的
    资产探测通道。判据与服务端的 D5 同源：**调用方对该节点有有效授权**
    （`UserNodeAuthorization`，状态 active）。
    无授权返回 403 + `data.error_code = NOT_AUTHORIZED`。

    <h2>为什么不过滤状态</h2>
    与本文件 `_long_term_keys_payload` 同一条理由：页面要能显示"上一版已被取代"
    "这一版已回收"，只回可用的会让用户看到"密钥凭空少了一把"。
    **能不能用**由 `allowsNewWork` 字段回答（取自 `api_contract`，前端不另判），
    页面按它把不可用的版本置灰。

    `?algorithm=` 可给逗号分隔的算法名（规范名或历史拼写都认，经
    `canonical_algorithm` 归一）；**不给则不过滤**，把全部算法如实返回。
    """
    node = _find_node(identity)
    if node is None:
        return _error('当前账号未关联任何节点', 403, error_code=C.ERR_NOT_AUTHORIZED)

    peer = Node.objects.filter(node_id=peer_node_id).first()
    if peer is None:
        return _error(f'节点不存在：{peer_node_id}', 404, error_code=C.ERR_KEY_NOT_FOUND)

    # ⚠️ 比的是**主键**（`authorized_node_ids` 返回的就是主键），不是业务编号。
    if peer.id not in set(authorized_node_ids(identity['userId'])):
        return _error(
            f'你没有与节点 {peer.node_id} 的通信权限', 403, error_code=C.ERR_NOT_AUTHORIZED,
        )

    wanted = {
        C.canonical_algorithm(part)
        for part in (request.GET.get('algorithm') or '').split(',')
        if part.strip()
    }
    keys = [
        payload for payload in _long_term_keys_payload(peer)
        if not wanted or payload['algorithm'] in wanted
    ]
    return _ok({
        # 两个标识都给：主键给调用方回传用，业务编号给人看/给日志用。
        'nodeId': peer.id,
        'nodeCode': peer.node_id,
        'nodeName': peer.name,
        'keys': keys,
        'total': len(keys),
    })


@csrf_exempt
@require_http_methods(['POST'])
@require_kms_user
def node_self_distributions(request, identity):
    """发起一次**节点到节点**的分发 —— KMS-008 的新请求契约，KMS-009 起**由节点封装**。

    请求体（驼峰，snake_case 兼容；与 `/node-self/keys/` 同一套读法）：

    ```json
    { "receiverNodeId": "KRB-XXXX",        // 业务编号，不是主键
      "protectionAlgorithm": "KYBER",      // SM2 / SSCL / KYBER（规范名）
      "recipientKeyId": "KRB-XXXX-KYBER-ab12cd34",
      "recipientKeyVersion": 1,
      "falconKeyId": "KRB-XXXX-FALCON-4b7e1b0a",   // 发送方用于签名的 Falcon 密钥（KMS-010）
      "falconKeyVersion": 1,
      "batchId": "dist-20261003153012-4b7e1b0a",
      "expiresAt": "2026-10-04T15:30:12+08:00",
      "envelope": { ... },                 // 节点用接收方那一版公钥封好的密文
      "signature": "<base64>",             // 节点用本地 Falcon 私钥对规范字节串的签名
      "keyHash": "<64 位十六进制>" }        // SM4 载荷密钥的 SHA256（接收方自查用）
    ```

    ⚠️ `falconKeyId` / `falconKeyVersion` 必须与**签名时用的那把**一致：
       服务端按它们查公钥验签（计划 §6.1「所有请求显式携带版本」）。
       缺了它们无从得知是哪把私钥签的 —— 按"当前生产版本"替调用方猜会
       在并发轮换时验到另一把上，报成"签名无效"（像伪造）。

    <h2>与旧 `POST /key-pool/distribute-to-user/` 的差别（这就是"新契约"）</h2>
    1. **没有 `source_key_id`** —— 发送方不再需要一把"给自己解封"的用户密钥。
       传了也不作数（会记一条日志，落库的 `source_key_id` 是 NULL），
       因为新模型里根本不存在这个角色。
    2. **接收方密钥版本是显式的**，且登记时核对的就是**那一版**
       （`require_key_version` 先于落库查询）。旧流程读物化列，
       选哪版都等于"当前生产版本"。
    3. **只封给接收节点**，没有"发起用户自己的那一份"（用户腿）。
    4. 保护算法用**规范名**（SM2 / SSCL / KYBER）；Falcon 被拒 ——
       它是签名算法，不提供机密性（计划 §3）。

    <h2>KMS-009：SM4 与封装搬到了节点侧（服务端不再生成载荷密钥）</h2>
    节点在浏览器里生成 SM4、用接收方的**指定版本公钥**封装、再用**本地 Falcon
    私钥**签名（`crypto/envelope-signing.js` + `provider.wrapForPeer`），
    服务端只**核形状、算摘要、落库**。于是服务端从头到尾拿不到 SM4 明文
    （计划 §2.1）。

    ⚠️ `batchId` 与 `expiresAt` 由**调用方**给出：签名覆盖它们，
       服务端就不能在事后赋值。服务端仍校验形状与上界（"客户端给值"不等于
       "客户端说了算"）。

    <h2>KMS-010：服务端**验签**（本接口从"只收签名"升级为"验过才收"）</h2>
    信封必须用 `falconKeyId` / `falconKeyVersion` 指定的那一版发送方 Falcon
    公钥验得过才登记；验不过一律拒（`SIGNATURE_INVALID`），且**一条池行都不留下**。
    验签覆盖收发节点、保护算法、接收方 keyId 与版本、密文摘要、载荷密钥哈希、
    批次号与有效期 —— 改任何一个被签字段都会验不过。
    通过后回执里如实给 `signatureVerified: true`（只有验过才可能被回）。

    <h2>身份与权限</h2>
    发送方 = 令牌映射到的节点（前端传不了，也不该传）。需要：
      * 账号映射到节点，否则 403；
      * 具备 `CAP_DISTRIBUTE`（L2 及以上），否则 403；
      * 对接收节点有有效授权，否则 403。
    """
    try:
        payload = json.loads(request.body or b'{}')
    except (ValueError, TypeError):
        return _error('请求体不是合法 JSON')
    if not isinstance(payload, dict):
        return _error('请求体应为 JSON 对象')

    node = _find_node(identity)
    if node is None:
        return _error('当前账号未关联任何节点，无法发起分发', 403, error_code=C.ERR_NOT_AUTHORIZED)

    if payload.get('source_key_id') or payload.get('sourceKeyId'):
        # 不拒绝（迁移期里客户端可能还带着它），但必须让"它没被用到"可追溯 ——
        # 静默忽略一个字段，事后没人能回答"到底是不是按新的那套走的"。
        logger.info(
            '节点 %s 的分发请求带了 source_key_id=%r：新契约不使用它（节点间分发没有用户腿）',
            node.node_id, payload.get('source_key_id') or payload.get('sourceKeyId'),
        )

    receiver_code = str(
        payload.get('receiverNodeId') or payload.get('receiver_node_id') or ''
    ).strip()
    if not receiver_code:
        return _error('缺少 receiverNodeId（接收节点的业务编号）')
    receiver = Node.objects.filter(node_id=receiver_code).first()
    if receiver is None:
        return _error(f'接收节点不存在：{receiver_code}', 404, error_code=C.ERR_KEY_NOT_FOUND)

    # 阶段 7（文档 §8.4）：发起分发需要 distribute 能力。与旧入口同一口径 ——
    # 管理员不能代替节点发起（新模型里"发送方"必须是个有密钥的节点）。
    try:
        require_capability(node, CAP_DISTRIBUTE)
    except NodePermissionError as exc:
        return _error(str(exc), 403, error_code=C.ERR_NOT_AUTHORIZED)

    if receiver.id not in set(authorized_node_ids(identity['userId'])):
        return _error(
            f'你没有向节点 {receiver.node_id} 分发的权限', 403, error_code=C.ERR_NOT_AUTHORIZED,
        )

    try:
        result = create_node_distribution(
            node, receiver,
            protection_algorithm=payload.get('protectionAlgorithm')
            or payload.get('protection_algorithm') or '',
            recipient_key_id=payload.get('recipientKeyId') or payload.get('recipient_key_id'),
            recipient_key_version=payload.get('recipientKeyVersion')
            if payload.get('recipientKeyVersion') is not None
            else payload.get('recipient_key_version'),
            batch_id=payload.get('batchId') if payload.get('batchId') is not None
            else payload.get('batch_id'),
            expires_at=payload.get('expiresAt') if payload.get('expiresAt') is not None
            else payload.get('expires_at'),
            # KMS-010：**签名者那一版** Falcon 长期密钥，由请求显式给出。
            # ⚠️ 与 `keyVersion` 同一套读法：先驼峰、再 snake_case，用
            #    `is not None` 而不是 `or` 兜底 —— 后者会把 `0` 吞成"没提供"。
            #    版本 0 本来就非法（`_as_version` 拒），但读法不一致的代价是
            #    两个字段在同一份请求里行为不同，将来没人记得住哪条是哪条。
            falcon_key_id=payload.get('falconKeyId') if payload.get('falconKeyId') is not None
            else payload.get('falcon_key_id'),
            falcon_key_version=payload.get('falconKeyVersion')
            if payload.get('falconKeyVersion') is not None
            else payload.get('falcon_key_version'),
            # KMS-009：这三样由**节点**产出（本地封装 + 本地签名），
            # 服务端只登记。见该 service 的 docstring。
            envelope=payload.get('envelope'),
            signature=payload.get('signature'),
            key_hash=payload.get('keyHash') if payload.get('keyHash') is not None
            else payload.get('key_hash'),
        )
    except C.ContractError as exc:
        # 业务码按 `ERROR_HTTP_STATUS` 给（那是对外契约的唯一一份映射），
        # 可编程码原样放 `data.error_code` —— 页面据此分支，不匹配文案。
        return _error(exc.message, C.ERROR_HTTP_STATUS.get(exc.code, 400), error_code=exc.code)
    except Exception as exc:  # noqa: BLE001
        logger.exception('节点 %s 向 %s 分发异常', node.node_id, receiver_code)
        return _error(f'分发失败：{exc}', 500)

    key = result['recipient_key']
    return _ok(
        {
            'batchId': result['batch_id'],
            'receiverNodeId': receiver.node_id,
            'receiverNodeName': receiver.name,
            'protectionAlgorithm': result['protection_algorithm'],
            'wrappingAlgorithm': result['wrapping_algorithm'],
            # 回显**实际用的**那一版 —— 这是"请求里的版本真的进了封装"的可核对证据
            # （页面显示"用的是 v2"，而库里那一行也是 v2）。
            'recipientKeyId': key.key_id,
            'recipientKeyVersion': key.key_version,
            'keyHash': result['key_hash'],
            'sessionCount': result['session_count'],
            'expiresAt': result['expires_at'].isoformat(),
            # 空串 = 存证未成功（链不可用等）。**不隐藏**：
            # 前端据此如实显示"已分发，但存证未成功"，而不是混成一句"成功"。
            'chainHash': result['chain_hash'] or '',
            # KMS-012：这条分发对应的会话（发起方据此把 K 存进本地会话密钥库，
            # 并提交自己的持有证明）。为 None 表示本次没有建出会话 ——
            # 页面如实不显示"待确认"，而不是给一个点了会 404 的按钮。
            'sessionId': result.get('session_id'),
            'sessionStatus': result.get('session_status'),
            # KMS-010：验签真实发生了，且这一条只有**验过**才可能被回。
            # 失败在服务层就抛 `SIGNATURE_INVALID` 了，走不到这里 ——
            # 所以它不是"声明"，是"这一步已经过去了"。
            'signatureVerified': bool(result.get('signature_verified')),
            # 回显**验签实际用的**那一版签名密钥：页面显示"用哪把验的"，
            # 与请求里给的那一版逐字段对得上（对不上就说明请求的版本没进验签）。
            'falconKeyId': result['signing_key'].key_id,
            'falconKeyVersion': result['signing_key'].key_version,
            # KMS-011：**签名实际用的**那一版（与上面两个同值，但在同一份回执里
            # 用两个名字表达两件事：`falconKey*` 是"验签用的"，`signingKey*`
            # 是"签的"。现在是同一行记录，将来若支持"一把签、另一把验"会分叉）。
            # 接收方要回到**同一版**公钥验签，会话行也记的它（`node_session_versions`）。
            'signingKeyId': result['signing_key'].key_id,
            'signingKeyVersion': result['signing_key'].key_version,
            # 保留 `signaturePresent`（KMS-009 起就有）：它是"有没有带"的如实回答，
            # 与"验没验过"是两个问题。既有调用方若只看这一个字段，行为不变。
            'signaturePresent': True,
            'status': 'success',
        },
        msg='分发完成（信封已验签）',
    )


# ---------------------------------------------------------------------------
# 任务书「节点多级授权」：节点名录 + 授权申请（节点侧）
# ---------------------------------------------------------------------------
# 流程：节点看到**全网**名录 → 选对端 → 发起申请 → 管理员审批 → 双向放行。
#
# ⚠️ 这是本命名空间里**唯一**让节点看到"自己没被授权"的节点的接口，边界必须清楚：
#
#   * **放行判据自始至终只有一条**：`distribution_service.authorized_node_ids`
#     （`UserNodeAuthorization` 表）。申请单只记录过程 —— `status='approved'`
#     不构成任何放行理由。批准动作本身就是"写那两行授权"。
#     理由见 `models.NodeAuthorizationRequest` 的 docstring（仓库里那套被下线的
#     权限审批就是"批了不等于授权"的反面教材）。
#
#   * **名录只回身份性字段**（编号/名字/状态/域/类型/等级）——
#     **不含** ip/port/`sys_user_id`/公钥/密钥指纹。对照：
#     `GET /pqkds-api/pqkds/nodes/`（DRF 列表）把这些全回给**未认证**调用方，
#     那是另一处历史包袱，不能拿它当本接口的形状参考。
#     对端**密钥版本**仍然要授权后才可见（`node_peer_keys` 的归属校验不动）。
#
#   * 三个端点都是**函数视图**（`require_kms_user` 链），不是 DRF action ——
#     所以不需要登记进 `views.py` 的 `open_actions`/`_NODE_ADMIN_ACTIONS`。

def _authorization_state(node: Node, *, peer: Node, pending: dict) -> dict:
    """`node` 视角下与 `peer` 的授权关系（**两个方向分别判**）。

    ⚠️ 不合成一个"已授权"布尔：管理员手工只授单向是允许的（既有页面做得到），
       届时 A 能发给 B、B 回不了 —— 合成之后这种不对称在界面上就消失了，
       而用户看到的会是"已授权"却发不出去（或者反过来，明明能发却显示未授权）。
    """
    from .node_authorization_service import effective_authorizations

    directions = effective_authorizations(node, peer)
    entry = pending.get(peer.id) or {}

    def state(active: bool, direction: str) -> str:
        if active:
            return 'granted'
        return 'pending' if entry.get('direction') == direction else 'none'

    return {
        # `granted` 是"两个方向都通"的便捷布尔，仅供界面显示"已互通"标签；
        # 判断能不能发（outgoing）与对方能不能回（incoming）请分别看下面两项。
        'granted': directions['outgoing'] and directions['incoming'],
        'outgoing': state(directions['outgoing'], 'outgoing'),
        'incoming': state(directions['incoming'], 'incoming'),
        'pendingRequestId': entry.get('id'),
    }


def _load_pending_map(node: Node) -> dict:
    """这一节点参与的全部 pending 申请 → `{对方节点主键: {'direction', 'id'}}`。

    方向是**以 `node` 为视角**的：`outgoing` = 我发起的，`incoming` = 对方发起的。
    同一对节点无序去重（服务层保证同时只有一条 pending），所以一个对方只会出现一次。
    """
    from django.db.models import Q

    from .models import NodeAuthorizationRequest

    rows = NodeAuthorizationRequest.objects.filter(
        Q(requester=node) | Q(target=node), status='pending',
    ).values('id', 'requester_id', 'target_id')
    out = {}
    for row in rows:
        if row['requester_id'] == node.id:
            out[row['target_id']] = {'direction': 'outgoing', 'id': row['id']}
        else:
            out[row['requester_id']] = {'direction': 'incoming', 'id': row['id']}
    return out


def _request_payload(row) -> dict:
    """一条申请 → 页面需要的形状（**节点侧视角**，不带任何内部 id 之外的量）。"""
    return {
        'id': row.pk,
        'status': row.status,
        'statusLabel': row.get_status_display(),
        'reason': row.reason,
        'requesterNodeId': row.requester.node_id,
        'requesterName': row.requester.name,
        'targetNodeId': row.target.node_id,
        'targetName': row.target.name,
        'decidedBy': row.decided_by or '',
        'decidedAt': _iso(row.decided_at),
        'decisionRemark': row.decision_remark or '',
        # 链上存证哈希：空 = 未成功（如实为空，不粉饰）
        'chainTx': row.chain_tx or '',
        'createdAt': _iso(row.create_datetime),
        # 一次多选提交共用的组号；单目标申请为 None（页面据此把"一次提交的若干条"
        # 折叠成一组，而**不**据此判断权限 —— 判据只有授权表）。
        'batchId': row.batch_id or '',
        'batchSeq': row.batch_seq,
    }


@csrf_exempt
@require_http_methods(['GET'])
@require_kms_user
def node_directory(request, identity):
    """**全网节点名录**（任务书「节点多级授权」）。

    节点要能表达"我想和谁建会话"，就必须先看到有哪些节点 —— 在此之前
    `/user-nodes/` 只回**已被授权**的节点，"没授权"与"不存在"在界面上无法区分。
    本接口回全部（排除自己），并逐行带上与我的授权关系。

    暴露边界（见本段开头的说明）：只回身份性字段，不回 ip/port/sys_user_id/密钥材料。
    """
    node = _find_node(identity)
    if node is None:
        return _error('当前账号未关联任何节点，无法查看节点名录', 403)

    pending = _load_pending_map(node)
    rows = (
        Node.objects.exclude(pk=node.pk)
        .only('id', 'node_id', 'name', 'status', 'domain_id', 'node_type', 'permission_level')
        .order_by('node_id')
    )
    items = []
    for peer in rows:
        items.append({
            'nodeCode': peer.node_id,
            'name': peer.name,
            'status': _public_status(peer),
            'domainId': peer.domain_id,
            'nodeType': peer.node_type,
            'permissionLevel': peer.permission_level,
            'relationship': _authorization_state(node, peer=peer, pending=pending),
            # 停用节点不给申请入口：申请了也建不了会话（create_request 也会拒）。
            'canRequest': _public_status(peer) != 'DISABLED',
        })
    return _ok({
        'nodeId': node.node_id,
        'nodes': items,
        'total': len(items),
        # 与 /user-nodes/ 同一口径：一次分发的接收方数量上限（页面据此提示）。
        'maxSelectable': NODE_DIRECTORY_MAX_SELECT,
    })


@csrf_exempt
@require_http_methods(['GET', 'POST'])
@require_kms_user
def node_authorization_requests(request, identity):
    """我的授权申请：GET 列表 / POST 发起。

    GET 返回 `{outgoing: [...], incoming: [...]}`：
      * outgoing —— 我发起的（正在等审批 / 已出结果）；
      * incoming —— 别的节点想与我通信（我无权批，但看得见；决定权在管理员）。

    POST 支持两种入参（**并存**，单个走的是本功能最早的那条路径：
    `targetNodeId`，数组是"多选一次提交"扩展）：
      * `{targetNodeId: "节点编号", reason}` —— 单个目标；
      * `{targetNodeIds: [...], reason}` —— 一次提交多个目标（任务书「多选节点提交
        权限确认请求」）。走 `create_requests`，逐条独立成行、共用一个 `batchId`。
    """
    from .node_authorization_service import (
        AuthorizationRequestError, create_request, create_requests,
    )
    from .models import NodeAuthorizationRequest

    node = _find_node(identity)
    if node is None:
        return _error('当前账号未关联任何节点，无法使用授权申请', 403)

    if request.method == 'GET':
        base = NodeAuthorizationRequest.objects.select_related('requester', 'target')
        outgoing = base.filter(requester=node).order_by('-create_datetime')[:100]
        incoming = base.filter(target=node).order_by('-create_datetime')[:100]
        return _ok({
            'outgoing': [_request_payload(r) for r in outgoing],
            'incoming': [_request_payload(r) for r in incoming],
        })

    # ---- POST：发起申请 ----
    try:
        payload = json.loads(request.body or b'{}')
    except (ValueError, TypeError):
        return _error('请求体不是合法 JSON')
    if not isinstance(payload, dict):
        return _error('请求体应为 JSON 对象')

    if _public_status(node) == 'DISABLED':
        return _error('本节点已被停用，无法发起授权申请', 403)

    # ---- 批量：targetNodeIds 数组 ----
    raw_ids = payload.get('targetNodeIds') or payload.get('target_node_ids')
    if raw_ids is not None:
        if not isinstance(raw_ids, list) or not raw_ids:
            return _error('targetNodeIds 应为非空数组（单个目标请用 targetNodeId）')
        # 上限与名录的 `maxSelectable` 同口径：一次提交 10 个。
        if len(raw_ids) > NODE_DIRECTORY_MAX_SELECT:
            return _error(f'一次最多提交 {NODE_DIRECTORY_MAX_SELECT} 个目标（收到 {len(raw_ids)} 个）')

        codes, targets, missing = [], [], []
        for raw in raw_ids:
            code = str(raw or '').strip()
            if not code or code in codes:
                continue
            codes.append(code)
            peer = Node.objects.filter(node_id=code).first()
            if peer is None:
                missing.append(code)
            else:
                targets.append(peer)
        if missing:
            return _error(f'节点不存在：{", ".join(missing)}', 404, error_code=C.ERR_KEY_NOT_FOUND)
        if not targets:
            return _error('没有有效的目标节点')

        result = create_requests(node, targets, payload.get('reason') or '')
        created, skipped = result['created'], result['skipped']
        return _ok(
            {
                'batchId': result['batchId'],
                'created': [_request_payload(r) for r in created],
                'skipped': [
                    {
                        'nodeId': item['node'].node_id,
                        'nodeName': item['node'].name,
                        'reason': item['reason'],
                        # 业务拒绝（停用/无账号）带原始文案；两种幂等跳过没有 message。
                        'message': item.get('message', ''),
                    }
                    for item in skipped
                ],
                'total': result['total'],
            },
            msg=(f'已提交 {len(created)} 条申请，等待管理员审批'
                 + (f'（{len(skipped)} 条未新建，见明细）' if skipped else '')),
        )

    # ---- 单个（原有路径，行为不变）----
    target_code = str(payload.get('targetNodeId') or payload.get('target_node_id') or '').strip()
    if not target_code:
        return _error('缺少 targetNodeId（目标节点的业务编号）')
    target = Node.objects.filter(node_id=target_code).first()
    if target is None:
        return _error(f'节点不存在：{target_code}', 404, error_code=C.ERR_KEY_NOT_FOUND)

    try:
        result = create_request(node, target, payload.get('reason') or '')
    except AuthorizationRequestError as exc:
        return _error(exc.message, C.ERROR_HTTP_STATUS.get(exc.code, 400), error_code=exc.code)

    if result.get('alreadyGranted'):
        return _ok(
            {'alreadyGranted': True, 'request': None},
            msg=f'已与节点 {target.node_id} 双向授权，无需申请',
        )
    row = result['request']
    return _ok(
        {'alreadyGranted': False, 'created': result['created'], 'request': _request_payload(row)},
        msg=(f'申请已提交，等待管理员审批（{target.node_id}）' if result['created']
             else f'这一对节点已有待审批的申请（#{row.pk}），未重复创建'),
    )


@csrf_exempt
@require_http_methods(['POST'])
@require_kms_user
def node_authorization_request_cancel(request, request_id, identity):
    """撤回自己发起的待审批申请。"""
    from .node_authorization_service import AuthorizationRequestError, cancel_request

    node = _find_node(identity)
    if node is None:
        return _error('当前账号未关联任何节点，无法撤回申请', 403)

    try:
        row = cancel_request(node, request_id)
    except AuthorizationRequestError as exc:
        return _error(exc.message, C.ERROR_HTTP_STATUS.get(exc.code, 400), error_code=exc.code)

    return _ok({'request': _request_payload(row)}, msg='申请已撤回')


# ---------------------------------------------------------------------------
# 预分配密钥池：上传保护包 / 看余量 / 取用一条（任务书「预分配」）
# ---------------------------------------------------------------------------
# 规范（用户定义）："发送节点在实际通信之前，提前生成一定数量的随机 SM4 会话密钥，
# 利用接收节点的 Kyber 公钥形成加密保护包，并将保护包上传至 KMS 预分配密钥池。
# 服务端仅负责保存、调度和管理保护包。实际建立会话时，发送节点取用一条预分配资源，
# 使用 Falcon 私钥签名并发送…"
#
# ⚠️ 与 `KeyPoolViewSet`（管理端的 `/key-pool/*`）的分工：那套是**管理面**
#    （列表、统计、清理、删除），它调的是服务端生成的那条老路径
#    （`generate_kyber_pool` 自己生成 K），与计划 §2.1「服务端禁止接触 SM4 明文」
#    相抵 —— 那正是本次把**生成与封装搬到节点侧**的原因。三个新端点在此，
#    接收方与发送方都由令牌映射，传不了也不该传。

@csrf_exempt
@require_http_methods(['POST'])
@require_kms_user
def node_pool_preallocate(request, identity):
    """**上传一批保护包**（节点侧生成并封好的预分配资源）。

    请求体：
    ```json
    { "targetNodeCode": "KRB-XXXX",       // 接收方（业务编号）
      "poolId": "pool_<32hex>",           // 由**节点侧**生成：它进签名，服务端不能事后赋值
      "expiresAt": "2026-10-09T15:30:12+08:00",
      "items": [ { "envelope": {...}, "signature": "<base64>", "keyHash": "<64hex>" }, ... ] }
    ```

    <h2>为什么 poolId 由节点侧生成</h2>
    签名覆盖 `batch_id`（`NODE_ENVELOPE_SIGNED_FIELDS` 的第一项），而池项的
    `batch_id` 就是池号 —— 服务端事后赋值的话，节点签的是一份"还不知道自己
    属于哪个池子"的信（KMS-009 定下的同一口径，见 `envelope-signing.js`）。

    <h2>逐条：先验签，再落库</h2>
    每条保护包都必须用**请求指定的那一版发送方 Falcon 公钥**验得过
    （`verify_node_envelope`，与现场分发**同一个函数**），验不过的**不落库**、
    计入 `failed` 并附错误码。本端点是**部分成功**语义：一条坏了不该让
    另外 199 条一起作废（池子是渐进填的，用户接着补即可）。

    ⚠️ 每条独立落库（不是一个大事务）：`pool_id + key_index` 上有唯一约束，
       重复上传同一批时撞约束的那几条如实计入 `failed`（`DUPLICATE_ITEM`），
       而不是把整批回滚 —— 后者会让"补传第 51 条"变成不可能。
    """
    from .envelope_signature import verify_node_envelope
    from .key_pool_service import KeyPoolService
    from .node_key_registry import require_key_version, require_usable_key
    from .models import PreDistributedKey

    node = _find_node(identity)
    if node is None:
        return _error('当前账号未关联任何节点，无法上传预分配资源', 403,
                      error_code=C.ERR_NOT_AUTHORIZED)

    try:
        payload = json.loads(request.body or b'{}')
    except (ValueError, TypeError):
        return _error('请求体不是合法 JSON')
    if not isinstance(payload, dict):
        return _error('请求体应为 JSON 对象')

    target_code = str(payload.get('targetNodeCode') or payload.get('target_node_code') or '').strip()
    if not target_code:
        return _error('缺少 targetNodeCode（接收节点的业务编号）')
    receiver = Node.objects.filter(node_id=target_code).first()
    if receiver is None:
        return _error(f'节点不存在：{target_code}', 404, error_code=C.ERR_KEY_NOT_FOUND)
    if receiver.id == node.id:
        return _error('不能给自己预分配密钥', error_code=C.ERR_INVALID_PARAMETER)

    # 授权闸门：与 `/node-self/distributions/` **同一判据**（不另写一套）。
    from .distribution_service import authorized_node_ids
    if receiver.id not in set(authorized_node_ids(identity['userId'])):
        return _error(
            f'你没有与节点 {receiver.node_id} 的通信权限（预分配是分发的前置动作）',
            403, error_code=C.ERR_NOT_AUTHORIZED,
        )

    pool_id = str(payload.get('poolId') or payload.get('pool_id') or '').strip()
    if not pool_id or not _POOL_ID_RE.match(pool_id):
        return _error(
            'poolId 形状不对（期望 pool_<16~32 位十六进制>）—— 它进签名，必须由节点侧生成',
            error_code=C.ERR_INVALID_PARAMETER,
        )

    try:
        expires_at = _as_future_expiry(payload.get('expiresAt') if payload.get('expiresAt') is not None
                                      else payload.get('expires_at'))
    except ValueError as exc:
        return _error(str(exc), error_code=C.ERR_INVALID_PARAMETER)

    raw_items = payload.get('items')
    if not isinstance(raw_items, list) or not raw_items:
        return _error('items 应为非空数组（每条是一个保护包 + 签名）')
    if len(raw_items) > MAX_POOL_ITEMS_PER_BATCH:
        return _error(f'单次最多上传 {MAX_POOL_ITEMS_PER_BATCH} 条（收到 {len(raw_items)} 条）')

    # 接收方**当前可用**的那一版 Kyber 长期密钥：封装用的就是它，引用必须如实落库
    # （回收时的精确失效全靠这两列，见 KMS-007 D3）。
    try:
        recipient_key = require_usable_key(receiver, 'KYBER')
    except C.ContractError as exc:
        return _error(f'接收节点 {receiver.node_id} 的 Kyber 密钥不可用：{exc.message}',
                      C.ERROR_HTTP_STATUS.get(exc.code, 400), error_code=exc.code)

    # 发送方用于签名的 Falcon 版本：**每条显式携带**（与现场分发同一读法）。
    falcon_key_id = payload.get('falconKeyId') if payload.get('falconKeyId') is not None \
        else payload.get('falcon_key_id')
    falcon_key_version = payload.get('falconKeyVersion') \
        if payload.get('falconKeyVersion') is not None else payload.get('falcon_key_version')
    signing_key = None
    if falcon_key_id is not None and falcon_key_version is not None:
        try:
            signing_key = require_key_version(node, 'FALCON', falcon_key_id, falcon_key_version,
                                             for_new_work=False)
        except C.ContractError as exc:
            return _error(f'发送方 Falcon 密钥不可用：{exc.message}',
                          C.ERROR_HTTP_STATUS.get(exc.code, 400), error_code=exc.code)

    import hashlib
    import time as _time

    generated, failed, latencies = 0, [], []
    created_rows = []
    for index, raw in enumerate(raw_items):
        t0 = _time.perf_counter()
        if not isinstance(raw, dict):
            failed.append({'index': index, 'errorCode': 'INVALID_PARAMETER',
                           'message': 'item 应为对象'})
            continue
        envelope = raw.get('envelope')
        signature = str(raw.get('signature') or '').strip()
        if not isinstance(envelope, dict) or not envelope:
            failed.append({'index': index, 'errorCode': 'INVALID_PARAMETER',
                           'message': '缺少 envelope'})
            continue
        if not signature:
            failed.append({'index': index, 'errorCode': C.ERR_SIGNATURE_REQUIRED,
                           'message': '缺少 signature（保护包必须由发送节点本地签名）'})
            continue

        # 信封里必须**自洽**：池号、收发节点、接收方密钥版本都要与本次请求一致 ——
        # 不一致的信封意味着节点签的是另一批东西（或页面拼错了），此时落库会留下
        # 一条"谁也对不上"的池项。
        if str(envelope.get('batch_id') or '') != pool_id:
            failed.append({'index': index, 'errorCode': C.ERR_ENVELOPE_TAMPERED,
                           'message': '信封里的 batch_id 与本批 poolId 不一致'})
            continue
        if str(envelope.get('sender_node_id') or '') != node.node_id \
                or str(envelope.get('receiver_node_id') or '') != receiver.node_id:
            failed.append({'index': index, 'errorCode': C.ERR_ENVELOPE_TAMPERED,
                           'message': '信封里的收发节点与本次请求不一致'})
            continue
        if envelope.get('recipient_key_id') not in (None, recipient_key.key_id) \
                or (envelope.get('recipient_key_version') is not None
                    and str(envelope.get('recipient_key_version')) != str(recipient_key.key_version)):
            failed.append({'index': index, 'errorCode': C.ERR_KEY_VERSION_MISMATCH,
                           'message': f'信封标注的接收方密钥版本不是当前可用的那一版'
                                      f'（{recipient_key.key_id} v{recipient_key.key_version}）'})
            continue

        # 验签：用**请求指定的那一版**发送方 Falcon 公钥（缺版本时退回"当前可用"，
        # 与 KMS-010 之前的现场分发同一条兜底 —— 但如实记一条日志，因为它弱于显式版本）。
        verify_key = signing_key
        if verify_key is None:
            try:
                verify_key = require_usable_key(node, 'FALCON')
            except C.ContractError as exc:
                failed.append({'index': index, 'errorCode': exc.code,
                               'message': f'无法取到发送方 Falcon 公钥：{exc.message}'})
                continue
            logger.warning('预分配上传未携带 falconKeyId/Version，按当前可用版本 %s v%s 验签（弱于显式版本）',
                           verify_key.key_id, verify_key.key_version)
        if not verify_node_envelope(envelope, signature, verify_key.public_key):
            failed.append({'index': index, 'errorCode': C.ERR_SIGNATURE_INVALID,
                           'message': '签名校验失败（与发送节点的 Falcon 公钥不匹配）'})
            continue

        key_hash = str(raw.get('keyHash') or raw.get('key_hash')
                       or envelope.get('key_hash') or '').strip().lower()
        if not _SHA256_RE.match(key_hash or ''):
            failed.append({'index': index, 'errorCode': 'INVALID_PARAMETER',
                           'message': '缺少 keyHash（64 位十六进制）'})
            continue

        try:
            with transaction.atomic():
                PreDistributedKey.objects.create(
                    pool_id=pool_id,
                    key_index=index,
                    # 方向：`node1` = 收件方（与现场分发的信封腿同一列语义），
                    # 这样"谁取信封"的既有查询不用改。
                    node1=receiver,
                    node2=node,
                    algorithm='kyber_kem',
                    wrapping_algorithm='kyber_kem',
                    payload_algorithm='sm4',
                    # 保护包本体（密文 + 签名）。取用时才改写成可签的节点信封。
                    encrypted_key_data=json.dumps(
                        {**envelope, 'signature': signature},
                        ensure_ascii=False, sort_keys=True,
                    ),
                    key_hash=key_hash,
                    status=C.POOL_READY,
                    # ⚠️ 池项是一种**独立的资源形态**，不是"已经交出去的信封"：
                    # 取用（consume）的那一刻才翻成 'node'，接收方此时才看得见它。
                    # 用默认值 'node' 会让**还没发**的资源立刻出现在接收方列表里。
                    recipient_type='pool',
                    expires_at=expires_at,
                    generation_time_ms=round((_time.perf_counter() - t0) * 1000, 2),
                    long_term_key_id=recipient_key.key_id,
                    long_term_key_version=recipient_key.key_version,
                )
        except IntegrityError:
            # `pool_id + key_index` 唯一：这是**重复上传**（页面重试、或两条并发的
            # 同一批）。如实计入 failed，不把整批回滚 —— 见 docstring。
            failed.append({'index': index, 'errorCode': 'DUPLICATE_ITEM',
                           'message': '这一条已经在池子里（同一批同一序号）'})
            continue
        except Exception as exc:  # noqa: BLE001
            logger.warning('预分配上传第 %d 条落库失败：%s', index, exc)
            failed.append({'index': index, 'errorCode': 'INVALID_PARAMETER',
                           'message': f'落库失败：{exc}'})
            continue

        generated += 1
        created_rows.append(index)
        latencies.append((_time.perf_counter() - t0) * 1000)

    # 任务书 §20 的六项读数（服务端只度量**管理侧**这一步：验签 + 落库）。
    # ⚠️ 节点侧的封装耗时不在服务端 —— 它由页面自己度量并显示（`localMs`），
    #    两者不混成一句"吞吐"（服务端的 2933 条/秒与浏览器的 2600 条/秒
    #    说的是两件不同的事，合成一个数就没人能解释了）。
    total_sec = sum(latencies) / 1000.0
    # 审计流水（「分发记录」页的数据源）。上传这一步在**取用之前**，
    # 链上存证留给取用那条（`KEY_DISTRIBUTED` 的口径是"一把密钥被用于建立会话"，
    # 上传时还没有会话 —— 为它上链会把"存证"变成一笔糊涂账）。
    if generated:
        _write_pool_log(node, 'pool_prealloc', {
            'poolId': pool_id, 'targetNodeCode': receiver.node_id,
            'generated': generated, 'requested': len(raw_items),
            'algorithm': 'kyber_kem',
            'recipientKeyId': recipient_key.key_id,
            'recipientKeyVersion': recipient_key.key_version,
        })
    return _ok({
        'poolId': pool_id,
        'targetNodeCode': receiver.node_id,
        'generated': generated,
        'requested': len(raw_items),
        'failed': failed,
        'serverMs': round(total_sec * 1000, 1),
        'serverThroughputPerSec': round(generated / total_sec, 1) if total_sec > 0 else 0,
        'avgServerLatencyMs': round(sum(latencies) / len(latencies), 2) if latencies else 0,
        'expiresAt': expires_at.isoformat(),
        'recipientKeyId': recipient_key.key_id,
        'recipientKeyVersion': recipient_key.key_version,
    }, msg=(f'已上传 {generated}/{len(raw_items)} 条预分配资源'
            + (f'，{len(failed)} 条未通过（见明细）' if failed else '')))


def _write_pool_log(node, action: str, details: dict, tx_hash: str = '') -> None:
    """给预分配两条动作写一条「分发记录」流水。

    ⚠️ **失败不抛出**：流水是旁路审计，写不进去不该让一次已经成立的取用/上传
       变成失败（与链上存证同一条口径 —— 见 `record_distribution_chain_event`
       的 docstring：存证失败不改变分发结论）。
    ⚠️ **明文的 K 绝不进这里**：`details` 只放标识与计数（池号、序号、算法、
       `key_hash` 这类摘要），不放任何密钥材料 —— 这一列会出现在页面上。
    """
    from .models import KeyDistributionLog
    try:
        detail = dict(details)
        if tx_hash:
            detail['chainTx'] = tx_hash
        KeyDistributionLog.objects.create(
            node=node, action=action,
            details=json.dumps(detail, ensure_ascii=False),
            blockchain_tx_hash=tx_hash or '',
            success=True,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning('预分配流水写入失败（不影响本次动作）：action=%s node=%s %s',
                       action, node.node_id, exc)


@csrf_exempt
@require_http_methods(['GET'])
@require_kms_user
def node_pool_summary(request, identity):
    """每个对端**可用**的预分配资源条数（分发页据此显示"可用预分配 N 条"）。

    只回计数与最近过期时间，**不回密文** —— 密文本来就是封给接收方的，
    对发送方没有用途；回出去只是扩大暴露面。
    """
    from .pool_consume_service import pool_summary

    node = _find_node(identity)
    if node is None:
        return _error('当前账号未关联任何节点', 403)

    from .distribution_service import authorized_node_ids
    allowed = set(authorized_node_ids(identity['userId']))
    peers = list(Node.objects.filter(pk__in=allowed).only('id', 'node_id', 'name'))
    items = pool_summary(node, peers)
    return _ok({'items': items, 'total': sum(i['available'] for i in items)})


@csrf_exempt
@require_http_methods(['POST'])
@require_kms_user
def node_pool_consume(request, identity):
    """**取用一条预分配资源**：标记消费 + 归一成可签信封 + 建 initiated 会话。

    请求体：
    ```json
    { "peerNodeCode": "KRB-XXXX",      // 对端（本次会话的另一方）
      "batchId": "dist-20261008...",   // 本次交付的批次号（由节点侧生成，进签名）
      "falconKeyId": "...", "falconKeyVersion": 1,   // 发送方用于签名的 Falcon 版本
      "protectionAlgorithm": "KYBER" }
    ```

    响应里的 `envelope` 是**已盖好本次交付元数据、待签名**的信封 ——
    发送方在本地用 Falcon 私钥签完，调 `/node-self/envelopes/<id>/sign/` 补交，
    接收方那边才验得了签。**在这一步之前，接收方的信封列表里还没有它。**

    ⚠️ `keyHash` 一并回给发送方：签名要覆盖它，而它是池项在上传时就定下的
       （节点自己声称的那把 K 的摘要），所以发送方不需要重新算 —— 它本地
       存着 K，可以核对（页面对账用）。
    """
    from .pool_consume_service import PoolConsumeError, consume_pool_item

    node = _find_node(identity)
    if node is None:
        return _error('当前账号未关联任何节点，无法取用预分配资源', 403,
                      error_code=C.ERR_NOT_AUTHORIZED)

    try:
        payload = json.loads(request.body or b'{}')
    except (ValueError, TypeError):
        return _error('请求体不是合法 JSON')
    if not isinstance(payload, dict):
        return _error('请求体应为 JSON 对象')

    peer_code = str(payload.get('peerNodeCode') or payload.get('peer_node_code') or '').strip()
    if not peer_code:
        return _error('缺少 peerNodeCode（对端的业务编号）')
    peer = Node.objects.filter(node_id=peer_code).first()
    if peer is None:
        return _error(f'节点不存在：{peer_code}', 404, error_code=C.ERR_KEY_NOT_FOUND)

    # 授权闸门：与上传/分发**同一判据**。
    from .distribution_service import authorized_node_ids
    if peer.id not in set(authorized_node_ids(identity['userId'])):
        return _error(
            f'你没有与节点 {peer.node_id} 的通信权限', 403, error_code=C.ERR_NOT_AUTHORIZED,
        )

    batch_id = str(payload.get('batchId') if payload.get('batchId') is not None
                   else payload.get('batch_id') or '').strip()
    if not batch_id or not _DIST_BATCH_RE.match(batch_id):
        return _error('缺少或非法的 batchId（形状 dist-<14位时间>-<8位hex>，由节点侧生成）',
                      error_code=C.ERR_INVALID_PARAMETER)

    try:
        result = consume_pool_item(
            sender=node, receiver=peer, batch_id=batch_id,
            protection_algorithm=payload.get('protectionAlgorithm')
            or payload.get('protection_algorithm') or 'KYBER',
            falcon_key_id=payload.get('falconKeyId') if payload.get('falconKeyId') is not None
            else payload.get('falcon_key_id'),
            falcon_key_version=payload.get('falconKeyVersion')
            if payload.get('falconKeyVersion') is not None
            else payload.get('falcon_key_version'),
        )
    except PoolConsumeError as exc:
        return _error(exc.message, exc.http_status, error_code=exc.code)

    item = result['item']
    # 链上存证 + 审计流水（都在**事务提交之后**）：与现场分发同一口径 ——
    # `keyId` 位放**接收方那一版长期密钥**（保护 SM4 的正是它），`nodeId` 位放它的
    # 归属节点（接收方）。⚠️ 别在这里改成发送方：链上"哪台机器的哪把钥匙"一旦
    # 分叉，回读时就无法回答"谁受影响"（`record_distribution_chain_event` 的注释）。
    chain_tx = ''
    try:
        from .distribution_service import record_distribution_chain_event
        recipient_key = result['recipient_key']
        chain_tx = record_distribution_chain_event(
            'KEY_DISTRIBUTED', int(recipient_key.pk), int(recipient_key.key_version),
            peer.node_id, item.key_hash, batch_id,
        ) or ''
    except Exception as exc:  # noqa: BLE001
        # 存证失败**不影响取用结论**（信封已经交给发送方、会话已经建了）——
        # 与 `record_distribution_chain_event` 的 docstring 同一条纪律。
        logger.warning('预分配取用存证未成功（不影响本次取用）：%s#%s %s',
                       item.pool_id, item.key_index, exc)
    # 审计流水只记**摘要与标识**，绝不记 K（见 `_write_pool_log` 的说明）。
    _write_pool_log(node, 'pool_consume', {
        'poolId': item.pool_id, 'keyIndex': item.key_index,
        'batchId': batch_id, 'sessionId': result['session_id'],
        'peerNodeCode': peer.node_id, 'algorithm': 'kyber_kem',
        'keyHash': item.key_hash,
    }, tx_hash=chain_tx)
    return _ok({
        # 发送方本地要存 K（会话确认要用），所以它得知道这些：
        'envelopeId': item.pk,
        'poolId': item.pool_id,
        'keyIndex': item.key_index,
        # `keyHash` 是**发送方自己**在预分配时声称的那把 K 的摘要 ——
        # 服务端自始至终没有解开保护包，只是把它原样回传，供发送方对本机 K 自查
        # （服务端既不知道 K、也算不出 K）。
        'keyHash': item.key_hash,
        'wrappingAlgorithm': 'kyber_kem',
        'recipientKeyId': getattr(result['recipient_key'], 'key_id', None),
        'recipientKeyVersion': getattr(result['recipient_key'], 'key_version', None),
        'expiresAt': item.expires_at.isoformat() if item.expires_at else None,
        'sessionId': result['session_id'],
        'remaining': result['remaining'],
        'envelope': result['envelope'],
        # 与分发同一条口径：拿不到时是空串并附 warning，**不混成一句成功**。
        'chainHash': chain_tx,
        'chainWarning': '' if chain_tx else '已取用，但链上存证未成功（链不可用或未配置）',
    }, msg=f'已取用一条预分配资源（{item.pool_id}#{item.key_index}），'
           f'请在本机签名后补交（会话 {result["session_id"]}）')
