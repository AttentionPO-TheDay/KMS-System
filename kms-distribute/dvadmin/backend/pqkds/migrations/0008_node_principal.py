"""
阶段 2（身份模型）：Node 表加「账号映射 + 多级授权 + 跨域」三组字段。

对应文档 §2.3（Node 1─1 sys_user）、§8.4（节点多级授权）、§8.5（跨域分发）、
§2.4（节点状态增加 PENDING_INIT）。

⚠️ 关于 status 的默认值变更
--------------------------
本迁移把 Node.status 的 default 从 'registered' 改成 'PENDING_INIT'。
这是**有意的语义变更**，不是笔误：

  改造前：管理员建节点 → 服务端立刻生成四套密钥 → status='registered'
  改造后：管理员建节点 → 只建账号，status='PENDING_INIT'
                        → 节点首次登录才生成密钥 → status='ACTIVE'

因此新建的节点**必须**是 PENDING_INIT，密钥初始化由 node_service 的
首次初始化流程推进。旧的 'registered' 等状态保留在 choices 里，
因为存量数据仍可能带有它们，且状态机是单向累加的。
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("pqkds", "0007_node_gm_keys"),
    ]

    operations = [
        # --- 节点 ↔ 登录账号 的一一映射（跨 schema，无 FK，应用层维护） ---
        migrations.AddField(
            model_name="node",
            name="sys_user_id",
            field=models.BigIntegerField(
                null=True, blank=True, db_index=True, unique=True,
                verbose_name="关联登录账号ID",
                help_text="kms.sys_user.user_id；跨 schema 无 FK，由应用层维护一一映射",
            ),
        ),
        # --- 节点多级授权（L1/L2/L3） ---
        migrations.AddField(
            model_name="node",
            name="permission_level",
            field=models.CharField(
                max_length=4,
                choices=[
                    ("L1", "查询"),
                    ("L2", "查询+生成+分发"),
                    ("L3", "查询+生成+分发+更新+回收"),
                ],
                default="L1",
                verbose_name="节点权限等级",
                help_text="节点多级授权等级",
            ),
        ),
        # --- 跨域分发标记 ---
        migrations.AddField(
            model_name="node",
            name="domain_id",
            field=models.CharField(
                max_length=64, blank=True, default="domain-1",
                verbose_name="所属域", help_text="用于判定同域/跨域分发",
            ),
        ),
        # --- 首次初始化完成时间 ---
        migrations.AddField(
            model_name="node",
            name="initialized_at",
            field=models.DateTimeField(
                null=True, blank=True, verbose_name="首次初始化完成时间",
                help_text="四套基础密钥全部就绪的时间",
            ),
        ),
        # --- 状态机：默认值改为 PENDING_INIT（见模块 docstring） ---
        migrations.AlterField(
            model_name="node",
            name="status",
            field=models.CharField(
                max_length=20,
                choices=[
                    ("PENDING_INIT", "待初始化"),
                    ("registered", "已注册"),
                    ("kyber_uploaded", "Kyber公钥已上传"),
                    ("partial_key_received", "部分私钥已接收"),
                    ("falcon_generated", "Falcon密钥已生成"),
                    ("active", "活跃"),
                    ("inactive", "非活跃"),
                ],
                default="PENDING_INIT",
                verbose_name="节点状态",
                help_text="节点当前状态",
            ),
        ),
    ]
