"""
阶段 5（文档 §6.2/§6.3）：为节点增加**标准 Falcon 签名密钥**。

## 为什么必须另加一对密钥
现有 `falcon_private_key` / `falcon_public_key` 里装的**不是标准 Falcon 密钥**，
而是 CL-Falcon 方案的格矩阵（`D_id` / `S_id`，各 1024 维）——
实测结构为 `{D_id, S_id, algorithm, security_level, node_id, parameters}`。
它与标准 Falcon DLL 不兼容：`crypto_sign` 需要 1281 字节的 NIST 私钥，
而这里的材料是 JSON 矩阵。

文档 §0.5 明确要求「Falcon 不再伪装为无证书算法，节点侧使用标准 KeyGen 生成，
负责数字签名和验签」。因此按该定位补一对**标准 Falcon 密钥**专用于签名，
与既有的无证书材料**并存但不混用**：

    falcon_*_key        CL-Falcon 格材料 —— 分发中作为封装目标（历史用途）
    falcon_sign_*_key   标准 Falcon 密钥 —— **专用于对信封签名/验签**（§6.3）

## 为什么服务端生成
文档想要的是"节点侧 KeyGen"。但本仓库没有节点侧运行环境
（前端无 PQ 实现、无节点 agent），这一点在阶段 2 已如实记录。
本轮先用服务端生成让签名机制**能跑通并被验证**，
待节点侧环境确定后再把生成位置下移 —— 那是一次位置调整，
不影响签名的语义与调用方。

## 存什么
标准 Falcon 密钥就是普通字节串，base64 存即可，不需要既有那套
`COMPRESSED:base64(zlib(json))` 的包装 —— 那是为结构化格材料设计的。
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("pqkds", "0011_pool_status_field"),
    ]

    operations = [
        migrations.AddField(
            model_name="node",
            name="falcon_sign_public_key",
            field=models.TextField(
                blank=True, default="",
                verbose_name="标准Falcon签名公钥",
                help_text="NIST Falcon-512 公钥（base64），专用于验签分发信封",
            ),
        ),
        migrations.AddField(
            model_name="node",
            name="falcon_sign_private_key",
            field=models.TextField(
                blank=True, default="",
                verbose_name="标准Falcon签名私钥",
                help_text="NIST Falcon-512 私钥（base64），专用于对分发信封签名",
            ),
        ),
    ]