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
沿用仓库既有约定：与 RuoYi 默认管理员相同的 BCrypt 哈希（`admin123`）。
`17_add_demo_test_user.sql:4` 与 `19_add_acceptance_user.sql:4` 都写明
"与管理员相同的 BCrypt 哈希"，本模块保持一致，不另造一套口令策略。
"""
import hashlib
import logging

from django.db import connection

logger = logging.getLogger(__name__)

# RuoYi 默认口令 admin123 的 BCrypt 哈希。
# 与 02.sql 的 admin 行、17_/19_ 两个迁移脚本逐字节一致 —— 刻意复用，
# 不引入第二套口令策略。
DEFAULT_PASSWORD_HASH = "$2a$10$7JB720yubVSZvUI0rEqK/.VqGOZTH.ulu33dHOiBE8ByOhJIrdAu2"

# 节点账号挂「普通角色」（role_id=2）。角色 1 是超级管理员，绝不能给节点。
NODE_ROLE_ID = 2

# sys_user.user_name 是 varchar(30)，而 node_id 允许到 64 字符。
USER_NAME_MAX_LEN = 30


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
                    DEFAULT_PASSWORD_HASH,
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
