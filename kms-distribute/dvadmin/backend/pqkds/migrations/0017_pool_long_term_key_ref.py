# -*- coding: utf-8 -*-
"""KMS-007：给 `PreDistributedKey` 补两列，记住池项是用哪把长期密钥封的。

计划 §7 阶段 2「回收时同步禁止新预分配」/ §13 KMS-007「回收服务、池项、会话服务」
------------------------------------------------------------------------------
补 `long_term_key_id` 与 `long_term_key_version` 两列。写入点在预分配创建处，
回收时按精确匹配失效。

为什么必须补列，而不是继续按 node_id 清
----------------------------------------
`KeyPoolService.revoke_pool_items_for_key(node_id, key_id, version)` 的签名收着
`key_id` / `version`，日志里也逐字印着它们，但查询**只按 `node_id` 匹配** ——
两个参数根本没进条件。这不是实现疏忽，是**数据不在表里**：补这两列之前，
`PreDistributedKey` 没有任何字段记录"我是用哪把长期公钥封的"。

`algorithm` / `wrapping_algorithm` 只到算法家族（kyber_kem / falcon_lattice），
`source_key_id` 指的是**另一个库**的 `kms.keymanage.key_id`，只服务用户腿。

按 node 全清的后果：回收**任何一个算法**的一把密钥，会把该节点**全部**
READY/RESERVED 池项一次清空 —— 包括用其它仍然有效的算法封的那些。
而这些条目本来是好的，被误杀之后用户看到的是"池子空了、得重新预分配"，
没有任何一处会报错。

为什么**不回填**历史行
----------------------
回填只能靠猜：表里没有信息能判定某条历史池项当初用的是 v1 还是 v2 的公钥。
猜错的后果是**静默漏杀** —— 一条永远解不开的池项继续显示 READY，
等着某次会话去取，然后在解密时失败（这正是 `revoke_pool_items_for_key`
自己的 docstring 要消灭的那种失败）。

两害相权：留 NULL 会在回收时退化成"同节点 + 同算法"匹配，**多杀**几条
（可见、可重新预分配）；猜错回填会**漏杀**（不可见、伪装成偶发故障）。
所以历史行一律 NULL，退化行为写在回收路径的日志里，不假装精确。

⚠️ 本迁移是**纯加列**（两个 `AddField`），不写数据、不可回滚出问题：
   反向迁移只丢这两列，池项本身与状态一动不动。

顺带收掉一处**先前遗留**的模型/迁移不一致（与本任务的设计无关）
----------------------------------------------------------------
KMS-005 改写了 `Node.key_device_id` 的 `help_text`（"首次上报公钥的设备标识"
→ "设备公钥指纹（激活时写入）"），但没有配上相应的迁移。于是
`makemigrations --check` 一直在报一个待生成的 `AlterField`。

为什么在这里顺手收掉，而不是放着不管：

  * 它**只动 help_text**（`max_length` / `blank` / `default` 与 0014 逐字相同），
    MySQL 层面不产生任何 DDL 差异，收掉它没有风险；
  * 留着它，`makemigrations --check` 就永远返回非零 —— 这条检查再也当不了
    "模型与迁移是否一致"的闸门，而本任务恰恰要靠它证明 0017 是完整的；
  * 更糟的是下一个人跑 `makemigrations` 时，Django 会把这个 `AlterField`
    **和他的改动写进同一个文件**（文件名按当时的最新迁移生成）。届时这个
    与提交主题无关的 `node` 表改动会混进他的变更里，谁也不会注意到。

⚠️ 这一条与上面两条**不是一回事**：它不是我加的两列，也不属于 KMS-007 的
   设计。写在这里是为了让"它为什么出现在这个文件里"有一个可查的答案。
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pqkds', '0016_node_long_term_key'),
    ]

    operations = [
        # --- 本任务的两列 ---
        migrations.AddField(
            model_name='predistributedkey',
            name='long_term_key_id',
            field=models.CharField(
                blank=True, null=True, max_length=64,
                verbose_name='长期密钥标识',
                help_text='封这一项时所用 NodeLongTermKey.key_id；历史行为 NULL（无法可靠回填）',
            ),
        ),
        migrations.AddField(
            model_name='predistributedkey',
            name='long_term_key_version',
            field=models.PositiveIntegerField(
                blank=True, null=True,
                verbose_name='长期密钥版本',
                help_text='封这一项时所用 NodeLongTermKey.key_version；历史行为 NULL',
            ),
        ),
        # --- 收掉上面说的那处遗留（仅 help_text，无 DDL 差异）---
        migrations.AlterField(
            model_name='node',
            name='key_device_id',
            field=models.CharField(
                max_length=128, blank=True, default='',
                verbose_name="密钥绑定设备",
                help_text="设备公钥指纹（激活时写入）；与该设备本地密钥库一一对应",
            ),
        ),
    ]
