# -*- coding: utf-8 -*-
"""节点自助接口（阶段 2）。

    GET  /node-self/          我在 KMS 里对应的节点（含初始化状态）
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

import json
import logging

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .models import Node
from .node_service import NodeService
from .node_permission import (
    CAP_GENERATE,
    LEVEL_LABELS,
    NodePermissionError,
    capabilities_of,
    normalize_level,
    require_capability,
)
from .user_distribution_views import require_kms_user

logger = logging.getLogger(__name__)


def _ok(data=None, msg='操作成功'):
    return JsonResponse({'code': 200, 'msg': msg, 'data': data})


def _error(msg, code=400):
    return JsonResponse({'code': code, 'msg': msg, 'data': None}, status=200)


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
        # 四套密钥各自是否就绪 —— 首次初始化引导页用它显示进度
        'keys': {
            'kyber': bool(node.kyber_public_key),
            'falcon': bool(node.falcon_public_key),
            'sm2': bool(node.gm_public_key),
            'sscl': bool(node.sscl_public_key),
        },
    }


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
@require_http_methods(['POST'])
@require_kms_user
def node_self_keys(request, identity):
    """登记一个算法的**公钥**（文档 §4.4）。

    私钥在节点浏览器产生并留在那里，服务端只收公钥 —— 这是本接口与旧
    「服务端生成四套密钥」路径的根本区别（旧路径见 `initialize_base_keys` 的说明）。

    ⚠️ 入口处显式拒绝私钥样式的字段名：与其信任调用方，不如在入口挡一道。
       一旦私钥进来，它就已经落进服务端日志与请求记录，**撤不回来**。
    """
    node = _find_node(identity)
    if node is None:
        return _error('当前账号未关联任何节点，无法登记密钥', 403)
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

    try:
        service = NodeService(node.node_id)
        result = service.store_node_public_key(
            algorithm, public_key, payload.get('securityLevel') or payload.get('security_level')
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception('节点 %s 登记公钥异常', node.node_id)
        return _error(f'登记公钥失败：{exc}', 500)

    if not result.get('success'):
        return _error(result.get('message') or '登记公钥失败')

    node.refresh_from_db()
    return _ok({'node': _node_payload(node)}, msg=result.get('message') or '公钥已登记')


@csrf_exempt
@require_http_methods(['POST'])
@require_kms_user
def node_self_init(request, identity):
    """
    节点首次登录后初始化四套基础密钥：Kyber / SSCL / SM2 / Falcon。

    幂等：已 ACTIVE 的节点直接返回，不重复生成。
    失败：保持 PENDING_INIT，允许再次调用重试（四套必须全成才算完成）。

    ⚠️ 耗时：Falcon 占大头，整体约 15~25 秒。调用方必须显示 loading 并抑制重复提交。

    ⚠️⚠️ 这里**不能**用 `transaction.atomic()` 包裹 —— 2026-09-27 实测踩过：
    `node_service.generate_falcon_keys_v2()` 在 Falcon 长耗时计算**前会主动
    `connection.close()`**（`node_service.py:1022`，本意是避免 Falcon-1024 矩阵
    乘法期间 MySQL 空闲断连）。而事务内的 `close()` 会**丢弃整个未提交事务**：
    Kyber 与国密是在 Falcon 之前写的，连接一关全部丢失，只有 Falcon 在重连后
    新写的部分留了下来。表现是「接口返回 success、status=ACTIVE，
    但库里只有 Falcon，Kyber/国密全空」——比直接报错危险得多。

    不加事务不会失去正确性：初始化本来就是**非事务性**的长任务，
    一致性靠"四套全成才置 ACTIVE"这条判定保证；中途失败保持 PENDING_INIT，
    节点可以再次登录重试。
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
