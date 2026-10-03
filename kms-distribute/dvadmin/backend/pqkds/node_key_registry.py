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

#: keyId 的字符合集与长度上限。与前端 `key-ref.js` 的可接受集合一致
#: （`node/{nodeId}/{算法}/{keyId}/{版本}` 的 keyId 段），也与模型列宽一致。
_KEY_ID_RE = re.compile(r'[A-Za-z0-9_.-]{1,64}')
_KEY_ID_MAX_LEN = 64


def _validate_key_id(raw) -> str:
    """校验调用方**显式给出**的 keyId。空值表示"未提供"，由本模块铸一个新的。

    ⚠️ 刻意**拒绝而不 trim**：本地 keyRef 的 keyId 段就是调用方给的原文
       （`key-ref.js` 的 `requireRefPart` 同样拒绝首尾空白）。这里若静默
       `strip()`，服务端记录的 keyId 与节点本地的引用会变成两个不同的 id ——
       而两处各自"看起来都对"，只有等到按引用找密钥时才现形。
    """
    text = str(raw if raw is not None else '')
    if not text:
        return ''
    if text != text.strip():
        raise C.ContractError(
            'keyId 首尾不能有空白（不做静默更正：本地 keyRef 用的是原文，'
            'trim 会让服务端记录与节点本地引用指向两个不同的 id）',
            code=C.ERR_INVALID_PARAMETER,
        )
    if not _KEY_ID_RE.fullmatch(text):
        raise C.ContractError(
            f'keyId 只允许字母、数字与 _ . -，长度 1~{_KEY_ID_MAX_LEN}：{text!r}。'
            '尤其不能含 "/" —— keyRef 按 / 切段，切错段不报错，只会找不到密钥',
            code=C.ERR_INVALID_PARAMETER,
        )
    return text


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
    suffix = uuid.uuid4().hex[:8]
    # 列宽就是 64（与 `_validate_key_id` 同一上限）：节点编号很长时整串会超，
    # 超了在 MySQL 严格模式下是插入报错、在非严格模式下是静默截断 ——
    # 后者更糟（截断后的 keyId 与节点本地引用不再相等）。所以在这里收口：
    # 截的只是**可读部分**，随机后缀与算法名完整保留，唯一性不受影响。
    room = _KEY_ID_MAX_LEN - len(name) - len(suffix) - 2
    if len(safe_node) > room:
        safe_node = safe_node[:max(room, 1)]
    return f'{safe_node}-{name}-{suffix}'


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
    _via_rotate: bool = False,
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
    kid = _validate_key_id(key_id)

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

    # ⚠️ 显式 keyId，且该 keyId 在本节点本算法**已有别的版本**时，这里其实是在给
    #    一把已存在的逻辑密钥加版本 —— 那是 rotate 的语义，必须走
    #    `rotate_public_key` 的三道校验（回收终态 / 生产槽位归属 / 逐版递增）。
    #
    #    登记口放行会造成两种**静默**坏结果（都是判据②③要防的）：
    #      * 已回收的 keyId 被重新置为 ACTIVE —— 审计里那一行带着 `revoked_at`，
    #        业务上却又能用了；回收是终态这件事只在前端和 rotate 口成立；
    #      * 把当前在产那把降级、换成调用方指定的另一把，而请求返回"已登记" ——
    #        请求方看不出自己刚刚换掉了生产版本。
    #
    #    为什么能确认调用方是"加版本"而不是"新登记"：走到这里说明
    #    (kid, version) 这一行**不存在**（存在时上面已在 224-234 行返回或抛错），
    #    而同一个 kid 的**其它版本**存在。
    #
    # ⚠️ `_via_rotate` 不是"跳过校验"，是"校验已经做过了"。
    #
    #    上一条判断**无法从参数本身推断出调用方是谁**：`rotate_public_key` 落库时
    #    正是转调本函数，它出现时必然"同 kid 已有别的版本"—— 与上面要拦的那种
    #    绕过，在库里的样子**一模一样**。存储层只能由调用方声明意图：
    #      * `_via_rotate=False`（默认，也是唯一的外部取值）—— 调用方是登记口或
    #        直接调用方，它没跑过那三道校验，所以这里拦；
    #      * `_via_rotate=True` —— 只有 `rotate_public_key` 会传，它在转调之前
    #        已经校验过回收终态、生产槽位归属与逐版递增。
    #
    #    曾经这里只写了"同 kid 已有别的版本"，本意是拦登记口，实际把 rotate
    #    自己的每一次合法更新也拦下了：4 组自测同时失败，报的还是"请走 rotate"，
    #    看起来像调用方用错了。要删掉 `_via_rotate` 之前先想清楚 —— 删掉它，
    #    登记口就能复活已回收的密钥、把在产那把换成调用方手里那把。
    if kid and not _via_rotate and NodeLongTermKey.objects.filter(
        node=node, algorithm=name, key_id=kid,
    ).exists():
        raise C.ContractError(
            f'{name} 密钥 {kid} 已登记过；要增加版本请走 rotate（rotate=true）——'
            f'登记路径不做回收终态、生产槽位与逐版递增的校验，'
            f'从这里加版本会绕过它们',
            code=C.ERR_KEY_VERSION_MISMATCH,
        )

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


def _as_version(raw) -> int:
    """版本号只接受**整数**或纯数字字符串。**不做 `int()` 兜底**。

    `int(1.9)→1`、`int(True)→1` 都是"调用方以为说的是 X、实际记下的是 Y"，
    而版本号正是 keyRef 的末段与信封要引用的东西 —— 错一位不报错，
    只是从此找不到密钥。规则与 `node_service.store_node_public_key` 一致；
    那里校验的是 HTTP 入参，这里守的是本函数的入参（可能有直接调用方）。
    """
    if isinstance(raw, bool) or raw is None:
        raise C.ContractError(
            f'keyVersion 应为 ≥1 的整数：{raw!r}', code=C.ERR_INVALID_PARAMETER,
        )
    if isinstance(raw, int):
        value = raw
    else:
        text = str(raw).strip()
        if not text.isdigit():
            raise C.ContractError(
                f'keyVersion 应为 ≥1 的整数：{raw!r}', code=C.ERR_INVALID_PARAMETER,
            )
        value = int(text)
    if value < 1:
        raise C.ContractError(
            f'keyVersion 应为 ≥1 的整数：{raw!r}', code=C.ERR_INVALID_PARAMETER,
        )
    return value


@transaction.atomic
def rotate_public_key(
    node: Node,
    *,
    algorithm: str,
    public_key: str,
    key_id: str,
    key_version,
    security_level: str = '',
    device_id: str = '',
    effective_at=None,
    expires_at=None,
) -> NodeLongTermKey:
    """**更新**：保留 `key_id`，`key_version` 递增，旧版本降级为 RETIRED。

    与 `register_public_key` 的区别就是计划 §6.1 那句"更新保留 key_id，递增
    key_version" —— 更新不是"又生成了一把新密钥"，是"同一把密钥的新版本"。
    这个区别决定了历史信封能不能被追溯回它用的那一版。

    `key_id` 与 `key_version` **都必填**（KMS-006）
    ----------------------------------------------
    计划 §6.1："所有请求显式携带版本；不允许依赖'当前最新版本'的隐式行为"。
    早先这里是"取该算法最新的一行、版本 +1"，正是被禁止的隐式行为，而且
    有三个具体坏结果，**一个都不报错**：

      * 该算法最新一行若已 REVOKED，会在回收记录之上再叠一个 ACTIVE 版本，
        把终态盖掉；
      * 调用方手里的 keyId 与服务端在产那把不同时（换过设备、两次更新
        并发），会把**另一把**密钥降级、把手里这把扶正 —— 生产版本被换掉，
        而请求本身返回成功（阶段 2 判据②要防的就是这个）；
      * 节点已在本地按某个版本号封存了新私钥，服务端若另算一个版本号，
        两边对同一个 keyRef 的记账就此分叉 —— 分叉的表现是"密钥在、查不到"。

    所以版本由**调用方**给出（节点本地先封存、再上报，见更新页与
    `verify-keyupdate-rotate.mjs`），本函数只做三项校验：

      1. `key_id` 必须是本节点该算法**已登记过**的（否则 KEY_NOT_FOUND：
         调用方以为登记过、实际没成功，正是要它回到"先登记"那一步）；
      2. 已回收的 keyId 不能更新（KEY_REVOKED —— 回收是终态，否则审计里
         它带着 `revoked_at`、业务上却又能用，两个说法只有一个是真的）；
      3. 版本必须落在该 keyId 现有最新版本的 `+1`（正常更新）或等于最新
         版本（**重试**：上一次可能已落库而响应丢了，交给
         `register_public_key` 按公钥摘要判"无操作"还是真的版本冲突）。

    通过校验后交给 `register_public_key(activate=True)`：它在一个事务里把旧
    ACTIVE 降级、把新版本置为 ACTIVE、并同步 `Node.<算法>_public_key`。
    这三件事要么一起发生、要么一件都不发生 —— 阶段 2 判据③
    "任一步失败不得把服务端标成 ACTIVE"就落在这个原子块上。
    """
    name = _assert_registrable(algorithm)
    material = str(public_key or '').strip()
    if not material:
        raise C.ContractError('公钥为空', code=C.ERR_INVALID_PARAMETER)

    kid = _validate_key_id(key_id)
    if not kid:
        raise C.ContractError(
            '更新必须显式携带 keyId：服务端不再替你推断"要更新哪一把"——'
            '推断可能更新到与本机不同的那把密钥上，而请求会成功',
            code=C.ERR_INVALID_PARAMETER,
        )
    version = _as_version(key_version)

    latest = (NodeLongTermKey.objects
              .filter(node=node, algorithm=name, key_id=kid)
              .order_by('-key_version', '-id').first())
    if latest is None:
        raise C.ContractError(
            f'{name} 密钥 {kid} 在本节点没有登记记录，无法更新；请先登记公钥',
            code=C.ERR_KEY_NOT_FOUND,
        )
    if latest.status == C.KEY_STATUS_REVOKED:
        raise C.ContractError(
            f'{name} 密钥 {kid} 已回收（终态），不能更新；'
            '要恢复服务请在本机生成新的逻辑密钥（新 keyId）后重新登记',
            code=C.ERR_KEY_REVOKED,
        )

    # 生产槽位归属：该算法在产的那把必须**就是**本次要更新的 keyId。
    # 不是的话，这次"更新"会把它降级，生产版本被换成调用方手里那把 ——
    # 而当前在产那把可能是本机刚生成的新密钥、也可能属于另一台设备。
    active = NodeLongTermKey.objects.filter(
        node=node, algorithm=name, status=C.KEY_STATUS_ACTIVE,
    ).first()
    if active is not None and active.key_id != kid:
        raise C.ContractError(
            f'{name} 当前生产版本是 {active.key_id} v{active.key_version}，'
            f'不是请求要更新的 {kid}；请刷新后基于生产版本再更新',
            code=C.ERR_KEY_VERSION_MISMATCH,
        )

    if version == latest.key_version:
        # 重试路径：上一次更新可能已经落库、只是响应没有到达。
        # 公钥摘要相同 → `register_public_key` 返回已有行（无操作）；
        # 摘要不同 → 同 (keyId, 版本) 两把公钥，是真冲突，报版本不符。
        pass
    elif version == latest.key_version + 1:
        pass
    elif version < latest.key_version:
        raise C.ContractError(
            f'{name} 密钥 {kid} 已有 v{latest.key_version}，请求的 v{version} 更旧；'
            '版本只增不减，请刷新后基于最新版本再更新',
            code=C.ERR_KEY_VERSION_MISMATCH,
        )
    else:
        raise C.ContractError(
            f'{name} 密钥 {kid} 当前最新是 v{latest.key_version}，'
            f'请求的 v{version} 跨过了 v{latest.key_version + 1}；'
            '版本必须逐版递增 —— 跳跃会让中间版本在历史里凭空消失',
            code=C.ERR_KEY_VERSION_MISMATCH,
        )

    # `_via_rotate=True` 是这个标志**唯一**的传值点：上面那三道校验刚刚在本函数里跑完，
    # 接下来这一步只是落库。不传的话 `register_public_key` 会把每一次合法更新都判成
    # "登记口试图给已有 keyId 加版本" —— 它拿到的参数与那种绕过**长得一模一样**
    # （见那里的说明），分辨不出来只能由调用方声明。
    return register_public_key(
        node, algorithm=name, public_key=material,
        key_id=kid,
        key_version=version,
        security_level=security_level or latest.security_level,
        device_id=device_id,
        effective_at=effective_at,
        expires_at=expires_at,
        _via_rotate=True,
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
