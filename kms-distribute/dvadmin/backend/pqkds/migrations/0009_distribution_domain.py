"""
阶段 5（文档 §8.5）：分发批次增加跨域标记。

记录发起方所属域与目标域集合的**快照**，并据此判定 same / cross / mixed。

为什么存快照而不是每次回查：
人的组织归属会变（部门调动、节点换域），而"这次分发当时是不是跨域"
是一个**历史事实**，不该随后续变更而被改写 —— 否则审计记录会自相矛盾。
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("pqkds", "0008_node_principal"),
    ]

    operations = [
        migrations.AddField(
            model_name="distributionbatch",
            name="source_domain_id",
            field=models.CharField(
                max_length=64, blank=True, default="",
                verbose_name="发起方所属域",
                help_text="分发发起时发起方的 domain_id 快照",
            ),
        ),
        migrations.AddField(
            model_name="distributionbatch",
            name="target_domain_ids",
            field=models.TextField(
                blank=True, default="",
                verbose_name="目标域集合",
                help_text="JSON 数组，各目标节点所属域的并集快照",
            ),
        ),
        migrations.AddField(
            model_name="distributionbatch",
            name="distribution_type",
            field=models.CharField(
                max_length=16, blank=True, default="",
                choices=[("same", "同域"), ("cross", "跨域"), ("mixed", "混合")],
                verbose_name="分发类型",
                help_text="same=全部同域 / cross=全部跨域 / mixed=两者都有",
            ),
        ),
    ]