"""
阶段 6：PreDistributedKey.status 的 choices 与默认值变更。

与 0010 的分工：
- 0010 是**数据迁移**（把存量行的旧值改成新值）
- 0011 是**schema 迁移**（更新字段的 choices 声明与 default）

Django 的 autodetector 会因为 choices/default 变化要求生成 AlterField，
本文件手工写好同一效果，避免下次 makemigrations 时冒出"未反映的模型变更"。

注意：choices 只在应用层生效，DB 层仍是 varchar(20)，
所以这个迁移不会重建表、也没有数据风险；default 变更只影响新插入的行。
"""
from django.db import migrations, models


STATUS_CHOICES = [
    ("READY", "已预分配，可被会话取用"),
    ("RESERVED", "正在被某次会话占用"),
    ("CONSUMED", "已成功建立会话，不可再次使用"),
    ("EXPIRED", "超过有效期"),
    ("REVOKED", "依赖的长期密钥已回收或检测异常"),
    ("unused", "未使用（历史值，等价 READY）"),
    ("used", "已使用（历史值，等价 CONSUMED）"),
    ("expired", "已过期（历史值，等价 EXPIRED）"),
    ("distributed", "已下发（历史值，等价 CONSUMED）"),
]


class Migration(migrations.Migration):

    dependencies = [
        ("pqkds", "0010_pool_status_normalize"),
    ]

    operations = [
        migrations.AlterField(
            model_name="predistributedkey",
            name="status",
            field=models.CharField(
                max_length=20,
                choices=STATUS_CHOICES,
                default="READY",
                verbose_name="状态",
                help_text="密钥当前状态",
            ),
        ),
    ]
