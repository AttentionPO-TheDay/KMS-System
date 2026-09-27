# -*- coding: utf-8 -*-
"""节点多级授权（阶段 7 / 文档 §8.4）。

等级定义（文档 §8.4）：
    L1  查询
    L2  查询 + 生成 + 分发
    L3  查询 + 生成 + 分发 + 更新 + 回收

管理员创建 / 编辑节点时设置 `permission_level`（阶段 2 已落字段与展示）。

为什么需要这个模块
----------------
`permission_level` 此前**只存不用** —— 字段在、UI 显示得出、但没有任何入口
校验它。那等于给用户一个可以设置却不起作用的开关，比没有这个字段更糟：
使用者会以为自己已经限制了权限。

设计要点
-------
**按"能力"而非"等级"判断。** 调用方写 `require_level(node, CAP_ROTATE)`，
而不是 `node.permission_level >= 'L2'` —— 后者把等级与能力的对应关系散落到
每个调用点，日后要调整"哪些等级能做轮换"得满仓库改；而且字符串比较
（'L1' < 'L3'）看着对、实则依赖命名的字典序，改个名就悄悄失效。

**未知等级按最小权限处理**：`permission_level` 为空或不在表内时，只当 L1。
与前端 `resolvePrincipalType()` 的取舍一致 —— 配置缺失时宁可不放行，
也不要因为"没读到配置"而给出超出预期的权限。
"""

from __future__ import annotations

from typing import Dict, FrozenSet

#: 能力标识。恒定不变，便于审计日志与前端映射。
CAP_QUERY = 'query'          # 查看自己的密钥/分发记录
CAP_GENERATE = 'generate'    # 生成新密钥
CAP_DISTRIBUTE = 'distribute'  # 发起分发、建立会话
CAP_ROTATE = 'rotate'        # 更新（轮换）
CAP_REVOKE = 'revoke'        # 回收

#: 等级 → 能力集合。文档 §8.4 的定义直接落在这里，是唯一的真实来源。
LEVEL_CAPABILITIES: Dict[str, FrozenSet[str]] = {
    'L1': frozenset({CAP_QUERY}),
    'L2': frozenset({CAP_QUERY, CAP_GENERATE, CAP_DISTRIBUTE}),
    'L3': frozenset({CAP_QUERY, CAP_GENERATE, CAP_DISTRIBUTE, CAP_ROTATE, CAP_REVOKE}),
}

#: 等级展示名（与 models.Node.permission_level 的 choices 保持一致）
LEVEL_LABELS = {
    'L1': '查询',
    'L2': '查询+生成+分发',
    'L3': '查询+生成+分发+更新+回收',
}

#: 配置缺失时的兜底等级（最小权限）
DEFAULT_LEVEL = 'L1'


class NodePermissionError(Exception):
    """节点权限不足。

    携带结构化信息，让接口层能给出**可执行**的提示
    （"需要 L3，当前 L1" 比 "无权限" 有用得多）。
    """

    def __init__(self, required_capability: str, current_level: str):
        self.required_capability = required_capability
        self.current_level = current_level
        super().__init__(
            f'节点权限不足：需要「{capability_label(required_capability)}」能力，'
            f'当前等级 {current_level}（{LEVEL_LABELS.get(current_level, "未知")}）'
        )


def capability_label(capability: str) -> str:
    return {
        CAP_QUERY: '查询',
        CAP_GENERATE: '生成密钥',
        CAP_DISTRIBUTE: '发起分发',
        CAP_ROTATE: '更新密钥',
        CAP_REVOKE: '回收密钥',
    }.get(capability, capability)


def normalize_level(raw) -> str:
    """把任意输入归一到已知等级；未知一律降为 DEFAULT_LEVEL。

    ⚠️ 这里刻意**不抛异常**：`permission_level` 是管理员填的配置项，
    历史数据里可能有空值或拼写错误。为一条配置瑕疵让整个节点无法登录，
    代价远大于"先按最小权限放行、由运维去修配置"。
    """
    level = (str(raw) if raw is not None else '').strip().upper()
    return level if level in LEVEL_CAPABILITIES else DEFAULT_LEVEL


def capabilities_of(raw) -> FrozenSet[str]:
    return LEVEL_CAPABILITIES[normalize_level(raw)]


def has_capability(raw, capability: str) -> bool:
    return capability in capabilities_of(raw)


def require_capability(node, capability: str) -> None:
    """校验节点具备某能力，不足则抛 `NodePermissionError`。

    传入的是 Node 实例（取它的 permission_level），不是等级字符串 ——
    避免调用方自己先读字段、读错了还不报错。
    """
    level = normalize_level(getattr(node, 'permission_level', None))
    if capability not in LEVEL_CAPABILITIES[level]:
        raise NodePermissionError(capability, level)