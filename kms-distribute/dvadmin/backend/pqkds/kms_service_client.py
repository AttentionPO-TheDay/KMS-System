# -*- coding: utf-8 -*-
"""调用主 KMS 内部接口的客户端（D7 身份桥接 + §5.2 用户公钥）。

为什么需要一个独立的客户端模块
------------------------------
分发模块要与主 KMS 共享身份，但它**不能自己解释令牌**（那要把 JWT 密钥复制一份，
身份源就变成两处，与 D7 相反）。所以身份一律**问 KMS**：
`introspect` 把用户令牌换成 `kms.sys_user` 身份，`user-public-key` 给出加密目标点。

两条硬约束写在这里，免得日后被"优化"掉：

1. **`user_id` 只能来自 `introspect` 的结果**，绝不能从请求参数取 ——
   否则构造一个 `user_id` 就能查看别人的对称密钥。
2. **加密目标点只能来自 `user-public-key`**，绝不能自己去解析 `key_value` ——
   里面那个 `finalPublicKey` 是 `W_A`，用它加密出来的信封**谁都打不开**
   （计划 §3.2.3 用实验纠正过；`tools/verify-pa-target.mjs` 有回归用例）。
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional

import requests

logger = logging.getLogger(__name__)

#: 主 KMS 生命周期服务。沿用本仓库既有写法（Docker 网络服务名 + 可覆盖的环境变量）。
KMS_LIFECYCLE_BASE = os.getenv('KMS_LIFECYCLE_BASE', 'http://updatedel-java:9082')

#: 服务间令牌。与 Go↔Java 内部通道同一把，由 compose 注入。
INTERNAL_TOKEN = os.getenv('INTERNAL_TOKEN', '')

#: 单次调用超时。分发是同步动作，卡住比失败更糟，所以给得比较紧。
DEFAULT_TIMEOUT = 8

INTERNAL_TOKEN_HEADER = 'X-Internal-Token'


class KmsServiceError(Exception):
    """调用主 KMS 失败（网络/服务端异常）。与"用户令牌无效"区分开。"""


class KmsTokenInvalid(Exception):
    """用户令牌无效或已过期。调用方应据此返回 401，而不是 500。"""


def _internal_headers() -> Dict[str, str]:
    if not INTERNAL_TOKEN:
        # 静默发一个空令牌出去只会换来一个语焉不详的 500，
        # 不如在这里就把"部署没配好"说清楚。
        raise KmsServiceError(
            '未配置 INTERNAL_TOKEN，无法调用主 KMS 内部接口。'
            '该值由 compose 注入，参见 kms-ops/.env.example。'
        )
    return {INTERNAL_TOKEN_HEADER: INTERNAL_TOKEN, 'Content-Type': 'application/json'}


def introspect(user_token: str) -> Dict[str, Any]:
    """把用户令牌换成 `kms.sys_user` 身份。

    @return `{'userId': int, 'userName': str, 'roleLevel': int|None}`
    @raise KmsTokenInvalid 令牌无效/过期
    @raise KmsServiceError 网络或服务端故障
    """
    if not user_token or not str(user_token).strip():
        raise KmsTokenInvalid('缺少用户令牌')

    headers = _internal_headers()
    # 用户令牌走标准 Authorization 头：主 KMS 那边用同一套 TokenService 解析，
    # 不需要为分发模块另造一种令牌格式。
    headers['Authorization'] = 'Bearer ' + str(user_token).strip()

    try:
        response = requests.get(
            f'{KMS_LIFECYCLE_BASE}/internal/lifecycle/introspect',
            headers=headers,
            timeout=DEFAULT_TIMEOUT,
        )
    except requests.RequestException as exc:
        raise KmsServiceError(f'无法连接主 KMS 自省接口: {exc}') from exc

    if response.status_code != 200:
        # 服务令牌不对时，超时/鉴权失败都会走到这里 —— 属于部署问题，不是用户问题
        raise KmsServiceError(
            f'主 KMS 自省接口返回 {response.status_code}: {response.text[:200]}'
        )

    payload = response.json() or {}
    data = payload.get('data') or {}
    if not data.get('ok'):
        raise KmsTokenInvalid(data.get('errorMessage') or '令牌无效或已过期')

    user_id = data.get('userId')
    if user_id is None:
        # 自省说 ok 却没有 userId —— 这种"半成功"必须当成失败，
        # 否则下游会拿着 None 去查数据，查出一堆空结果还以为是"没有权限"。
        raise KmsServiceError('自省接口返回 ok 但缺少 userId')

    return {
        'userId': int(user_id),
        'userName': data.get('userName') or '',
        'roleLevel': data.get('roleLevel'),
    }


def user_public_key(key_id: int) -> Dict[str, Any]:
    """取某把密钥的**加密目标点** `P_A`（§5.2）。

    @return 成功时 `{'ok': True, 'publicKey': str, 'encrytName': str, ...}`
    @raise KmsServiceError 网络/服务端故障
    """
    headers = _internal_headers()
    try:
        response = requests.get(
            f'{KMS_LIFECYCLE_BASE}/internal/lifecycle/user-public-key',
            headers=headers,
            params={'keyId': key_id},
            timeout=DEFAULT_TIMEOUT,
        )
    except requests.RequestException as exc:
        raise KmsServiceError(f'无法连接主 KMS 用户公钥接口: {exc}') from exc

    if response.status_code != 200:
        raise KmsServiceError(
            f'主 KMS 用户公钥接口返回 {response.status_code}: {response.text[:200]}'
        )

    payload = response.json() or {}
    data = payload.get('data') or {}
    if not data:
        raise KmsServiceError('主 KMS 用户公钥接口返回空数据')
    # 注意：`ok=false` 是**业务结论**（密钥不存在/已回收/算法不支持），
    # 不是异常。调用方要把它当作"这把密钥不能用于分发"来回应，
    # 而不是当成服务故障重试。
    return data


def issue_session(user_id: int) -> str:
    """为**已通过设备凭据验证**的节点铸一个标准 RuoYi 令牌。

    为什么必须走这里，而不是在 Django 侧自己造令牌
    ------------------------------------------------
    D7 把 `kms.sys_user` 定为唯一身份源 —— 令牌只能有 RuoYi 一个签发者。
    Django 若自行签一份 JWT，就要复制 JWT 密钥与 Redis 会话格式，
    身份源立刻变成两处，且两边会各自漂移（而漂移的表现是"某些页面莫名 401"）。
    所以这里只做"把已验证的结论告诉 KMS，请它发令牌"。

    ⚠️ 调用前提：**调用方已完成设备签名验证**。
       本函数自己**不做任何身份校验** —— 它信任内部通道的调用者。
       因此它绝不能暴露成对外端点（对外暴露 = 任何人可给任意 userId 铸令牌）。
       这正是它只被 `node_auth_views` 在验签成功之后调用的原因。

    @param user_id 目标账号（应为该节点的 `sys_user_id`）
    @return 令牌字符串
    @raise KmsServiceError 网络/服务端故障，或 KMS 拒绝签发
    """
    headers = _internal_headers()
    try:
        response = requests.post(
            f'{KMS_LIFECYCLE_BASE}/internal/lifecycle/session/issue',
            headers=headers,
            json={'userId': int(user_id)},
            timeout=DEFAULT_TIMEOUT,
        )
    except requests.RequestException as exc:
        raise KmsServiceError(f'无法连接主 KMS 令牌签发接口: {exc}') from exc

    if response.status_code != 200:
        raise KmsServiceError(
            f'主 KMS 令牌签发接口返回 {response.status_code}: {response.text[:200]}'
        )

    payload = response.json() or {}
    data = payload.get('data') or {}
    if not data.get('ok'):
        raise KmsServiceError(data.get('errorMessage') or '主 KMS 拒绝签发令牌')

    token = str(data.get('token') or '').strip()
    if not token:
        # "说 ok 却没给令牌"这种半成功必须当失败，
        # 否则调用方会拿着空串当令牌用，现象是"登录后立刻 401"。
        raise KmsServiceError('主 KMS 返回 ok 但未包含 token')
    return token


def list_users(keyword: Optional[str] = None) -> list:
    """账号列表（供管理端的用户选择器用）。

    浏览器**不能**直接调这个内部接口（它需要 `X-Internal-Token`），
    所以由分发模块以自己的管理员门控为前置、代理转发（见 `admin_node_authorization_views`）。
    这样浏览器只需要跟两个它已经在用的 base 打交道，内部令牌一步都不出服务端。
    """
    headers = _internal_headers()
    params = {}
    if keyword:
        params['keyword'] = keyword
    try:
        response = requests.get(
            f'{KMS_LIFECYCLE_BASE}/internal/lifecycle/users',
            headers=headers,
            params=params,
            timeout=DEFAULT_TIMEOUT,
        )
    except requests.RequestException as exc:
        raise KmsServiceError(f'无法连接主 KMS 用户列表接口: {exc}') from exc

    if response.status_code != 200:
        raise KmsServiceError(
            f'主 KMS 用户列表接口返回 {response.status_code}: {response.text[:200]}'
        )
    payload = response.json() or {}
    data = payload.get('data')
    return data if isinstance(data, list) else []


def record_chain_event(event_type: str, key_id: int, version: int = 0,
                       node_id: str = '', public_material_hash: str = '',
                       timeout: int = 12) -> Optional[str]:
    """把一条生命周期事件记到链上（文档 §8.6）。

    @return 成功时交易哈希；任何失败都返回 None
    @raise KmsServiceError 只在调用方明确需要区分"服务不可用"时抛出（见下）

    <h2>为什么失败**不抛异常**</h2>
    上链存证是**旁路增强**，不是分发主流程的一部分。分发已经把密钥安全地交到了
    接收方手上 —— 这个事实不因为链上少一条记录而改变。如果这里抛异常并让调用方
    回滚，就会造成"链上写失败 ⇒ 用户拿不到密钥"，把可用性问题升级成功能问题。

    所以失败一律返回 None 并记日志，由调用方决定怎么呈现（通常是如实告知
    "已分发，但存证未成功"）。**绝不静默吞掉** —— 那会让审计缺口不可见。

    <h2>为什么不复用 `/kms/lifecycle-record`</h2>
    那个端点会把请求**转发成一次真实的密钥更新/回收调用**（`_call_lifecycle_api`），
    语义完全不同：它改密钥状态，本函数只留痕。用它记 KEY_DISTRIBUTED
    会让主 KMS 把分发误当成一次轮换，把密钥版本白白推进一格。
    """
    from .chain_backend import is_fabric_did, chain_writes_enabled
    if not chain_writes_enabled():
        logger.info('CHAIN_WRITES_PAUSED: 本地操作已记录，不提交链事件 type=%s keyId=%s', event_type, key_id)
        return None
    if is_fabric_did():
        # 数字 keyId + 摘要不能冒充 DID 的完整公钥/版本绑定，也不能悄悄
        # 回退去发 FISCO 事件。登记事件走 durable outbox；其余语义待链方确认。
        logger.warning('Fabric DID 未使用旧生命周期事件接口: type=%s keyId=%s；绑定状态请查询登记任务', event_type, key_id)
        return None
    try:
        headers = _internal_headers()
    except KmsServiceError as exc:
        logger.warning('上链存证不可用（内部令牌未配置）: %s', exc)
        return None

    payload = {
        'eventType': event_type,
        'keyId': int(key_id),
        'version': int(version or 0),
        'nodeId': node_id or '',
        # ⚠️ 传的是**摘要**而不是公开材料本身。链上只需要能核验"是不是同一份材料"，
        #    不需要材料原文；少写一点，链上就少暴露一点。
        'publicMaterialHash': public_material_hash or '',
    }
    try:
        response = requests.post(
            f'{KMS_LIFECYCLE_BASE}/internal/lifecycle/chain/event',
            headers=headers,
            json=payload,
            timeout=timeout,
        )
    except requests.RequestException as exc:
        logger.warning('上链存证请求失败: type=%s keyId=%s err=%s', event_type, key_id, exc)
        return None

    if response.status_code != 200:
        logger.warning('上链存证返回 %s: %s', response.status_code, response.text[:200])
        return None
    try:
        body = response.json() or {}
    except ValueError:
        logger.warning('上链存证响应不是 JSON: %s', response.text[:200])
        return None
    data = body.get('data') or {}
    tx_hash = data.get('chainHash')
    if not tx_hash:
        logger.warning('上链存证未返回交易哈希: %s', str(body)[:200])
        return None
    return tx_hash


def extract_bearer_token(request) -> Optional[str]:
    """从 Django 请求里取用户令牌。

    只认 `Authorization: Bearer xxx`。**不**接受从查询串或 body 传令牌 ——
    令牌出现在 URL 里会被网关日志、浏览器历史、Referer 记录下来。
    """
    authorization = request.META.get('HTTP_AUTHORIZATION', '')
    if authorization.lower().startswith('bearer '):
        token = authorization[7:].strip()
        return token or None
    return None