# -*- coding: utf-8 -*-
"""冻结契约：算法枚举、状态枚举、错误码（计划 §7 阶段 0 / KMS-002）。

这个模块为什么单独存在
----------------------
在这之前，同一组取值散落在 `wrappers`、`models`、各 `*_views`、前端下拉里，
每处各写一遍。三处写三遍的后果不是"冗余"，而是**它们会漂移**：

  * `NODE_LEG_ALGORITHMS` 里至今留着 `falcon_lattice` —— 它 2026-09-28 就
    不再作为封装算法了，但没人删得掉，因为一删就要先确认没有读路径在用；
  * 前端 `USER_LEG_ALGORITHMS = ['SM2','SSCL']` 与后端 `frozenset({'SM2','SSCL'})`
    是两份独立的字面量，改一处不会提醒另一处；
  * 错误码此前根本不存在 —— 拒绝只体现为"HTTP 200 + msg 里一句话"，
    调用方要判断失败原因只能**匹配文案**，改一个字就断。

所以本模块是这些取值的**唯一来源**。规则：

  1. 新代码不得再写字面量算法名，一律引用本模块常量；
  2. 前端对应物在 `kms-updatedel/front/src/utils/crypto/key-ref.js` 与
     `constants/contract.js`（同一套取值，改一处要改两处 —— 跨语言没有
     共享常量的办法，所以两边都写了"改一处要改两处"的提示）；
  3. 本模块**只放取值和纯函数，不 import 任何业务模块** —— 否则会被
     循环引用，最后又有人"临时"在别处写一份字面量绕开。

⚠️ 历史取值（LEGACY_*）只允许**读**。任何把它们放进白名单的改动，
   都等于让"Falcon 保护 SM4"这条已被否定的设计从后门回来。
"""

from __future__ import annotations

from typing import Dict, Optional, Tuple

# ---------------------------------------------------------------------------
# 一、算法：谁能保护 SM4，谁只能签名（计划 §3）
# ---------------------------------------------------------------------------
# 这张表是计划 §3「固定密码学职责」的代码化。之前的问题是**角色混用**：
# Falcon 既被当成封装算法（`falcon_lattice` 在 `NODE_WRAPPING_CHOICES` 里），
# 又被当成签名算法（`falcon_sign_private_key`）。混用的具体后果是：
# 拿一把签名密钥去"解封"，密码学上根本走不通，而错在哪要等端到端测试才暴露。

#: 可以把 SM4 载荷封给收件人的算法（保护算法）。**新业务只允许这三个。**
PROTECTION_ALGORITHMS: Tuple[str, ...] = ('SM2', 'SSCL', 'KYBER')

#: 只做签名/验签的算法。**不得**出现在保护算法字段里。
SIGNATURE_ALGORITHMS: Tuple[str, ...] = ('FALCON',)

#: 历史遗留的"保护算法"取值。**只读兼容**，新信封一律不得产生。
LEGACY_PROTECTION_ALGORITHMS: Tuple[str, ...] = (
    'FALCON',           # 概念错误：签名算法当封装用
    'FALCON_LATTICE',   # CL-Falcon 格材料，与标准 Falcon 不兼容
    'AES',              # 早期 aes_falcon 会话类型
)

#: `PreDistributedKey.algorithm` / 信封 `wrapping_algorithm` 的历史拼写。
#: 与原实现一致（`wrappers.NODE_WRAPPING_CHOICES`），改这些值会让库里
#: 已有信封**读不出来** —— 它们是数据，不是代码。
WRAPPING_KYBER = 'kyber_kem'
WRAPPING_SM2 = 'gm_sm2'
WRAPPING_SSCL = 'gm_sscl'
LEGACY_WRAPPING_FALCON = 'falcon_lattice'

NODE_WRAPPING_CHOICES: Tuple[str, ...] = (WRAPPING_KYBER, WRAPPING_SM2, WRAPPING_SSCL)
NODE_DEFAULT_WRAPPING = WRAPPING_KYBER

#: 信封 `wrapping_algorithm`（库里那套拼写）→ 规范算法名（本模块那套）。
_WRAPPING_TO_CANONICAL: Dict[str, str] = {
    WRAPPING_KYBER: 'KYBER',
    WRAPPING_SM2: 'SM2',
    WRAPPING_SSCL: 'SSCL',
    LEGACY_WRAPPING_FALCON: 'FALCON',
}

#: 上表的**反查**：规范算法名 → 该算法在库里的全部封装拼写。
#: 由 `_WRAPPING_TO_CANONICAL` 派生而非手抄 —— 手抄的第二份一旦漂移，
#: 表现是"某算法的历史池项匹配不到"，静默少失效一批（不报错）。
_WRAPPINGS_BY_CANONICAL: Dict[str, Tuple[str, ...]] = {
    canonical: tuple(
        wrapping for wrapping, owner in _WRAPPING_TO_CANONICAL.items() if owner == canonical
    )
    for canonical in set(_WRAPPING_TO_CANONICAL.values())
}

#: 规范算法名 → 节点的公钥列名（`models.Node`）。这是**唯一**一份映射：
#: 写入侧由 `node_key_registry._write_node_column` 取用（KMS-004 之后
#: `NodeService._PUBLIC_KEY_COLUMNS` 已删除，不再有第二份）。镜像列
#: （FALCON 还要一并写 `falcon_public_key`）不在本表里 —— 那是存储层
#: 双写的一致性要求，见 `node_key_registry._MIRROR_COLUMNS`。
NODE_PUBLIC_KEY_COLUMN: Dict[str, str] = {
    'KYBER': 'kyber_public_key',
    'SM2': 'gm_public_key',
    'SSCL': 'sscl_public_key',
    'FALCON': 'falcon_sign_public_key',
}

#: 规范算法名 → 私钥列名。**这些列不得再被写入新私钥**（计划 §5.2）。
#: 列出来是为了让"盘点存量私钥"有唯一一份清单，不是因为还能往里写。
NODE_LEGACY_PRIVATE_KEY_COLUMN: Dict[str, str] = {
    'KYBER': 'kyber_private_key',
    'SM2': 'gm_private_key',
    'SSCL': 'sscl_private_key',
    'FALCON': 'falcon_sign_private_key',
}


def canonical_algorithm(value: str) -> str:
    """把各处五花八门的写法收敛成规范算法名（SM2 / SSCL / KYBER / FALCON）。

    接受的输入：`'kyber_kem'`、`'gm_sm2'`、`'cl-falcon'`、`'falcon_lattice'`、
    `' kyber '` … 归一化后统一走本模块的白名单。
    不认识的输入原样大写返回 —— **不抛异常**：调用方多半要做的是
    "判断是否在白名单里"，让它自己去判，比在这里抛要清楚。
    """
    raw = str(value or '').strip()
    if not raw:
        return ''
    lowered = raw.lower().replace('-', '_')
    if lowered in _WRAPPING_TO_CANONICAL:
        return _WRAPPING_TO_CANONICAL[lowered]
    name = raw.upper().replace('CL-', '').replace('CL_', '')
    if name in ('FALCON_LATTICE', 'FALCONLATTICE'):
        return 'FALCON'
    return name


def wrapping_algorithms_for(algorithm: str) -> Tuple[str, ...]:
    """规范算法名 → 它在 `PreDistributedKey` 里可能出现的**全部**拼写。

    用于"按算法家族匹配历史行"（KMS-007 D3 的退化分支）：库里的
    `algorithm` / `wrapping_algorithm` 是**数据**（`kyber_kem` / `gm_sm2` /
    `gm_sscl` / `falcon_lattice` …），而调用方手里通常是规范名
    （`KYBER` / `FALCON`…）。两种拼写直接比会**恒不命中且不报错**，
    表现是"该失效的历史池项还活着"。

    返回值含：
      * 上表的全部封装拼写（FALCON 的 `falcon_lattice`）；
      * **规范名本身**（大写）—— 库里也确实有以规范名写进去的值
        （`LEGACY_PROTECTION_ALGORITHMS` 那一类历史写法）。

    不认识的输入（含空串）返回**空元组**：空集合不会误命中任何行。
    这里刻意不返回"原样大写"—— 那个值在这套表里根本不存在，拿它去查
    等于白查，而且看起来像查过了。
    （`canonical_algorithm` 对不认识的输入原样大写返回、不抛异常，所以
    这里**必须自己按表判一次成员资格**，不能把"返回非空"当成"认识"。）
    """
    canonical = canonical_algorithm(algorithm)
    if canonical not in _WRAPPINGS_BY_CANONICAL:
        return ()
    return _WRAPPINGS_BY_CANONICAL[canonical] + (canonical,)


def is_protection_algorithm(value: str) -> bool:
    """该算法是否可以用于**新**信封的保护算法。"""
    return canonical_algorithm(value) in PROTECTION_ALGORITHMS


def is_legacy_protection_algorithm(value: str) -> bool:
    """是否是"曾经被当成保护算法"的历史取值（只读兼容）。"""
    return canonical_algorithm(value) in LEGACY_PROTECTION_ALGORITHMS


def assert_protection_algorithm(value: str) -> str:
    """校验并返回规范名；不是保护算法时抛 `AlgorithmNotAllowed`。

    接口层用它**在入口处**拒绝，而不是等到封装那一步 —— 失败点离入口越远，
    错误信息里能带上的上下文越少，最后只剩一句"封装失败"。
    """
    name = canonical_algorithm(value)
    if name not in PROTECTION_ALGORITHMS:
        raise AlgorithmNotAllowed(
            f'{value!r} 不能作为 SM4 的保护算法（允许：{"、".join(PROTECTION_ALGORITHMS)}）'
        )
    return name


def algorithm_column(algorithm: str, *, private: bool = False) -> Optional[str]:
    """规范算法名 → `models.Node` 上的公钥（或历史私钥）列名。"""
    name = canonical_algorithm(algorithm)
    table = NODE_LEGACY_PRIVATE_KEY_COLUMN if private else NODE_PUBLIC_KEY_COLUMN
    return table.get(name)


# ---------------------------------------------------------------------------
# 二、长期密钥状态（计划 §6.1）
# ---------------------------------------------------------------------------
# 此前"节点某算法的密钥是什么状态"没有独立表达：`Node.status` 是**节点**的
# 状态（ACTIVE/PENDING/DISABLED），公钥列是**有没有值**。于是"这把公钥已回收"
# 只能靠"把列清空"来表达 —— 而清空同时抹掉了审计线索。
#
# ⚠️ 与 `PreDistributedKey.STATUS_CHOICES` 的区别（很容易看混）：
#    那套描述的是**池项**（一把待消费的 SM4 的份额），
#    这套描述的是**长期密钥**（节点的 SM2/SSCL/Kyber/Falcon 密钥对）。
#    两者都有 REVOKED/EXPIRED，但生命周期毫无关系。

KEY_STATUS_PENDING = 'PENDING'      # 已生成，尚未成为生产版本
KEY_STATUS_ACTIVE = 'ACTIVE'        # 当前生产版本，可被封装/签名/预分配
KEY_STATUS_RETIRED = 'RETIRED'      # 被新版本取代，按策略仍可解旧信封
KEY_STATUS_REVOKED = 'REVOKED'      # 已回收：禁止新封装、新签名、新会话
KEY_STATUS_EXPIRED = 'EXPIRED'      # 超过有效期
KEY_STATUS_LEGACY = 'LEGACY'        # 历史记录，来源不明，只读

KEY_STATUS_CHOICES: Tuple[Tuple[str, str], ...] = (
    (KEY_STATUS_PENDING, '待启用'),
    # ⚠️ ACTIVE 的展示文案是「当前版本」而**不是**「生产中」（2026-10-04 改）：
    #    "生产中"在密钥管理的语境里会被读成"正在生成"（与生成页的「生成中…」
    #    只差一个字），用户看到一个已就绪的密钥标着它，会以为还在生成、
    #    不敢用它分发。而 ACTIVE 的真实语义是"**这一版是当前生产版本**"
    #    （它能开新工作；被它取代的版本叫「已被取代」）。
    #    「当前版本」与「已被取代」「已回收」并列自洽，没有歧义。
    (KEY_STATUS_ACTIVE, '当前版本'),
    (KEY_STATUS_RETIRED, '已被取代'),
    (KEY_STATUS_REVOKED, '已回收'),
    (KEY_STATUS_EXPIRED, '已过期'),
    (KEY_STATUS_LEGACY, '历史记录（只读）'),
)

#: 允许**新**封装/签名/预分配的状态。RETIRED 不在其中：新业务必须用当前生产版本，
#: 旧版本的存在意义只是"解旧信封"。把 RETIRED 放进来会让"回收后禁止新分发"
#: 这条要求失效 —— 而失效是静默的，因为解密照样成功。
KEY_STATUS_USABLE_FOR_NEW_WORK = frozenset({KEY_STATUS_ACTIVE})

#: 允许**解旧信封**的状态。回收（REVOKED）不在其中：回收的语义就是"不许再用"。
KEY_STATUS_USABLE_FOR_UNWRAP = frozenset({
    KEY_STATUS_ACTIVE, KEY_STATUS_RETIRED, KEY_STATUS_EXPIRED,
})


def key_status_allows_unwrap(status: str) -> bool:
    """该状态的密钥是否还能解封**已存在**的信封。

    ⚠️ `LEGACY` 刻意**不在**放行集合里：来源不明的历史记录可能根本没有
       对应私钥（计划 §7 阶段 2「不能假设历史记录都有本地 u」），
       让调用方以为能解、解到一半才发现，比一开始就拒绝更糟。
    """
    return str(status or '').upper() in KEY_STATUS_USABLE_FOR_UNWRAP


def key_status_allows_new_work(status: str) -> bool:
    """该状态的密钥是否还能用于**新**封装 / 新签名 / 新预分配。

    与上面那个函数的差集正是计划 §6.1 那句话：「回收后禁止新封装、新签名、
    新预分配和新会话」。`RETIRED` / `EXPIRED` 允许解旧信封，但不允许产生新信封 ——
    这个区分必须由两个函数表达，用一个函数表达必然要在一处放宽。
    """
    return str(status or '').upper() in KEY_STATUS_USABLE_FOR_NEW_WORK


# ---------------------------------------------------------------------------
# 二之二、池项状态（计划 §7 阶段 5「READY → RESERVED → CONSUMED 不可逆乱跳」）
# ---------------------------------------------------------------------------
# 与上面长期密钥一样，这里也是**状态机表**而不是散落各处的 `if status == ...`：
# 消费路径（`consume_key`）与失效路径（`revoke_pool_items_for_key`）在不
# 同的模块里，任何一侧放宽都会让另一侧的判断失去意义。
#
# ⚠️ KMS-013 的**定夺**：`RESERVED` 是**保留值**，当前没有任何生产写入点，
#    也不应该有 —— 见下方 `POOL_TRANSITIONS` 的说明。把它连同转移表一起
#    写在这里，是为了让"它是一条谁都不走的路"成为**可读的事实**，而不是
#    一个需要翻遍全仓才能确认的疑点。

POOL_READY = 'READY'          # 已预分配，可被会话取用
POOL_RESERVED = 'RESERVED'    # 保留值：从未产生过（见 POOL_TRANSITIONS 说明）
POOL_CONSUMED = 'CONSUMED'    # 已取用：一次性，不可再取
POOL_EXPIRED = 'EXPIRED'      # 超过有效期
POOL_REVOKED = 'REVOKED'      # 依赖的长期密钥已回收（KMS-007 的连带失效）

#: 旧拼写 → 新拼写。库里已有按旧值写入的历史行（'unused' 等），
#: **读取方**必须把两套拼写都算数，否则历史行永远取不出来 ——
#: 现象是"池子里明明有货，却说没有可用的预分配密钥"。
POOL_LEGACY_STATUS_ALIASES: Dict[str, str] = {
    'unused': POOL_READY,
    'used': POOL_CONSUMED,
    'distributed': POOL_CONSUMED,
    'expired': POOL_EXPIRED,
}

#: 状态机允许的池项迁移。**只允许**这些边。
#:
#: 为什么没有 `READY → RESERVED`：
#:   `RESERVED` 要解决的是"我取出来到用上它之间，别被别人抢走"。而当前
#:   消费是**单个事务**里的"选中（FOR UPDATE）→ 标记 CONSUMED"，中间窗口
#:   为零 —— 没有需要预留的时间段，加了它反而会引入一个"预留了但忘了消费"
#:   的新故障态（池项卡在 RESERVED，过期又被 cleanup 忽略）。
#:   计划 §7 阶段 5 原文写的是「READY → RESERVED → CONSUMED 状态不可逆乱跳」；
#:   既然中间站不落地，这条要求在这里的可执行形式就是：**表内没有那两条边，
#:   强行置 RESERVED 会被本表拒绝**（`pool_transition_allowed`），
#:   而不是"没人走"而已。
#:
#: ⚠️ 改这张表之前先问"这条边会不会让人相信一个没发生的动作"：
#:    `REVOKED` 从每个非终态都可到达（回收是外部事实，不产生信任主张）；
#:    `CONSUMED` 只能从 `READY` 到达（它主张"这一项被某次会话用掉了"，
#:    从其它状态到达就是在伪造消费记录）。
POOL_TRANSITIONS: Dict[str, frozenset] = {
    POOL_READY: frozenset({POOL_CONSUMED, POOL_REVOKED, POOL_EXPIRED}),
    POOL_RESERVED: frozenset({POOL_CONSUMED, POOL_REVOKED, POOL_EXPIRED}),
    POOL_CONSUMED: frozenset(),   # 终态：消费是历史事实
    POOL_EXPIRED: frozenset({POOL_REVOKED}),
    POOL_REVOKED: frozenset(),    # 终态
}

#: 终态集合：到达后不再接受任何消费。
POOL_TERMINAL_STATUSES = frozenset({POOL_CONSUMED, POOL_EXPIRED, POOL_REVOKED})

#: 「可用于**新会话**」的判定值集合，只收敛**新逻辑**要写的那一个值。
#: ⚠️ 读取/消费路径还应把 `POOL_LEGACY_STATUS_ALIASES` 里的旧值一并纳入 ——
#:    历史行仍在那里，漏掉它们不会报错，只会静默地把可用项说成不可用。
POOL_STATUS_USABLE_FOR_NEW_WORK = frozenset({POOL_READY})


def normalize_pool_status(status) -> str:
    """池项状态归一：旧拼写 → 新拼写；未知值**原样返回**。

    原样返回未知值（而不是猜一个近似的）是刻意的：池项状态列没有 choices
    之外的写入点，出现未知值说明有第三个写入方 —— 把它猜成 READY 会让
    "来路不明的行"变成"可消费的行"，而那是安全方向的错误。
    """
    text = str(status or '').strip()
    return POOL_LEGACY_STATUS_ALIASES.get(text, text)


def pool_status_allows_new_work(status) -> bool:
    """该池项是否可被**新会话**取用（消费）。旧拼写经归一后判定。"""
    return normalize_pool_status(status) in POOL_STATUS_USABLE_FOR_NEW_WORK


def pool_transition_allowed(current, target) -> bool:
    """`current → target` 是否是合法的池项迁移（两侧都先归一旧拼写）。"""
    return normalize_pool_status(target) in POOL_TRANSITIONS.get(
        normalize_pool_status(current), frozenset()
    )


# ---------------------------------------------------------------------------
# 三、会话状态（计划 §6.3）
# ---------------------------------------------------------------------------
# 原状态机只有 initiated / established / blockchain_recorded / expired / revoked，
# 缺的正是**中间那三步**：验签通过、解封成功、双方确认。缺了它们的后果在
# 计划 §4.4 里写得很直白：分发能创建 initiated，但没有任何界面能把它推进到
# established —— 因为"推进"所需要的证据在模型里无处可放。
#
# ⚠️ `blockchain_recorded` 保留在取值里但**不作为状态流转的一站**：
#    上链是**旁路**（成功与否不影响会话能否建立），把它塞进状态机会导致
#    "链上拥堵 → 会话建不起来"。它继续作为一个独立字段 `chain_tx_hash` 表达。

SESSION_INITIATED = 'initiated'                  # 信封已登记，尚未被接收方处理
SESSION_RECIPIENT_VERIFIED = 'recipient_verified'  # 收件方验签通过
SESSION_KEY_RECOVERED = 'key_recovered'          # 收件方本地解封成功
SESSION_ESTABLISHED = 'established'              # 双方确认持有同一把 K
SESSION_CLOSED = 'closed'                        # 正常关闭
SESSION_EXPIRED = 'expired'
SESSION_REVOKED = 'revoked'

SESSION_STATUS_CHOICES: Tuple[Tuple[str, str], ...] = (
    (SESSION_INITIATED, '已发起'),
    (SESSION_RECIPIENT_VERIFIED, '接收方已验签'),
    (SESSION_KEY_RECOVERED, '接收方已解封'),
    (SESSION_ESTABLISHED, '已建立'),
    (SESSION_CLOSED, '已关闭'),
    (SESSION_EXPIRED, '已过期'),
    (SESSION_REVOKED, '已撤销'),
    ('blockchain_recorded', '已记录到区块链（历史值，旁路事件）'),
)

#: 状态机允许的迁移。**只允许**这些边 —— 其余一律拒绝。
#:
#: 为什么要把这个集合写出来，而不是在各接口里 `if status == ...`：
#: 分散判断必然漏。最危险的一条是 `initiated → established`：
#: 少了它，一条请求就能跳过"验签 + 解封 + 双方确认"全部证据。
#:
#: ⚠️ KMS-012 扩了一条语义：**关闭（`closed`）从每个非终态都可到达**，
#:    而不只是从 `established`。理由：
#:      * 关闭是**放弃动作**、不产生任何信任主张（它不让人相信会话已建立），
#:        所以放开它不会给出任何"跳过证据"的捷径 —— 与
#:        `initiated → established` 那种"伪装成证据齐全"的边性质完全不同；
#:      * 计划 §6.3 的状态图把 closed/expired/revoked 画在同一层（三个终态），
#:        KMS-002 首版只给 established 留了 closed，实际效果是
#:        "一条没走完的会话**没法主动放弃**，只能等过期" —— 而设备丢失、
#:        对方长期不处理这类场景里，"主动关闭、留下明确的终态记录"才是
#:        用户要做的事（过期是时钟触发的，不是人的决定）。
#:    改这条边要连带更新：本表、`node_session_close` 的 allow_from、
#:    会话页的关闭按钮可用性、以及 `doc` 里 KMS-012 的关闭记录。
SESSION_TRANSITIONS: Dict[str, frozenset] = {
    SESSION_INITIATED: frozenset({
        SESSION_RECIPIENT_VERIFIED, SESSION_CLOSED, SESSION_EXPIRED, SESSION_REVOKED,
    }),
    SESSION_RECIPIENT_VERIFIED: frozenset({
        SESSION_KEY_RECOVERED, SESSION_CLOSED, SESSION_EXPIRED, SESSION_REVOKED,
    }),
    SESSION_KEY_RECOVERED: frozenset({
        SESSION_ESTABLISHED, SESSION_CLOSED, SESSION_EXPIRED, SESSION_REVOKED,
    }),
    SESSION_ESTABLISHED: frozenset({SESSION_CLOSED, SESSION_EXPIRED, SESSION_REVOKED}),
    # 终态：不再迁出。会话关闭后要重新通信就重新分发 ——
    # 允许"关闭→established"等于让关闭变成可撤销的装饰。
    SESSION_CLOSED: frozenset(),
    SESSION_EXPIRED: frozenset(),
    SESSION_REVOKED: frozenset(),
}

#: 终态集合：到达后不再接受任何确认或状态变更。
SESSION_TERMINAL_STATUSES = frozenset({SESSION_CLOSED, SESSION_EXPIRED, SESSION_REVOKED})


def session_status_allows_confirm(status: str) -> bool:
    """该状态下是否还接受**确认**提交。

    刻意只允许到 `key_recovered` 为止：`established` 之后再来一条确认，
    语义上是"重复提交"（应当幂等成功）还是"换了一把 K"，从请求本身分不出来。
    所以由接口层对它做幂等处理，而不是在这里放行。
    """
    return str(status or '').lower() in (
        SESSION_INITIATED, SESSION_RECIPIENT_VERIFIED, SESSION_KEY_RECOVERED,
    )


def session_transition_allowed(current: str, target: str) -> bool:
    """`current → target` 是否是合法迁移。"""
    return str(target or '').lower() in SESSION_TRANSITIONS.get(str(current or '').lower(), frozenset())


# ---------------------------------------------------------------------------
# 四、错误码（计划 §7 阶段 2「回收后的接口返回明确错误码」）
# ---------------------------------------------------------------------------
# 在此之前，失败一律是 HTTP 200 + `msg` 里一句中文。调用方要区分
# "密钥被回收了"和"密钥不存在"，只能去匹配那句话 —— 改文案即破坏契约，
# 而且前端根本没法据此给出处置建议（该找管理员？该重新初始化？）：
#
#     '该节点的密钥已与另一台设备绑定。当前设备上没有对应私钥……'   （设备不一致）
#     '公钥为空'                                                  （参数错）
#
# 两者都应当是 4xx，且**可编程区分**。错误码是那个区分点。

ERR_KEY_NOT_FOUND = 'KEY_NOT_FOUND'
ERR_KEY_REVOKED = 'KEY_REVOKED'
ERR_KEY_EXPIRED = 'KEY_EXPIRED'
ERR_KEY_VERSION_MISMATCH = 'KEY_VERSION_MISMATCH'
ERR_KEY_LOCAL_MISSING = 'KEY_LOCAL_MISSING'        # 本机没有对应私钥（换了设备 / 清过站点数据）
ERR_ALGORITHM_NOT_ALLOWED = 'ALGORITHM_NOT_ALLOWED'
ERR_SIGNATURE_INVALID = 'SIGNATURE_INVALID'
ERR_SIGNATURE_REQUIRED = 'SIGNATURE_REQUIRED'      # 发送方本地没有 Falcon 私钥
ERR_ENVELOPE_TAMPERED = 'ENVELOPE_TAMPERED'        # 摘要不符
ERR_ENVELOPE_EXPIRED = 'ENVELOPE_EXPIRED'
ERR_ENVELOPE_NOT_FOUND = 'ENVELOPE_NOT_FOUND'
ERR_NOT_ENVELOPE_RECIPIENT = 'NOT_ENVELOPE_RECIPIENT'
ERR_SESSION_NOT_FOUND = 'SESSION_NOT_FOUND'
ERR_SESSION_STATE_INVALID = 'SESSION_STATE_INVALID'
ERR_SESSION_TERMINAL = 'SESSION_TERMINAL'
ERR_PROOF_MISMATCH = 'PROOF_MISMATCH'              # 双方 proof 不一致
ERR_NOT_SESSION_PARTY = 'NOT_SESSION_PARTY'
ERR_NOT_AUTHORIZED = 'NOT_AUTHORIZED'              # 域/授权关系不允许
ERR_DEVICE_MISMATCH = 'DEVICE_MISMATCH'
ERR_POOL_ITEM_CONSUMED = 'POOL_ITEM_CONSUMED'
ERR_POOL_ITEM_RESERVED = 'POOL_ITEM_RESERVED'
ERR_POOL_ITEM_UNAVAILABLE = 'POOL_ITEM_UNAVAILABLE'
ERR_INVALID_PARAMETER = 'INVALID_PARAMETER'

#: 错误码 → HTTP 状态。**两套响应约定**（`code/msg` 恒 200 与 `code/message` 真状态码）
#: 并存是既有事实，本表不强行统一 —— 它只回答"这个错误码对应哪个 HTTP 状态"，
#: 用哪套约定由所在命名空间决定（见 doc/kms-callsite-inventory.md）。
ERROR_HTTP_STATUS: Dict[str, int] = {
    ERR_KEY_NOT_FOUND: 404,
    ERR_KEY_REVOKED: 409,
    ERR_KEY_EXPIRED: 409,
    ERR_KEY_VERSION_MISMATCH: 409,
    ERR_KEY_LOCAL_MISSING: 409,
    ERR_ALGORITHM_NOT_ALLOWED: 400,
    ERR_SIGNATURE_INVALID: 400,
    ERR_SIGNATURE_REQUIRED: 409,
    ERR_ENVELOPE_TAMPERED: 400,
    ERR_ENVELOPE_EXPIRED: 410,
    ERR_ENVELOPE_NOT_FOUND: 404,
    ERR_NOT_ENVELOPE_RECIPIENT: 403,
    ERR_SESSION_NOT_FOUND: 404,
    ERR_SESSION_STATE_INVALID: 409,
    ERR_SESSION_TERMINAL: 409,
    ERR_PROOF_MISMATCH: 409,
    ERR_NOT_SESSION_PARTY: 403,
    ERR_NOT_AUTHORIZED: 403,
    ERR_DEVICE_MISMATCH: 409,
    ERR_POOL_ITEM_CONSUMED: 409,
    ERR_POOL_ITEM_RESERVED: 409,
    ERR_POOL_ITEM_UNAVAILABLE: 409,
    ERR_INVALID_PARAMETER: 400,
}

#: 错误码 → 面向节点的处置提示。写在这里而不是各接口里，是为了让
#: 同一个错误在任何页面上给出的下一步**一致** —— 否则用户在 A 页面看到
#: "请重新初始化"、在 B 页面看到"请联系管理员"，而实际情况只有一个。
ERROR_HINTS: Dict[str, str] = {
    ERR_KEY_REVOKED: '该密钥已回收，不能用于新的分发或签名。请先由节点重新生成并登记新版本。',
    ERR_KEY_EXPIRED: '该密钥已过期，请先生成新版本，或延长有效期。',
    ERR_KEY_VERSION_MISMATCH: '请求指定的密钥版本与该算法当前的可用版本不一致，请刷新后重选。',
    ERR_KEY_LOCAL_MISSING: (
        '本机没有这把密钥的私钥。按设计私钥只在生成它的那台设备上、不从服务器恢复 —— '
        '请改回原设备，或在本机重新初始化并回收旧密钥。'
    ),
    ERR_SIGNATURE_REQUIRED: '本机没有可用于签名的 Falcon 私钥，无法发送。请在本机生成 Falcon 密钥后再试。',
    ERR_ENVELOPE_TAMPERED: '信封内容与签名时的摘要不一致，已拒绝。这可能是一次篡改，请联系管理员核查。',
    ERR_NOT_ENVELOPE_RECIPIENT: '该信封不是发给当前节点的，无法读取。',
    ERR_PROOF_MISMATCH: '双方提交的持有证明不一致，说明两边解出的会话密钥不是同一把。会话保持未建立状态。',
    ERR_ALGORITHM_NOT_ALLOWED: 'Falcon 只用于签名，不能作为 SM4 的保护算法。可选：SM2、SSCL、Kyber。',
    ERR_POOL_ITEM_CONSUMED: '该池项已被消费，不能重复使用。请从密钥池中另取一项。',
}


class ContractError(Exception):
    """契约层错误基类。带 `code`，由接口层翻成响应。"""

    code = ERR_INVALID_PARAMETER

    def __init__(self, message: str = '', code: Optional[str] = None):
        super().__init__(message or self.code)
        if code:
            self.code = code
        self.message = message or self.code

    @property
    def http_status(self) -> int:
        return ERROR_HTTP_STATUS.get(self.code, 400)

    @property
    def hint(self) -> str:
        return ERROR_HINTS.get(self.code, '')


class AlgorithmNotAllowed(ContractError):
    """该算法不允许用于这个用途（计划 §3 白名单）。接口层应据此返回 400。"""

    code = ERR_ALGORITHM_NOT_ALLOWED


class KeyNotUsable(ContractError):
    """密钥存在但当前状态不允许该操作（回收 / 过期 / 版本不符）。"""

    code = ERR_KEY_REVOKED


class SignatureInvalid(ContractError):
    """签名验证失败。**验签失败不得交出密文**（计划 §6.2）。"""

    code = ERR_SIGNATURE_INVALID


class SessionTransitionInvalid(ContractError):
    """非法会话状态迁移（计划 §6.3 状态机）。"""

    code = ERR_SESSION_STATE_INVALID


__all__ = [
    'PROTECTION_ALGORITHMS', 'SIGNATURE_ALGORITHMS', 'LEGACY_PROTECTION_ALGORITHMS',
    'WRAPPING_KYBER', 'WRAPPING_SM2', 'WRAPPING_SSCL', 'LEGACY_WRAPPING_FALCON',
    'NODE_WRAPPING_CHOICES', 'NODE_DEFAULT_WRAPPING',
    'NODE_PUBLIC_KEY_COLUMN', 'NODE_LEGACY_PRIVATE_KEY_COLUMN',
    'canonical_algorithm', 'wrapping_algorithms_for',
    'is_protection_algorithm', 'is_legacy_protection_algorithm',
    'assert_protection_algorithm', 'algorithm_column',
    'KEY_STATUS_PENDING', 'KEY_STATUS_ACTIVE', 'KEY_STATUS_RETIRED', 'KEY_STATUS_REVOKED',
    'KEY_STATUS_EXPIRED', 'KEY_STATUS_LEGACY', 'KEY_STATUS_CHOICES',
    'KEY_STATUS_USABLE_FOR_NEW_WORK', 'KEY_STATUS_USABLE_FOR_UNWRAP',
    'key_status_allows_unwrap', 'key_status_allows_new_work',
    'SESSION_INITIATED', 'SESSION_RECIPIENT_VERIFIED', 'SESSION_KEY_RECOVERED',
    'SESSION_ESTABLISHED', 'SESSION_CLOSED', 'SESSION_EXPIRED', 'SESSION_REVOKED',
    'SESSION_STATUS_CHOICES', 'SESSION_TRANSITIONS', 'SESSION_TERMINAL_STATUSES',
    'session_status_allows_confirm', 'session_transition_allowed',
    'ERR_KEY_NOT_FOUND', 'ERR_KEY_REVOKED', 'ERR_KEY_EXPIRED', 'ERR_KEY_VERSION_MISMATCH',
    'ERR_KEY_LOCAL_MISSING', 'ERR_ALGORITHM_NOT_ALLOWED', 'ERR_SIGNATURE_INVALID',
    'ERR_SIGNATURE_REQUIRED', 'ERR_ENVELOPE_TAMPERED', 'ERR_ENVELOPE_EXPIRED',
    'ERR_ENVELOPE_NOT_FOUND', 'ERR_NOT_ENVELOPE_RECIPIENT', 'ERR_SESSION_NOT_FOUND',
    'ERR_SESSION_STATE_INVALID', 'ERR_SESSION_TERMINAL', 'ERR_PROOF_MISMATCH',
    'ERR_NOT_SESSION_PARTY', 'ERR_NOT_AUTHORIZED', 'ERR_DEVICE_MISMATCH',
    'ERR_POOL_ITEM_CONSUMED', 'ERR_POOL_ITEM_RESERVED', 'ERR_POOL_ITEM_UNAVAILABLE',
    'ERR_INVALID_PARAMETER', 'ERROR_HTTP_STATUS', 'ERROR_HINTS',
    'ContractError', 'AlgorithmNotAllowed', 'KeyNotUsable', 'SignatureInvalid',
    'SessionTransitionInvalid',
]
