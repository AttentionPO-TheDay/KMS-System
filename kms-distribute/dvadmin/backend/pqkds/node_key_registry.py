# -*- coding: utf-8 -*-
"""长期密钥登记的唯一入口（计划 §6.1 / KMS-004）。

为什么要有这个模块，而不是在各 service 里各写各的
------------------------------------------------
"服务端保存什么、什么时候算生效"这条规则必须在**一个地方**强制。分散写的后果
不是冗余，是每个调用点各松一点，而松掉的那一点不会报错：

  * 登记时必须**同时**更新 `NodeLongTermKey` 和 `Node.<算法>_public_key`。
    分开写会产生两处不一致，而"哪一处为准"取决于谁先读 —— 这类不一致
    在测试里表现为"有时对"，比稳定错更难查；
  * 同一节点同一算法**只能有一个** ACTIVE。应用层判断在并发下会双双通过
    （两个请求都还没看到对方尚未提交的行），真正的约束只能在数据库
    （唯一约束 `pqkds_ltk_uniq_active_per_node_alg`，建在 `active_slot` 上 ——
    一个 status 的派生列，取值见 `models.NodeLongTermKey.active_slot`）。
    这里负责把旧版本降级，数据库负责在漏掉时直接拒绝；
  * 回收时必须**同时**把 `Node.<算法>_public_key` 清空。不清空的话，大量既有
    读路径会继续把已回收的公钥当成可用 —— 而失败是静默的：解密照样成功，
    只是本该被拒绝的操作成功了。

这个模块是这三个不变量的所有者。任何直接 `node.kyber_public_key = ...` 的赋值
都是绕过；新增写入点应当改成调用这里。

与 `node_service.store_node_public_key` 的关系
---------------------------------------------
那个方法是**节点上报公钥**的接口层实现（做设备一致性检查、Kyber hex→base64
归一化）。KMS-005 之后它改为：先做它自己的检查与归一化，再调用本模块落库。
本模块不认识"设备指纹校验"这类业务规则，只保证存储层的三个不变量。
"""

from __future__ import annotations

import hashlib
import re
import uuid
from typing import Dict, Optional, Tuple

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from . import api_contract as C
from .models import Node, NodeLongTermKey

#: 可以登记为长期密钥的算法。**包含 FALCON** —— 它是合法的长期密钥，
#: 只是不能出现在保护算法字段里。这两个白名单不是一回事，别合并。
REGISTRABLE_ALGORITHMS = tuple(C.PROTECTION_ALGORITHMS) + tuple(C.SIGNATURE_ALGORITHMS)

#: 规范算法名 → `Node` 上的公钥列。双写目标。
_PUBLIC_KEY_COLUMN = dict(C.NODE_PUBLIC_KEY_COLUMN)

#: 规范算法名 → 除规范列之外**还要一起写**的镜像列。目前只有 FALCON。
#:
#: `Node` 上有两列装 Falcon 公钥，而它们语义不同：
#:   * `falcon_sign_public_key` —— 规范列，签名路径真正读的那一列；
#:   * `falcon_public_key`      —— CL-Falcon 时代的旧列，**但仍有读路径**在用它
#:     （`initialize_base_keys` 的就绪判定、`database_blockchain_sync_service`、
#:      若干 benchmark / 清理脚本）。
#:
#: 新登记的节点两列写同一把标准 Falcon 公钥。之所以不在这里顺手停写旧列：
#: 读路径还没清干净，停写会让每个新注册节点的 `falcon_public_key` 变成空，
#: 上列那些读取方立刻看到空值 —— 那是 KMS-015（封存遗留路径）要一起做的事。
#:
#: 放在这里而不是留在调用点，因为镜像列是**存储层一致性**的一部分：
#: 回收时必须与规范列一起清空，漏掉任何一列都会让已回收的公钥继续可读。
_MIRROR_COLUMNS: Dict[str, Tuple[str, ...]] = {
    'FALCON': ('falcon_public_key',),
}

_ID_SAFE = re.compile(r'[^A-Za-z0-9_.-]')


def hash_public_key(public_key: str) -> str:
    """公钥摘要（sha256 十六进制）。

    ⚠️ 算的是**存储形式的字符串**，不是解码后的字节：Kyber 存 base64、其余存
       小写 hex，同一把密钥的两种编码字节相同而摘要不同。用存储形式才能保证
       "同一行永远同一摘要"——这是拿摘要做对账的前提。
    """
    return hashlib.sha256(str(public_key or '').encode('utf-8')).hexdigest()


def new_key_id(node: Node, algorithm: str) -> str:
    """生成一个新逻辑密钥标识。

    形状 `{node_id}-{ALGO}-{8位随机}`。要求：
      * 可读 —— 出问题时从 key_id 就能看出属于哪个节点的哪种算法；
      * 路径安全 —— 前端 keyRef 是 `node/{nodeId}/{algorithm}/{keyId}/{version}`，
        key_id 里出现 `/` 会把引用切错段（**切错不报错，只会找不到密钥**）；
      * 不重复 —— 后缀取 uuid4 前 8 位。
    """
    name = C.canonical_algorithm(algorithm)
    if name not in REGISTRABLE_ALGORITHMS:
        raise C.AlgorithmNotAllowed(
            f'{algorithm!r} 不能登记为长期密钥（允许：{"、".join(REGISTRABLE_ALGORITHMS)}）'
        )
    safe_node = _ID_SAFE.sub('-', str(node.node_id or node.pk))
    return f'{safe_node}-{name}-{uuid.uuid4().hex[:8]}'


def _assert_registrable(algorithm: str) -> str:
    name = C.canonical_algorithm(algorithm)
    if name not in REGISTRABLE_ALGORITHMS:
        raise C.AlgorithmNotAllowed(
            f'{algorithm!r} 不能登记为长期密钥（允许：{"、".join(REGISTRABLE_ALGORITHMS)}）'
        )
    return name


def _demote_active(node: Node, algorithm: str, keep_pk: Optional[int] = None) -> int:
    """把该节点该算法现有的 ACTIVE 行降级为 RETIRED。返回降级条数。

    `keep_pk` 是本轮新登记的行（若它已经是 ACTIVE）—— 不能把自己降级。

    ⚠️ 走 `.update()` 就绕过了 `NodeLongTermKey.save()` 的派生逻辑，
       所以必须**手写** `active_slot=None`。漏掉的后果不是报错，是唯一约束
       失效：降级后的行仍占着槽位，下一次登记撞约束却看不出为什么。
    """
    qs = NodeLongTermKey.objects.filter(
        node=node, algorithm=algorithm, status=C.KEY_STATUS_ACTIVE,
    )
    if keep_pk is not None:
        qs = qs.exclude(pk=keep_pk)
    return qs.update(status=C.KEY_STATUS_RETIRED, active_slot=None)


def _write_node_column(node: Node, algorithm: str, public_key: str) -> None:
    """双写的"物化视图"那一半：把当前生产公钥写回 `Node.<算法>_public_key`。

    用 `queryset.update()` 而不是 `node.save()`：后者会把整个 Node 行写回，
    在并发登记时可能用陈旧的内存副本覆盖别人刚写的字段。

    镜像列（见 `_MIRROR_COLUMNS`）与规范列**同写同清**：`public_key=''`
    是回收路径，它必须把两列都清掉，否则已回收的 Falcon 公钥仍能被
    `node.falcon_public_key` 读到。
    """
    column = _PUBLIC_KEY_COLUMN.get(algorithm)
    if not column:
        return  # 理论上到不了：上面的白名单已经拦过
    columns = (column, *_MIRROR_COLUMNS.get(algorithm, ()))
    Node.objects.filter(pk=node.pk).update(**{c: public_key for c in columns})
    # 让调用方手里的实例与服务端一致，避免它随后拿旧值做判断
    for c in columns:
        setattr(node, c, public_key)


@transaction.atomic
def register_public_key(
    node: Node,
    *,
    algorithm: str,
    public_key: str,
    key_id: str = '',
    key_version: int = 1,
    security_level: str = '',
    device_id: str = '',
    effective_at=None,
    expires_at=None,
    activate: bool = True,
    legacy: bool = False,
    legacy_source: str = '',
) -> NodeLongTermKey:
    """登记一把长期公钥。**这是唯一的写入入口。**

    `activate=True`（默认）时把该算法现有的 ACTIVE 行降级为 RETIRED，本行升为
    ACTIVE；同一事务内完成，并由数据库的部分唯一索引兜底。

    **幂等**：同 (node, algorithm, key_id, key_version) 且公钥摘要相同 —— 直接返回
    已有行，不做任何变更。这是必要的：节点初始化页每次进入都会重新上报一遍公钥，
    不幂等的话每次进页面都会"轮换"一次密钥。

    同身份但摘要不同则抛 `ContractError`（这不是重报，是真冲突 ——
    要换公钥应当走 `rotate_public_key`，它的语义是"新版本"而不是"同名覆盖"）。
    """
    name = _assert_registrable(algorithm)
    material = str(public_key or '').strip()
    if not material:
        raise C.ContractError('公钥为空', code=C.ERR_INVALID_PARAMETER)

    digest = hash_public_key(material)
    version = int(key_version or 1)
    kid = (key_id or '').strip()

    if kid:
        existing = NodeLongTermKey.objects.filter(
            node=node, algorithm=name, key_id=kid, key_version=version,
        ).first()
        if existing is not None:
            if existing.public_key_hash == digest:
                return existing
            raise C.ContractError(
                f'{name} 密钥 {kid} v{version} 已登记且公钥不同；'
                f'换公钥应当走 rotate_public_key（新版本），不要同名覆盖',
                code=C.ERR_KEY_VERSION_MISMATCH,
            )
    elif activate:
        # 没给 key_id 时，调用方的意思是"这是我当前的公钥"（节点上报路径），
        # 不是"生成一把新密钥"。同一把公钥重复上报必须是**无操作** ——
        # 节点初始化页每次进入都会把四套公钥重报一遍，不拦的话每进一次页面
        # 就多一个版本、把上一版降级成 RETIRED：版本历史被噪声填满，
        # "当前版本号"也在毫无理由地变动，而它正是信封要引用的东西。
        #
        # 判据用公钥摘要而不是 key_id：新生成的 key_id 每次都不同，认不出"同一把"。
        # 公钥相同即同一把 —— 随机生成的密钥不会碰巧相同。
        existing = NodeLongTermKey.objects.filter(
            node=node, algorithm=name, public_key_hash=digest,
            status=C.KEY_STATUS_ACTIVE,
        ).first()
        if existing is not None:
            # 只补空字段。已有值是"这把密钥生成时的环境"，不该被后续上报改写
            # （换设备生成新密钥属于轮换，那是 rotate 的事）。
            touched = []
            if device_id and not existing.device_id:
                existing.device_id = device_id[:128]
                touched.append('device_id')
            if security_level and not existing.security_level:
                existing.security_level = security_level[:20]
                touched.append('security_level')
            if touched:
                existing.save(update_fields=touched + ['update_datetime'])
            return existing

    if not kid:
        kid = new_key_id(node, name)

    now = timezone.now()
    if activate:
        _demote_active(node, name)

    row = NodeLongTermKey.objects.create(
        node=node,
        key_id=kid,
        key_version=version,
        algorithm=name,
        status=C.KEY_STATUS_ACTIVE if activate else C.KEY_STATUS_PENDING,
        public_key=material,
        public_key_hash=digest,
        security_level=(security_level or '')[:20],
        device_id=(device_id or '')[:128],
        effective_at=effective_at or (now if activate else None),
        expires_at=expires_at,
        legacy=legacy,
        legacy_source=(legacy_source or '')[:64],
    )

    if activate:
        _write_node_column(node, name, material)

    return row


@transaction.atomic
def rotate_public_key(
    node: Node,
    *,
    algorithm: str,
    public_key: str,
    security_level: str = '',
    device_id: str = '',
    effective_at=None,
    expires_at=None,
) -> NodeLongTermKey:
    """**更新**：保留 `key_id`，`key_version` 递增，旧版本降级为 RETIRED。

    与 `register_public_key` 的区别就是计划 §6.1 那句"更新保留 key_id，递增
    key_version" —— 更新不是"又生成了一把新密钥"，是"同一把密钥的新版本"。
    这个区别决定了历史信封能不能被追溯回它用的那一版。

    找不到当前版本时退化为新建（首次登记），因为对调用方来说
    "更新一个还没有的密钥"和"登记它"是同一件事。
    """
    name = _assert_registrable(algorithm)
    material = str(public_key or '').strip()
    if not material:
        raise C.ContractError('公钥为空', code=C.ERR_INVALID_PARAMETER)

    current = NodeLongTermKey.objects.filter(
        node=node, algorithm=name,
    ).order_by('-key_version', '-id').first()

    if current is None:
        return register_public_key(
            node, algorithm=name, public_key=material,
            security_level=security_level, device_id=device_id,
            effective_at=effective_at, expires_at=expires_at,
        )

    return register_public_key(
        node, algorithm=name, public_key=material,
        key_id=current.key_id,
        key_version=current.key_version + 1,
        security_level=security_level or current.security_level,
        device_id=device_id,
        effective_at=effective_at,
        expires_at=expires_at,
    )


@transaction.atomic
def revoke_public_key(key: NodeLongTermKey, reason: str = '') -> NodeLongTermKey:
    """回收一把长期密钥。

    两个必须一起发生的动作：
      1. 本行标记 REVOKED（保留 `public_key`，这是审计线索）；
      2. 若它原本是 ACTIVE，**清空** `Node.<算法>_public_key`。

    第 2 条以前没做，因为清空就是唯一的"不可用"表达、同时抹掉审计线索。
    现在审计线索在新表里，清空旧列变成安全的、而且是必要的：不清空的话
    大量既有读路径会继续把已回收的公钥当成可用。**失败是静默的** ——
    解密照样成功，只是本该被拒绝的分发成功了。
    """
    if key.status == C.KEY_STATUS_REVOKED:
        return key  # 幂等

    was_active = key.status == C.KEY_STATUS_ACTIVE
    key.mark_revoked(reason)
    key.save(update_fields=['status', 'revoked_at', 'revoked_reason', 'update_datetime'])

    if was_active:
        # 清空物化视图列（含镜像列）。这既是"不可用"的存储层表达，也是**必须做**的：
        # 大量既有读路径直接取 `node.<算法>_public_key`，不清空它们会继续把
        # 已回收的公钥当成可用，而失败是静默的。
        _write_node_column(key.node, key.algorithm, '')
        # ⚠️ 这里**刻意不动** `Node.status`。曾经想把它打回"待初始化"，但两个方向都错：
        #   1. 撤一把算法（比如 KYBER）不等于节点没初始化 —— 另外三把还在。
        #      `Node.status` 是**整节点**的状态，表达不了"某个算法缺一把主版本"；
        #   2. 那个值也不对：`Node.status` 取小写 `active` / `PENDING_INIT`，
        #      而 `KEY_STATUS_ACTIVE` 是 `'ACTIVE'` —— 拿它去 filter 恒不命中
        #      （静默空操作），写进去的 `'pending'` 又不在 choices 里。
        #      两者都不报错，只让节点从 `status='active'` 与 `status='PENDING_INIT'`
        #      两个统计里同时消失（security_monitor_views / views 都在数）。
        # 节点的状态处置与"回收后已建立的会话怎么办"属于 KMS-007，
        # 需要跨算法信息，在存储层这一个方法里做不完整。

    return key


def current_key(node: Node, algorithm: str) -> Optional[NodeLongTermKey]:
    """取该算法当前生产中的版本。没有则 None —— **不抛异常**。

    给"展示用"的调用方（页面要能显示"这个算法还没登记"）。需要"必须存在"
    的调用方用 `require_usable_key`。
    """
    return NodeLongTermKey.objects.filter(
        node=node, algorithm=C.canonical_algorithm(algorithm),
        status=C.KEY_STATUS_ACTIVE,
    ).first()


def _no_current_key_error(candidates, name: str) -> C.ContractError:
    """没有可用版本时，构造一个**能区分原因**的错误（计划 §7 阶段 2）。

    区分"回收了"与"从来没有"是有用的：前者要提示管理员换一把，后者要提示
    节点先完成初始化。在这之前两者都只是 `msg` 里的一句中文，调用方要区分
    只能去匹配文案 —— 改文案即破坏契约。

    三种原因（回收 / 过期 / 从来没有）在处置上是三条不同的路：
    换密钥、续期或换版本、先去初始化。所以错误码必须区分，而不是都报"不存在"。
    """
    if candidates.filter(status=C.KEY_STATUS_REVOKED).exists():
        return C.ContractError(
            f'{name} 密钥已回收，没有可用的版本', code=C.ERR_KEY_REVOKED,
        )
    # status=EXPIRED 或 expires_at 已过。注意后者包含 NULL 安全：
    # `expires_at__lte=now` 不会命中 expires_at 为 NULL 的行。
    if candidates.filter(
        Q(status=C.KEY_STATUS_EXPIRED) | Q(expires_at__lte=timezone.now())
    ).exists():
        return C.ContractError(f'{name} 密钥已过期', code=C.ERR_KEY_EXPIRED)
    return C.ContractError(f'{name} 密钥不存在', code=C.ERR_KEY_NOT_FOUND)


def require_usable_key(node: Node, algorithm: str, *, for_new_work: bool = True) -> NodeLongTermKey:
    """取该算法可用版本；不可用则抛**带错误码**的异常。

    `for_new_work=True` 用于"要产生新信封"的路径 —— 只认生产版本（ACTIVE）；
    `for_new_work=False` 用于"解已存在的信封" —— 生产版本不可用时**退到最近的
    历史版本**。这不是宽松：旧信封是按**当时那一版公钥**封的，生产版本早已换代，
    只查 ACTIVE 会让它报 `KEY_NOT_FOUND`，而那一版明明在库里、也明明还该能解。

    可用性一律由 `NodeLongTermKey.allows_new_work` / `allows_unwrap` 判定，
    这里不另写一套状态判断：那两处已与 `api_contract` 的状态集合绑定，分头写
    会各自漂移，而漂移的表现是"本该拒绝的通过了"。

    抛出的错误码是计划 §7 阶段 2 要求的"回收后的接口返回明确错误码"：
    `KEY_NOT_FOUND` / `KEY_REVOKED` / `KEY_EXPIRED`。
    """
    name = C.canonical_algorithm(algorithm)
    candidates = NodeLongTermKey.objects.filter(node=node, algorithm=name)

    if for_new_work:
        key = candidates.filter(status=C.KEY_STATUS_ACTIVE).first()
        if key is None:
            raise _no_current_key_error(candidates, name)
        if not key.allows_new_work:
            # status 已经是 ACTIVE，唯一能让 allows_new_work 变 False 的是过期。
            # 错误码要具体到"过期"：调用方据此决定是换密钥还是续期。
            raise C.ContractError(f'{name} 密钥已过期', code=C.ERR_KEY_EXPIRED)
        return key

    # 解旧信封：按登记时间从新到旧取第一个允许解封的版本（生产版本优先，
    # 它降级/过期后 RETIRED 的上一版仍然可用）。
    #   * 用 `-id` 而不是模型默认的 `-key_version`：跨 key_id 比版本号没有意义
    #     （旧密钥的 v3 可能比新密钥的 v1 更早）；
    #   * REVOKED 不会被选中 —— `allows_unwrap` 对它返回 False。
    key = next((k for k in candidates.order_by('-id') if k.allows_unwrap), None)
    if key is None:
        raise _no_current_key_error(candidates, name)
    return key


def revoke_keys_for_node(node: Node, reason: str = '', algorithm: str = '') -> int:
    """回收一个节点的全部（或指定算法的）未回收长期密钥。返回条数。

    节点被禁用/删除时调用。逐个走 `revoke_public_key` 而不是批量 update ——
    因为"清空旧列"这个副作用只有在 ACTIVE 那一把上才需要发生，批量 update
    会把每条都当 ACTIVE 处理。
    """
    qs = NodeLongTermKey.objects.filter(node=node).exclude(status=C.KEY_STATUS_REVOKED)
    if algorithm:
        qs = qs.filter(algorithm=C.canonical_algorithm(algorithm))
    count = 0
    for key in list(qs):
        revoke_public_key(key, reason)
        count += 1
    return count


__all__ = [
    'REGISTRABLE_ALGORITHMS',
    'hash_public_key', 'new_key_id',
    'register_public_key', 'rotate_public_key', 'revoke_public_key',
    'current_key', 'require_usable_key', 'revoke_keys_for_node',
]
