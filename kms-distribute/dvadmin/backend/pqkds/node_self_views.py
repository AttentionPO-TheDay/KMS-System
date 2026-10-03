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

from django.http import JsonResponse
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
    return {
        'nodeId': node.node_id,
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
        'keys': {
            'kyber': bool(node.kyber_public_key),
            'falcon': bool(node.falcon_public_key),
            'sm2': bool(node.gm_public_key),
            'sscl': bool(node.sscl_public_key),
        },
    }


def _long_term_key_payload(k: NodeLongTermKey) -> dict:
    """一行长期密钥 → 页面需要的形状。逐行调用，公钥只换算一次。"""
    public_key = _public_key_hex(k)
    return {
        'algorithm': k.algorithm,
        'keyId': k.key_id,
        'keyVersion': k.key_version,
        'status': k.status,
        # 状态文案与「这把还能干什么」都由服务端下发，取自 `api_contract`。
        # 前端**不另写一份**中文表与可用性判断：两份必然漂移，而漂移的表现是
        # "界面写着生产中、实际已被取代"—— 用户据此做的判断全是错的，
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
            # KMS-010：验签真实发生了，且这一条只有**验过**才可能被回。
            # 失败在服务层就抛 `SIGNATURE_INVALID` 了，走不到这里 ——
            # 所以它不是"声明"，是"这一步已经过去了"。
            'signatureVerified': bool(result.get('signature_verified')),
            # 回显**验签实际用的**那一版签名密钥：页面显示"用哪把验的"，
            # 与请求里给的那一版逐字段对得上（对不上就说明请求的版本没进验签）。
            'falconKeyId': result['signing_key'].key_id,
            'falconKeyVersion': result['signing_key'].key_version,
            # 保留 `signaturePresent`（KMS-009 起就有）：它是"有没有带"的如实回答，
            # 与"验没验过"是两个问题。既有调用方若只看这一个字段，行为不变。
            'signaturePresent': True,
            'status': 'success',
        },
        msg='分发完成（信封已验签）',
    )
