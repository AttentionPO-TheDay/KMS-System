"""
节点 ↔ 登录账号 的映射维护（阶段 2）。

设计要点
--------
文档 §2.3 要求 `Node 1 ── 1 sys_user`，但两者分属**不同 schema**：
  * Node 在 `falcon_kds.dvadmin_pqkds_nodes`（本 Django 应用管的库）
  * sys_user 在 `kms.sys_user`（RuoYi / Java 后端管的库）

  两者在**同一个 MySQL 实例**（容器 kms_mysql）里，只是 schema 不同。
  所以这不是分布式事务问题 —— MySQL 原生支持跨 schema 写入，
  且 Django 的 `transaction.atomic()` 关掉 autocommit 后，同一条连接上的
  跨 schema INSERT 参与同一个事务。（此前文档 §13 把它列为"跨库写入无先例、
  最大技术不确定点"，经核实是把"同实例跨 schema"误当成了"跨实例"。）

  唯一建不出来的东西是**外键**：MySQL 的 FK 不能跨 schema。因此这里用
  `sys_user_id` 存主键值，一致性由本模块维护，而不是靠数据库约束。

为什么节点账号不是管理员
------------------------
`principal_type='NODE'`、`role_level=2`、只挂普通角色。节点是**业务使用者**，
不是平台管理员（文档 §2.1）。它拿到的权限应当只够做密钥业务，
不该能管理用户/角色。⚠️ 目前 role_id=2 这个「普通角色」沿用了 RuoYi 的
初始授权，里面**含 system:role:* 等管理权限**（2026-09-27 实测），
属于阶段 2 要收口的项 —— 见 32_trim_common_role_grants.sql。
在那一项完成前，节点账号虽然被标成 NODE，后端权限仍偏大。

密码
----
**节点没有可用口令**（2026-09-30 改）。文档 §3 的节点登录设计是
「节点名称 + 一次性激活码」，之后走设备凭据挑战-应答（§5），本来就没有口令。

原先这里复用 RuoYi 的 `admin123` 哈希，后果是**知道 node_id 就能登录任意节点**
（`node_id` 是可枚举的，口令是公开常量）—— 那不是弱口令，等于没有认证。

现在给每个节点账号写一个**随机、且从不以任何形式披露**的 BCrypt 哈希：
  * 口令明文从未存在过（随机字节直接哈希后即丢弃），所以谁也登不上；
  * 列仍非空，满足 `sys_user.password` 的既有约束，不必改表；
  * 节点走 `node_auth_views` 的激活/挑战-应答拿令牌，与口令无关。

⚠️ 由此「重置节点口令」这种操作**不存在也不该存在** —— 节点忘记凭据的正确处置是
   管理员在「节点管理」里重新签发激活凭证，而不是给它设个新口令。
"""
import hashlib
import logging
import secrets

from django.contrib.auth.hashers import make_password
from django.db import connection

logger = logging.getLogger(__name__)

# 节点账号挂「普通角色」（role_id=2）。角色 1 是超级管理员，绝不能给节点。
NODE_ROLE_ID = 2

# sys_user.user_name 是 varchar(30)，而 node_id 允许到 64 字符。
USER_NAME_MAX_LEN = 30


def _unusable_password_hash() -> str:
    """生成一个**无人知道明文**的口令哈希。

    明文是 48 字节随机数，哈希之后**立刻丢弃** ——
    没有任何一条代码路径能再得到它，因此不存在"能登录该账号的口令"。
    需要在重置等场景复用同一手法即可，不要为了"方便"改成固定值。

    ⚠️ 这里刻意**不用固定哈希**（改版前是 RuoYi 的 admin123 常量），
       因为那等于"知道 node_id 就能登录任意节点"—— 不是弱口令，是没有认证。

    ⚠️ 用 Django 默认的 PBKDF2，与 RuoYi 的 BCrypt **格式不同**。
       这是**刻意保留**的，不要"顺手对齐"成 BCrypt：
         * 实测（2026-09-30）格式不同不会出事：RuoYi 的
           `BCryptPasswordEncoder.matches()` 对非 BCrypt 串直接判 false，
           节点用任意口令登录会得到干净的"用户不存在/密码错误"，**不是 500**。
         * 改用 BCrypt 需要给 Django 镜像加 `bcrypt` 依赖（当前没有），
           而收益只是"格式看起来一致"—— 换不来任何安全性或功能。
       （bcrypt 在 Python 里也会截断到 72 字节，而这里本就是随机高熵串，
         两种算法对"无人知道明文"这个目标没有区别。）
    """
    return make_password(secrets.token_urlsafe(48))


def _node_user_name(node_id: str) -> str:
    """
    由 node_id 推出登录用户名。

    优先直接用 node_id（便于运维一眼对应），超出 30 字符时截断并补 6 位
    短哈希 —— 只截断会让长 ID 的前 30 字符相同的两个节点撞名，
    补哈希可避免。真实映射始终以 `Node.sys_user_id` 为准，用户名只是入口。
    """
    node_id = (node_id or "").strip()
    if len(node_id) <= USER_NAME_MAX_LEN:
        return node_id
    digest = hashlib.sha256(node_id.encode("utf-8")).hexdigest()[:6]
    return f"{node_id[:USER_NAME_MAX_LEN - 7]}_{digest}"


def ensure_node_account(node) -> int:
    """
    确保节点有对应的 `kms.sys_user` 账号，返回 user_id。

    幂等：已存在同名账号时直接复用（不重置密码、不改昵称），
    这样重复调用不会覆盖运维后续对该账号做的调整。

    ⚠️ 账号的 `password` 是**无人知道明文的随机哈希**（见模块 docstring 的「密码」段）——
       这不是"忘了设"，是刻意的：节点**不通过口令登录**，走
       `node_auth_views` 的激活凭证 + 设备凭据挑战-应答。
       不要为了"能登进去看看"把它改成固定口令。

    调用方应处于 `transaction.atomic()` 中 —— 与 Node 行的创建同事务，
    避免出现"Node 建了但账号没建"的半截状态。
    """
    user_name = _node_user_name(node.node_id)
    nick_name = (node.name or node.node_id)[:30]

    with connection.cursor() as cur:
        # 1) 账号已存在？（可能由更早的流程建过）
        cur.execute(
            "SELECT user_id FROM kms.sys_user WHERE user_name = %s LIMIT 1",
            [user_name],
        )
        row = cur.fetchone()
        if row:
            user_id = row[0]
            logger.info("节点 %s 复用已有账号 %s (user_id=%s)", node.node_id, user_name, user_id)
        else:
            # 2) 建账号。
            #    principal_type='NODE' 与 role_level=2 必须同时写上：
            #    前者是阶段 2 的新主体类型，后者是过渡期仍在生效的准入判据
            #    （前端 isAdminLevel() 读的就是 role_level）。两者不一致会造出
            #    "标成 NODE 却能进管理端"这类矛盾态，见 31_*.sql 的说明。
            cur.execute(
                """
                INSERT INTO kms.sys_user
                    (user_name, nick_name, user_type, email, phonenumber, sex,
                     password, status, del_flag, create_by, create_time,
                     remark, role_level, principal_type)
                VALUES
                    (%s, %s, '00', %s, '', '0',
                     %s, '0', '0', 'node-provision', NOW(),
                     %s, 2, 'NODE')
                """,
                [
                    user_name,
                    nick_name,
                    (node.email or "")[:50],
                    _unusable_password_hash(),
                    f"节点账号，由建节点流程自动创建（node_id={node.node_id}）",
                ],
            )
            user_id = cur.lastrowid
            logger.info("节点 %s 创建账号 %s (user_id=%s)", node.node_id, user_name, user_id)

        # 3) 挂角色（幂等）
        cur.execute(
            "INSERT IGNORE INTO kms.sys_user_role (user_id, role_id) VALUES (%s, %s)",
            [user_id, NODE_ROLE_ID],
        )

    return int(user_id)
