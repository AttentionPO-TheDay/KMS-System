from django.db import models
from django.utils import timezone
from dvadmin.utils.models import CoreModel, table_prefix
import json
import hashlib
from typing import Dict, Any

# 冻结契约（KMS-002）。models 只从这里取**取值**，不取任何业务逻辑 ——
# api_contract 不 import 任何业务模块，所以这里不会形成循环引用。
from .api_contract import (
    KEY_STATUS_ACTIVE,
    KEY_STATUS_CHOICES,
    KEY_STATUS_EXPIRED,
    KEY_STATUS_PENDING,
    KEY_STATUS_REVOKED,
    key_status_allows_new_work,
    key_status_allows_unwrap,
)
class SystemParameters(CoreModel):
    name = models.CharField(max_length=100, unique=True, verbose_name="参数名称", help_text="系统参数名称")
    n = models.IntegerField(verbose_name="安全参数n", help_text="Falcon安全参数n")
    m = models.IntegerField(verbose_name="安全参数m", help_text="Falcon安全参数m")
    q = models.IntegerField(verbose_name="素数q", help_text="Falcon素数q")
    sigma = models.FloatField(verbose_name="高斯分布参数σ", help_text="高斯分布参数σ")
    matrix_a = models.TextField(verbose_name="系统矩阵A", help_text="JSON格式存储系统矩阵A")
    kgc_public_key = models.TextField(verbose_name="KGC公钥", help_text="JSON格式存储KGC公钥")
    is_active = models.BooleanField(default=True, verbose_name="是否激活", help_text="是否为当前激活的系统参数")
    class Meta:
        verbose_name = "系统参数"
        verbose_name_plural = "系统参数"
        db_table = f"{table_prefix}pqkds_system_parameters"
        ordering = ['-create_datetime']
    def __str__(self):
        return f"系统参数-{self.name}"
class Node(CoreModel):
    node_id = models.CharField(max_length=64, unique=True, verbose_name="节点ID", help_text="唯一节点标识符")
    name = models.CharField(max_length=100, verbose_name="节点名称", help_text="节点显示名称")
    ip_address = models.GenericIPAddressField(verbose_name="IP地址", help_text="节点IP地址")
    port = models.IntegerField(verbose_name="端口号", help_text="节点服务端口")
    blockchain_config = models.ForeignKey(
        'BlockchainConfig',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        verbose_name="区块链配置",
        help_text="节点所属的区块链网络配置"
    )
    phone = models.CharField(max_length=20, blank=True, verbose_name="手机号", help_text="节点管理员手机号")
    email = models.EmailField(blank=True, verbose_name="邮箱", help_text="节点管理员邮箱")
    contact_person = models.CharField(max_length=50, blank=True, verbose_name="联系人", help_text="节点负责人姓名")
    organization = models.CharField(max_length=200, blank=True, verbose_name="所属组织", help_text="节点所属组织或公司")
    department = models.CharField(max_length=100, blank=True, verbose_name="部门", help_text="节点所属部门")
    location = models.CharField(max_length=200, blank=True, verbose_name="物理位置", help_text="节点物理位置描述")
    node_type = models.CharField(
        max_length=20,
        choices=[
            ('full', '全节点'),
            ('light', '轻节点'),
            ('validator', '验证节点'),
            ('storage', '存储节点'),
            ('compute', '计算节点')
        ],
        default='full',
        verbose_name="节点类型",
        help_text="节点功能类型"
    )
    hardware_spec = models.TextField(blank=True, verbose_name="硬件规格", help_text="节点硬件配置信息")
    description = models.TextField(blank=True, verbose_name="节点描述", help_text="节点详细描述信息")
    tags = models.CharField(max_length=500, blank=True, verbose_name="标签", help_text="节点标签，用逗号分隔")
    kyber_security_level = models.CharField(
        max_length=10,
        choices=[
            ('512', 'Kyber-512 (安全级别1)'),
            ('768', 'Kyber-768 (安全级别3)'),
            ('1024', 'Kyber-1024 (安全级别5)')
        ],
        default='512',
        verbose_name="Kyber安全级别",
        help_text="Kyber密钥封装机制的安全级别"
    )
    falcon_security_level = models.CharField(
        max_length=10,
        choices=[
            ('512', 'Falcon-512 (安全级别1)'),
            ('1024', 'Falcon-1024 (安全级别5)')
        ],
        default='512',
        verbose_name="Falcon安全级别",
        help_text="Falcon数字签名的安全级别"
    )
    kyber_public_key = models.TextField(blank=True, verbose_name="Kyber公钥", help_text="Base64编码的Kyber公钥")
    kyber_private_key = models.TextField(blank=True, verbose_name="Kyber私钥", help_text="Base64编码的Kyber私钥，仅节点本地存储")
    kyber_partial_key_data = models.TextField(blank=True, verbose_name="Kyber部分私钥数据", help_text="JSON格式存储KGC为Kyber生成的部分私钥数据")
    falcon_public_key = models.TextField(blank=True, verbose_name="Falcon公钥", help_text="Base64编码的Falcon公钥")
    falcon_private_key = models.TextField(blank=True, verbose_name="Falcon私钥", help_text="Base64编码的Falcon私钥，仅节点本地存储")
    falcon_partial_key_data = models.TextField(blank=True, verbose_name="Falcon部分私钥数据", help_text="JSON格式存储KGC为Falcon生成的部分私钥数据")
    partial_key_received = models.BooleanField(default=False, verbose_name="是否已接收部分私钥", help_text="标识是否已从KGC接收部分私钥")
    partial_key_data = models.TextField(blank=True, verbose_name="部分私钥数据（兼容旧版）", help_text="JSON格式存储加密的部分私钥数据，保留用于向后兼容")
    falcon_lattice_params = models.TextField(blank=True, verbose_name="Falcon格密码参数", help_text="JSON格式存储Falcon无证书格密码参数：A、B、H_id、U_id、D_id、S_id")
    # 国密（SM2）节点密钥 —— 2026-09-26 新增。
    #
    # 为什么需要：节点腿上原本**只有抗量子**（Kyber/Falcon），于是"这次分发不用抗量子"
    # 在界面上无路可走。加上国密后，用户可在分发时三选一：
    #   kyber_kem / falcon_lattice / gm_sm2
    # 选 gm_sm2 时节点信封用本字段里的 SM2 公钥封装，节点用私钥解封。
    #
    # 与 Kyber/Falcon 的区别：那两者是格密码（抗量子），SM2 是椭圆曲线国密；
    # 三者都是**节点持有私钥**的真实密钥，不是演示占位。
    gm_public_key = models.TextField(blank=True, verbose_name="国密公钥", help_text="SM2 公钥（130 位十六进制，04 开头）")
    gm_private_key = models.TextField(blank=True, verbose_name="国密私钥", help_text="SM2 私钥（64 位十六进制标量），仅节点本地存储")
    gm_keygen_time = models.DateTimeField(null=True, blank=True, verbose_name="国密密钥生成时间", help_text="SM2 节点密钥对生成的时间")
    # SSCL（无证书国密）节点密钥 —— 与 SM2 并列的第四种节点腿算法。
    #
    # 加解密算法与 SM2 **完全相同**（SSCL 的 d_A 是 sm2p256v1 上的标量、
    # P_A 是同一曲线上的点，见 wrappers.py 里 SsclWrapper 的说明），
    # 差别只在密钥怎么派生；因此这里同样存一对标量/点，由本模块生成。
    sscl_public_key = models.TextField(blank=True, verbose_name="SSCL 公钥", help_text="SSCL 加密目标点（130 位十六进制，04 开头）")
    sscl_private_key = models.TextField(blank=True, verbose_name="SSCL 私钥", help_text="SSCL 私钥标量（64 位十六进制），仅节点本地存储")
    kyber_keygen_time = models.DateTimeField(null=True, blank=True, verbose_name="Kyber密钥生成时间", help_text="Kyber密钥对生成的时间")
    kyber_keygen_duration = models.FloatField(null=True, blank=True, verbose_name="Kyber密钥生成耗时", help_text="Kyber密钥对生成花费的时间（秒）")
    falcon_keygen_time = models.DateTimeField(null=True, blank=True, verbose_name="Falcon密钥生成时间", help_text="Falcon密钥对生成的时间")
    falcon_keygen_duration = models.FloatField(null=True, blank=True, verbose_name="Falcon密钥生成耗时", help_text="Falcon密钥对生成花费的时间（秒）")
    status = models.CharField(
        max_length=20,
        choices=[
            # 阶段 2 新增：节点已建立账号，但**尚未完成首次密钥初始化**。
            # 建节点只创建账号与这一行记录，四套基础密钥推迟到节点首次登录时生成
            # （文档 §2.4 / §3.1：节点创建与密码学初始化是两个阶段）。
            ('PENDING_INIT', '待初始化'),
            ('registered', '已注册'),
            ('kyber_uploaded', 'Kyber公钥已上传'),
            ('partial_key_received', '部分私钥已接收'),
            ('falcon_generated', 'Falcon密钥已生成'),
            ('active', '活跃'),
            ('inactive', '非活跃')
        ],
        default='PENDING_INIT',
        verbose_name="节点状态",
        help_text="节点当前状态"
    )
    last_active = models.DateTimeField(default=timezone.now, verbose_name="最后活跃时间", help_text="节点最后活跃时间")

    # -------------------------------------------------------------------------
    # 阶段 2（身份模型）新增字段
    # -------------------------------------------------------------------------
    # 节点与 kms.sys_user 的**真实一一映射**（文档 §2.3：Node 1 ── 1 sys_user）。
    #
    # 为什么不建 ForeignKey：两者分属不同 schema（本模型在 falcon_kds，
    # sys_user 在 kms）。MySQL 的 FK 不能跨 schema，所以这里存 sys_user 的
    # 主键值并**在应用层维护一致性**，而不是声明一个建不出来的约束。
    #
    # 与 UserNodeAuthorization 的区别要说清楚，否则会被误当成同一个东西：
    #   那个模型**是通信授权**（"谁可以向谁分发/与谁建会话"）—— 用户与节点是
    #   **两个实体**；本字段是「这个节点**就是**这个账号」—— 节点与账号是**同一实体**。
    #
    #   ⚠️ 早先这里写的是"前者与设定二冲突、属于待删语义"（因为当时只有用户腿）。
    #      节点多级授权落地后那句话不再成立：节点场景下 `UserNodeAuthorization.user_id`
    #      填的就是本字段（`Node.sys_user_id`），这是它要**长期承担**的关系，
    #      不是过渡写法。两张表的分工没变：本字段回答"这个节点是哪个账号"，
    #      那张表回答"这个账号能跟哪些节点通信"。
    sys_user_id = models.BigIntegerField(
        null=True, blank=True, db_index=True, unique=True,
        verbose_name="关联登录账号ID",
        help_text="kms.sys_user.user_id；跨 schema 无 FK，由应用层维护一一映射"
    )
    # 节点多级授权（文档 §8.4）。与「登录主体类型」是两回事：
    #   principal_type 决定「能不能登录、进哪个视图」；
    #   permission_level 决定「登录后能做什么」——L1 查询 / L2 +生成分发 / L3 +更新回收。
    permission_level = models.CharField(
        max_length=4,
        choices=[('L1', '查询'), ('L2', '查询+生成+分发'), ('L3', '查询+生成+分发+更新+回收')],
        default='L1',
        verbose_name="节点权限等级",
        help_text="节点多级授权等级"
    )
    # 跨域分发标记（文档 §8.5）。第一版不部署多套 KMS，只把跨域语义做完整。
    domain_id = models.CharField(
        max_length=64, blank=True, default='domain-1',
        verbose_name="所属域",
        help_text="用于判定同域/跨域分发"
    )
    # 首次初始化完成时间。PENDING_INIT → ACTIVE 的那一刻写入，用于审计与排查。
    initialized_at = models.DateTimeField(
        null=True, blank=True, verbose_name="首次初始化完成时间",
        help_text="四套基础密钥全部就绪的时间"
    )

    # -------------------------------------------------------------------------
    # §4.4 设备绑定
    # -------------------------------------------------------------------------
    # 与哪台设备上生成的密钥绑定。KMS-005 起，它的值是**设备公钥的指纹**
    # （`sha256("{crv}|{x}|{y}")[:32]`，见 `node_auth_views._public_key_fingerprint`），
    # 由**服务端在激活时算出并写入** —— 不再是节点侧自报的浏览器随机串
    # （`NodeKeyStore.getDeviceId()` 仍存在，但那是密钥库自己的标识，用途不同）。
    #
    # 为什么需要它：私钥只在节点侧，**服务端无法从密钥本身看出它属于哪台设备**。
    # 没有这个记录，"换了一台设备登录"在服务端看来与"同一台设备"完全一样 ——
    # 而两者的正确处置是相反的：
    #   * 同一台设备：什么都不用做；
    #   * 新设备：按 §4.4 应当执行**重新初始化或轮换**，并回收旧版本 ——
    #     因为新设备上**没有**解密的私钥，旧版本的信封它一个也打不开。
    #
    # 它就是 `store_node_public_key` 设备守卫的比较对象：上报的 `deviceId`
    # 与这里不等时按 `DEVICE_MISMATCH` 拒绝登记。注意该比较仍只是**字符串比对** ——
    # 值的**来源**是密码学的（由已验签的公钥算出），但上报方无需出示私钥，
    # 所以它防的是"换了设备却不自知"，不是恶意的冒名上报。
    #
    # 历史遗留：激活流程之前建的节点这一列可能是空的，此时第一次上报会**采纳**
    # 上报值（`store_node_public_key` 的 adopt 分支）；新节点不再走那条路径。
    key_device_id = models.CharField(
        max_length=128, blank=True, default='',
        verbose_name="密钥绑定设备",
        help_text="设备公钥指纹（激活时写入）；与该设备本地密钥库一一对应"
    )

    # -------------------------------------------------------------------------
    # 文档 §3.1 / §5：设备认证凭据（节点登录的**唯一**凭据）
    # -------------------------------------------------------------------------
    # 与上面 key_device_id 的关系，别混：
    #   key_device_id        —— 设备公钥的**指纹**，用于发现"换了设备"并拒绝上报
    #                           （DEVICE_MISMATCH）；由激活时的那把公钥算出。
    #   device_auth_public_key —— 公钥**本体**。节点侧 WebCrypto 生成不可导出的
    #                           ECDSA P-256 私钥，公钥上报到这里；登录时服务端下发
    #                           一次性挑战，节点用私钥签名，服务端用这把公钥验签。
    #                           私钥从不出本机，服务端无法伪造节点身份。
    #
    # 每个节点**各有一把**，存在该节点自己的命名空间里
    # （前端 keyRef = `node-{nodeId}-device-auth`），因此**同一个浏览器可以托管
    # 多个互不干扰的节点身份** —— 这正是文档 §4 的设计（一个浏览器 ≠ 一个节点，
    # 而是"一个节点本地测试环境，可托管多个独立节点身份"）。
    device_auth_public_key = models.TextField(
        blank=True, default='',
        verbose_name="设备认证公钥",
        help_text="ECDSA P-256 公钥（JWK JSON）；登录挑战-应答验签用。私钥只在节点本机"
    )
    device_auth_algorithm = models.CharField(
        max_length=32, blank=True, default='ECDSA-P256',
        verbose_name="设备认证算法",
        help_text="便于日后换算法时不必猜旧值是什么"
    )

    # --- 一次性激活凭证（文档 §3）---
    # 管理员建节点时签发，**只回传一次明文**，库里只存哈希。
    # 一次性 + 有有效期 + 用后立即失效 + 支持重新签发（文档 §3 的原文要求）。
    #
    # 为什么不存明文：凭证等同于节点的"入场券"，泄漏即可冒名激活。
    # 存哈希使得"读库"不等于"能激活"。
    activation_code_hash = models.CharField(
        max_length=128, blank=True, default='',
        verbose_name="激活凭证哈希",
        help_text="一次性激活凭证的 SHA-256 十六进制；明文只在签发响应里出现一次"
    )
    activation_code_issued_at = models.DateTimeField(
        null=True, blank=True, verbose_name="凭证签发时间"
    )
    activation_code_expires_at = models.DateTimeField(
        null=True, blank=True, verbose_name="凭证过期时间"
    )
    activated_at = models.DateTimeField(
        null=True, blank=True, verbose_name="设备激活时间",
        help_text="节点首次用激活凭证换取设备凭据的时间"
    )

    # --- 阶段 5（文档 §6.2/§6.3）：标准 Falcon 签名密钥 ---
    # ⚠️ 与上面的 falcon_public_key / falcon_private_key **不是一回事**：
    # 那两列装的是 CL-Falcon 的格矩阵（D_id / S_id），与标准 Falcon DLL 不兼容，
    # 无法用于 crypto_sign。文档 §0.5 要求 Falcon 回归"标准密钥生成 + 签名验签"
    # 的定位，故另加这一对专用于**对分发信封签名**。
    #
    # 两者并存不混用：格材料仍是分发中节点腿的封装目标（历史用途），
    # 标准密钥只做签名。混用会导致"拿签名密钥去解密"这类概念错误。
    falcon_sign_public_key = models.TextField(
        blank=True, default='',
        verbose_name="标准Falcon签名公钥",
        help_text="NIST Falcon-512 公钥（base64），专用于验签分发信封",
    )
    falcon_sign_private_key = models.TextField(
        blank=True, default='',
        verbose_name="标准Falcon签名私钥",
        help_text="NIST Falcon-512 私钥（base64），专用于对分发信封签名",
    )
    blockchain_synced = models.BooleanField(default=False, verbose_name="是否同步到区块链", help_text="节点信息是否已同步到区块链")
    blockchain_sync_time = models.DateTimeField(null=True, blank=True, verbose_name="同步时间", help_text="节点同步到区块链的时间")

    # --- 长期密钥版本的便利读法（KMS-004）---
    # 只读；**不要**在这里加写入方法 —— 写入的唯一入口是 `node_key_registry`，
    # 它负责双写 `Node.<算法>_public_key` 与降级旧版本这两件必须一起发生的事。
    def current_long_term_key(self, algorithm: str):
        """取该算法当前生产中的版本（status=ACTIVE）。没有则返回 None。

        ⚠️ 别的算法名写法（`kyber_kem` / `cl-falcon` / `falcon_lattice`）会先
           经 `canonical_algorithm` 归一 —— 调用方不必自己清洗拼写。
        """
        from .api_contract import canonical_algorithm
        return self.long_term_keys.filter(
            algorithm=canonical_algorithm(algorithm), status=KEY_STATUS_ACTIVE,
        ).first()

    def long_term_key_versions(self, algorithm: str):
        """该算法的全部版本，新的在前（供"版本历史"页面用）。"""
        from .api_contract import canonical_algorithm
        return self.long_term_keys.filter(
            algorithm=canonical_algorithm(algorithm),
        ).order_by('-key_version')

    class Meta:
        verbose_name = "节点"
        verbose_name_plural = "节点"
        db_table = f"{table_prefix}pqkds_nodes"
        ordering = ['-create_datetime']
    def __str__(self):
        return f"节点-{self.name}({self.node_id})"
class Block(CoreModel):
    block_hash = models.CharField(max_length=64, unique=True, verbose_name="区块哈希", help_text="区块哈希值")
    previous_hash = models.CharField(max_length=64, verbose_name="前一区块哈希", help_text="前一个区块的哈希值")
    block_number = models.IntegerField(verbose_name="区块号", help_text="区块序号")
    timestamp = models.DateTimeField(auto_now_add=True, verbose_name="时间戳", help_text="区块创建时间")
    merkle_root = models.CharField(max_length=64, verbose_name="Merkle根", help_text="交易Merkle树根")
    nonce = models.BigIntegerField(verbose_name="随机数", help_text="挖矿随机数")
    class Meta:
        verbose_name = "区块"
        verbose_name_plural = "区块"
        db_table = f"{table_prefix}pqkds_blocks"
        ordering = ['-block_number']
    def __str__(self):
        return f"区块#{self.block_number}"
class Transaction(CoreModel):
    TRANSACTION_TYPES = [
        ('kyber_upload', 'Kyber公钥上传'),
        ('falcon_upload', 'Falcon公钥上传'),
        ('partial_key_transfer', '部分私钥传输'),
        ('session_key_exchange', '会话密钥交换'),
        ('message_transfer', '消息传输')
    ]
    tx_hash = models.CharField(max_length=64, unique=True, verbose_name="交易哈希", help_text="交易哈希值")
    block = models.ForeignKey(Block, on_delete=models.CASCADE, related_name='transactions', verbose_name="所属区块", help_text="交易所属的区块")
    tx_type = models.CharField(max_length=30, choices=TRANSACTION_TYPES, verbose_name="交易类型", help_text="交易类型")
    from_node = models.ForeignKey(Node, on_delete=models.CASCADE, related_name='sent_transactions', verbose_name="发送节点", help_text="交易发送节点")
    to_node = models.ForeignKey(Node, on_delete=models.CASCADE, related_name='received_transactions',
                               null=True, blank=True, verbose_name="接收节点", help_text="交易接收节点")
    data = models.TextField(verbose_name="交易数据", help_text="JSON格式存储的交易数据")
    signature = models.TextField(verbose_name="交易签名", help_text="交易数字签名")
    timestamp = models.DateTimeField(auto_now_add=True, verbose_name="交易时间", help_text="交易创建时间")
    confirmed = models.BooleanField(default=False, verbose_name="是否确认", help_text="交易是否已确认")
    class Meta:
        verbose_name = "交易"
        verbose_name_plural = "交易"
        db_table = f"{table_prefix}pqkds_transactions"
        ordering = ['-timestamp']
    def __str__(self):
        return f"交易-{self.tx_type}({self.tx_hash[:8]}...)"
class SessionKey(CoreModel):
    session_id = models.CharField(max_length=64, unique=True, verbose_name="会话ID", help_text="唯一会话标识符")
    node1 = models.ForeignKey(Node, on_delete=models.CASCADE, related_name='sessions_as_node1', verbose_name="节点1", help_text="会话发起节点")
    node2 = models.ForeignKey(Node, on_delete=models.CASCADE, related_name='sessions_as_node2', verbose_name="节点2", help_text="会话接收节点")
    encrypted_session_key = models.TextField(verbose_name="加密的会话密钥", help_text="使用Kyber加密的AES会话密钥")
    key_exchange_data = models.TextField(verbose_name="密钥交换数据", help_text="JSON格式存储的密钥交换数据")
    session_type = models.CharField(
        max_length=20,
        choices=[
            ('aes_falcon', 'AES+Falcon会话'),
            ('kyber_kem', 'Kyber密钥协商'),
            # KMS-008：新分发的会话按**实际用的保护算法**记，不再是"一律 kyber_kem"。
            # 该字段在 `node_session_views` 里本来就以 `protectionAlgorithm` 的
            # 名义下发（会话列表拿它当"这条会话用哪种算法保护的"展示），
            # 而旧用户腿流程恒写 kyber_kem —— 连国密节点腿的会话也记成 Kyber。
            # 值是**节点腿的封装拼写**（与 `wrappers.NODE_WRAPPING_CHOICES` 同形）。
            ('gm_sm2', '国密 SM2 保护'),
            ('gm_sscl', '国密 SSCL 保护'),
        ],
        default='aes_falcon',
        verbose_name="会话类型",
        help_text="会话建立的协议类型 = 本次分发用的保护算法拼写"
    )
    status = models.CharField(
        max_length=20,
        choices=[
            ('initiated', '已发起'),
            ('established', '已建立'),
            ('blockchain_recorded', '已记录到区块链'),
            ('expired', '已过期'),
            ('revoked', '已撤销')
        ],
        default='initiated',
        verbose_name="会话状态",
        help_text="会话当前状态"
    )
    expires_at = models.DateTimeField(verbose_name="过期时间", help_text="会话密钥过期时间")

    # --- KMS-011：会话记录关联的具体密钥版本（计划 §7 阶段 4 第 1 条）---
    # "会话记录关联具体接收密钥版本和 Falcon 密钥版本"。
    #
    # 为什么必须是**显式四列**而不是从批次/信封反查：
    #   * 反查要拿 `{batch_id}-n{pk}` 去拼、再解析，而 batch_id 是字符串约定，
    #     改一次命名规则所有历史会话就查不出自己的密钥版本 —— 静默；
    #   * 接收方取信封时页面上要显示"这封信靠哪一版解封"，这个信息必须
    #     随会话本身给出，否则页面只能显示一个自己拼的猜测值。
    #
    # 留空（NULL）而不是填占位：历史会话（本迁移之前建的）没有这些值，
    # 编一个 key_id 比留空更糟 —— 它会被下游当成真的去查。与
    # `PreDistributedKey.long_term_key_id`（迁移 0017）同一条纪律。
    recipient_key_id = models.CharField(
        max_length=64, null=True, blank=True, verbose_name="接收方长期密钥 keyId",
        help_text="这条会话的 SM4 是靠接收方哪一把长期密钥保护的（KMS-011）",
    )
    recipient_key_version = models.IntegerField(
        null=True, blank=True, verbose_name="接收方长期密钥版本",
    )
    #: 发送方签名用的那一版 Falcon 长期密钥（KMS-010 起请求里显式携带，
    #: 这里随会话落库）：接收方验签要**回到同一版**公钥，kms 侧不再另挑。
    falcon_key_id = models.CharField(
        max_length=64, null=True, blank=True, verbose_name="发送方 Falcon keyId",
        help_text="发送节点签名这封信封用的 Falcon 密钥（验收签要用同一版）",
    )
    falcon_key_version = models.IntegerField(
        null=True, blank=True, verbose_name="发送方 Falcon 版本",
    )

    # --- KMS-014：会话的证据轨迹（监管页五态的数据源）---
    # 计划 §7 阶段 6 要求监管页区分「已登记 / 已验签 / 已解封 / 已建立 / 已上链」。
    # 前四态能从 `status` 推，**但只在会话还活着的时候** —— 关闭之后 status 只剩
    # 一个 `closed`，"它曾经走到过哪一步"就再也答不出来；而监管要看的恰恰是
    # 完整轨迹。所以每一步证据在这里各记一条（时间 + 链上哈希）：
    #
    #   {"verified":    {"at": "...", "tx": "0x…"},
    #    "recovered":   {"at": "...", "tx": ""},        # 解封无链上事件（服务端无法复核，见下）
    #    "established": {"at": "...", "tx": "0x…"},
    #    "closed":      {"at": "...", "tx": "0x…"}}
    #
    # ⚠️ `recovered` **没有**对应的链上事件（计划只要求三个会话类事件：
    #    ENVELOPE_VERIFIED / SESSION_ESTABLISHED / SESSION_CLOSED）。解封是
    #    节点的单方声明、服务端无法独立复核（不变量：服务端没有 K），
    #    它进不了链上存证 —— 这里如实记时间，tx 留空。不假装它上过链。
    # ⚠️ 不用 `status` 反推轨迹：那会在关闭/撤销后**静默丢失**轨迹，
    #    且与"五态"的语义（证据各有其时间线，与当前状态无关）不符。
    lifecycle_evidence = models.TextField(
        default='{}', blank=True, verbose_name="会话证据轨迹",
        help_text='JSON：各步证据的时间与链上哈希（KMS-014，监管页五态的数据源）',
    )

    def record_evidence(self, step: str, *, tx: str = '', at=None) -> None:
        """把一步证据追加进 `lifecycle_evidence`（幂等：已记过的不覆盖）。

        ⚠️ 只**追加**不覆盖：同一步事件重试时（例如链上失败后的重放），
        第一条时间才是"这一步真的发生"的时刻；覆盖会把它改写成一个更晚的
        时间，轨迹会悄悄后移。`tx` 为空且已有记录时也**顺带补写 tx** ——
        链上哈希是后到的事实（验证已提交、存证是旁路），补写不篡改时间。
        """
        import json as _json
        try:
            data = _json.loads(self.lifecycle_evidence or '{}')
            if not isinstance(data, dict):
                data = {}
        except (ValueError, TypeError):
            # 库内值坏了：不把它当致命错误（监管页少一条轨迹 > 整个列表 500），
            # 但**要看得见** —— warning 里带会话 ID。
            import logging as _logging
            _logging.getLogger(__name__).warning(
                '会话 %s 的 lifecycle_evidence 不是合法 JSON，本次重建', self.session_id,
            )
            data = {}
        entry = data.get(step) or {}
        if not isinstance(entry, dict):
            entry = {}
        if not entry.get('at'):
            from django.utils import timezone as _tz
            entry['at'] = (at or _tz.now()).isoformat()
        if tx and not entry.get('tx'):
            entry['tx'] = tx
        data[step] = entry
        self.lifecycle_evidence = _json.dumps(data, ensure_ascii=False, sort_keys=True)

    def evidence_state(self) -> dict:
        """给监管页的五态读数（不依赖当前 status，见 `lifecycle_evidence` 的说明）。"""
        import json as _json
        try:
            data = _json.loads(self.lifecycle_evidence or '{}')
        except (ValueError, TypeError):
            data = {}
        if not isinstance(data, dict):
            data = {}
        return {
            'registered': True,  # 行在 = 已登记（信封登记是建行那一刻）
            'verified': bool((data.get('verified') or {}).get('at')),
            'recovered': bool((data.get('recovered') or {}).get('at')),
            'established': bool((data.get('established') or {}).get('at')),
            # 已上链 = 至少一条**链上事件**落了 tx（解封不计，它本就不上链）。
            'onChain': any(
                (data.get(step) or {}).get('tx')
                for step in ('verified', 'established', 'closed')
            ),
        }

    class Meta:
        verbose_name = "会话密钥"
        verbose_name_plural = "会话密钥"
        db_table = f"{table_prefix}pqkds_session_keys"
    def __str__(self):
        return f"会话-{self.node1.name}↔{self.node2.name}"
class SessionKeyConfirmation(CoreModel):
    """会话的**双方确认**记录（文档 §6.5）。

    <h2>为什么单独一张表，而不是给 SessionKey 加两列</h2>
    确认是"每个节点各一次"的事件，需要各自的**时间**与**证明**。
    加两列也能存，但会丢掉"谁在什么时候提交了什么证明"——
    而审计要的恰恰是那个。会话的双方是 node1/node2 两个外键，
    摊平成列会让"第三个人来提交"这类越权判断散落在代码里。

    <h2>证明是什么（这一步的设计要点）</h2>
    双方各自提交 `HMAC-SHA256(K, session_id)`，K 是它们**实际解封得到**的
    SM4 会话密钥。服务端**比较两条证明是否相等**，而不去解出 K ——
    服务端本来就没有 K，这正是本系统"服务端解不开"那条不变量。

    相等 ⇒ 双方持有**同一把** K。这不是形式检查：
      * 单方随便算一个值 → 与对方对不上，提升不了；
      * 双方各持有不同的 K（例如封装时算法搞混）→ 同样对不上。
    所以"提升为 established"是有依据的，不是宣称。

    ⚠️ 服务端由此看到的只是一个 PRF 输出。K 是 128 位随机值，
       拿到 HMAC 对它没有实际优势 —— 但这句话的前提是
       **K 确实是随机的**，所以各处的 `PayloadCipher.generate_key()`
       不能退化成弱随机源。
    """

    session = models.ForeignKey(
        SessionKey, on_delete=models.CASCADE, related_name='confirmations',
        verbose_name="所属会话"
    )
    node = models.ForeignKey(
        Node, on_delete=models.CASCADE, related_name='session_confirmations',
        verbose_name="提交确认的节点"
    )
    #: HMAC-SHA256(K, session_id) 的十六进制。**不是 K 本身。**
    proof = models.CharField(max_length=64, verbose_name="持有证明")
    key_recovered = models.BooleanField(
        default=False, verbose_name="是否已恢复会话密钥",
        help_text="节点声明它已成功解封出 K。服务端无法独立验证这一条，"
                  "真正起作用的是 proof 的相互匹配。",
    )
    confirmed_at = models.DateTimeField(verbose_name="确认时间")

    class Meta:
        verbose_name = "会话确认"
        verbose_name_plural = "会话确认"
        db_table = f"{table_prefix}pqkds_session_confirmations"
        # 一个节点对一条会话只确认一次；重复提交走 update_or_create，
        # 使整个流程可安全重试（节点网络抖动不该产生第二行）。
        unique_together = (('session', 'node'),)

    def __str__(self):
        return f'确认-{self.session.session_id}-{self.node.node_id}'


class Message(CoreModel):
    message_id = models.CharField(max_length=64, unique=True, verbose_name="消息ID", help_text="唯一消息标识符")
    session = models.ForeignKey(SessionKey, on_delete=models.CASCADE, related_name='messages', verbose_name="所属会话", help_text="消息所属的会话")
    sender = models.ForeignKey(Node, on_delete=models.CASCADE, related_name='sent_messages', verbose_name="发送者", help_text="消息发送节点")
    receiver = models.ForeignKey(Node, on_delete=models.CASCADE, related_name='received_messages', verbose_name="接收者", help_text="消息接收节点")
    encrypted_content = models.TextField(verbose_name="加密内容", help_text="使用AES会话密钥加密的消息内容")
    message_type = models.CharField(
        max_length=20,
        choices=[
            ('text', '文本消息'),
            ('file', '文件传输'),
            ('command', '命令消息'),
            ('heartbeat', '心跳消息')
        ],
        default='text',
        verbose_name="消息类型",
        help_text="消息类型"
    )
    timestamp = models.DateTimeField(auto_now_add=True, verbose_name="发送时间", help_text="消息发送时间")
    delivered = models.BooleanField(default=False, verbose_name="是否已送达", help_text="消息是否已送达")
    read = models.BooleanField(default=False, verbose_name="是否已读", help_text="消息是否已读")
    class Meta:
        verbose_name = "消息"
        verbose_name_plural = "消息"
        db_table = f"{table_prefix}pqkds_messages"
        ordering = ['-timestamp']
    def __str__(self):
        return f"消息-{self.sender.name}{self.receiver.name}({self.timestamp})"
class BlockchainConfig(CoreModel):
    name = models.CharField(max_length=100, verbose_name="配置名称", help_text="区块链配置名称")
    provider_url = models.URLField(verbose_name="节点URL", help_text="区块链节点RPC URL")
    contract_address = models.CharField(max_length=42, blank=True, verbose_name="合约地址", help_text="智能合约地址")
    contract_abi = models.TextField(blank=True, verbose_name="合约ABI", help_text="智能合约ABI JSON")
    private_key = models.TextField(verbose_name="私钥", help_text="账户私钥（加密存储）")
    account_address = models.CharField(max_length=42, verbose_name="账户地址", help_text="以太坊账户地址")
    network_id = models.IntegerField(null=True, blank=True, verbose_name="网络ID", help_text="区块链网络ID")
    is_active = models.BooleanField(default=True, verbose_name="是否活跃", help_text="是否为当前活跃配置")
    gas_limit = models.IntegerField(default=500000, verbose_name="Gas限制", help_text="交易Gas限制")
    gas_price = models.BigIntegerField(default=20000000000, verbose_name="Gas价格", help_text="交易Gas价格（Wei）")
    class Meta:
        verbose_name = "区块链配置"
        verbose_name_plural = "区块链配置"
        db_table = f"{table_prefix}pqkds_blockchain_config"
    def __str__(self):
        return f"{self.name} - {self.account_address[:10]}..."
    def save(self, *args, **kwargs):
        contract_address_changed = False
        if self.pk:
            try:
                old_instance = BlockchainConfig.objects.get(pk=self.pk)
                if old_instance.contract_address != self.contract_address:
                    contract_address_changed = True
            except BlockchainConfig.DoesNotExist:
                pass
        if self.is_active:
            BlockchainConfig.objects.exclude(pk=self.pk).update(is_active=False)
        super().save(*args, **kwargs)
        if contract_address_changed:
            self._cleanup_blockchain_related_data()
    def _cleanup_blockchain_related_data(self):
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"区块链配置 {self.name} 的合约地址发生变更，开始清理相关数据...")
        logger.info(f"保留所有会话密钥记录（共 {SessionKey.objects.count()} 个）")
        logger.info(f"保留所有消息记录（共 {Message.objects.count()} 个）")
        transaction_count = Transaction.objects.count()
        Transaction.objects.all().delete()
        logger.info(f"已清理 {transaction_count} 个交易记录")
        nodes_in_config = Node.objects.filter(blockchain_config=self)
        nodes_count = nodes_in_config.count()
        nodes_in_config.update(
            blockchain_config=None,
            status='registered'
        )
        logger.info(f"已将 {nodes_count} 个节点从配置 '{self.name}' 中移除，新合约下将显示空节点列表")
        logger.info("区块链相关数据清理完成（会话和消息已保留）")
class FalconKeyPair(CoreModel):
    STATUS_CHOICES = [
        ('active', '活跃'),
        ('revoked', '已撤销'),
        ('expired', '已过期'),
    ]
    node = models.OneToOneField(Node, on_delete=models.CASCADE, verbose_name="关联节点", help_text="密钥对关联的节点")
    user_id = models.CharField(max_length=100, verbose_name="用户ID", help_text="用户标识符")
    public_key = models.TextField(verbose_name="公钥u", help_text="Falcon公钥")
    secret_key = models.TextField(verbose_name="私钥s", help_text="Falcon私钥（加密存储）")
    secret_value = models.TextField(verbose_name="用户秘密值s_id", help_text="用户秘密值（加密存储）")
    partial_key = models.TextField(verbose_name="部分密钥t_id", help_text="从KGC获得的部分密钥")
    partial_key_hash = models.CharField(max_length=64, verbose_name="部分密钥哈希c", help_text="部分密钥哈希值")
    system_params = models.ForeignKey(SystemParameters, on_delete=models.CASCADE, verbose_name="系统参数", help_text="关联的系统参数")
    blockchain_tx_hash = models.CharField(max_length=66, blank=True, verbose_name="区块链交易哈希", help_text="存储到区块链的交易哈希")
    blockchain_stored = models.BooleanField(default=False, verbose_name="是否已存储到区块链", help_text="公钥是否已存储到区块链")
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='active', verbose_name="状态", help_text="密钥对状态")
    class Meta:
        verbose_name = "Falcon密钥对"
        verbose_name_plural = "Falcon密钥对"
        db_table = f"{table_prefix}pqkds_falcon_keypairs"
    def __str__(self):
        return f"Falcon密钥-{self.user_id}({self.node.name})"
class KeyDistributionLog(CoreModel):
    ACTION_CHOICES = [
        ('system_setup', '系统初始化'),
        ('partial_key_gen', '部分密钥生成'),
        ('user_key_gen', '用户密钥生成'),
        ('blockchain_store', '区块链存储'),
        ('key_update', '密钥更新'),
        ('key_revoke', '密钥撤销'),
        # 任务书「预分配」：从池子里取用一条资源并建立会话。
        # ⚠️ 这两个值此前**没有任何写入点**，是本次补上的：新流程（节点到节点、
        #    节点侧生成 K）在这之前一条流水都不写，于是「分发记录」页恒空 ——
        #    页面没错，是没人写它。
        ('pool_consume', '预分配取用（建立会话）'),
        ('pool_prealloc', '预分配上传'),
    ]
    falcon_keypair = models.ForeignKey(FalconKeyPair, on_delete=models.CASCADE, null=True, blank=True, verbose_name="Falcon密钥对", help_text="关联的Falcon密钥对")
    node = models.ForeignKey(Node, on_delete=models.CASCADE, verbose_name="相关节点", help_text="操作相关的节点")
    action = models.CharField(max_length=30, choices=ACTION_CHOICES, verbose_name="操作", help_text="执行的操作类型")
    details = models.TextField(blank=True, verbose_name="详细信息", help_text="操作详细信息")
    blockchain_tx_hash = models.CharField(max_length=66, blank=True, verbose_name="区块链交易哈希", help_text="相关的区块链交易哈希")
    ip_address = models.GenericIPAddressField(null=True, blank=True, verbose_name="IP地址", help_text="操作来源IP地址")
    timestamp = models.DateTimeField(auto_now_add=True, verbose_name="时间戳", help_text="操作时间戳")
    success = models.BooleanField(default=True, verbose_name="是否成功", help_text="操作是否成功")
    error_message = models.TextField(blank=True, verbose_name="错误信息", help_text="操作失败时的错误信息")
    class Meta:
        verbose_name = "密钥分发日志"
        verbose_name_plural = "密钥分发日志"
        db_table = f"{table_prefix}pqkds_key_distribution_log"
        ordering = ['-timestamp']
    def __str__(self):
        return f"{self.action} - {self.node.name} - {self.timestamp}"
class NodeKeyVersion(CoreModel):
    node = models.OneToOneField(Node, on_delete=models.CASCADE, related_name='key_versions', verbose_name="节点", help_text="关联的节点")
    kyber_version = models.IntegerField(default=1, verbose_name="Kyber密钥版本", help_text="Kyber密钥的版本号")
    falcon_version = models.IntegerField(default=1, verbose_name="Falcon密钥版本", help_text="Falcon密钥的版本号")
    kyber_public_key_hash = models.CharField(max_length=64, verbose_name="Kyber公钥哈希", help_text="当前Kyber公钥的SHA256哈希")
    falcon_public_key_hash = models.CharField(max_length=64, verbose_name="Falcon公钥哈希", help_text="当前Falcon公钥的SHA256哈希")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间", help_text="版本最后更新时间")
    class Meta:
        verbose_name = "节点密钥版本"
        verbose_name_plural = "节点密钥版本"
        db_table = f"{table_prefix}pqkds_node_key_versions"
    def __str__(self):
        return f"{self.node.name} - Kyber v{self.kyber_version}, Falcon v{self.falcon_version}"

class ChainKeyBinding(models.Model):
    """登记事务中的公开量快照兼 Outbox；不是旧链 Transaction 的替身。

    密钥 ACTIVE 是本地事实，CONFIRMED 是链上证据，不能拿后者覆盖前者。
    元数据创建后不改；同节点 sequence 在锁住 Node 行后分配，避免旧投影追上新版本。
    """
    STATES = tuple((s, s) for s in (
        'PENDING', 'PREPARED', 'SUBMITTED', 'PENDING_VERIFICATION',
        'CONFIRMED', 'FAILED', 'NOT_CONFIGURED', 'UNSUPPORTED',
    ))
    id = models.BigAutoField(primary_key=True)
    provider = models.CharField(max_length=20, default='FABRIC_DID')
    chain_id = models.CharField(max_length=128, blank=True, default='')
    namespace = models.CharField(max_length=80, default='kms-key-binding-v1')
    # 允许原管理接口删除源节点/密钥，但链证据的公开量快照不可随 CASCADE 丢失。
    # 未提交任务失去源行后由 worker 明确失败；已经确认的历史证据保留。
    node = models.ForeignKey(Node, on_delete=models.SET_NULL, null=True, blank=True, related_name='chain_key_bindings')
    long_term_key = models.ForeignKey('NodeLongTermKey', on_delete=models.SET_NULL, null=True, blank=True, related_name='chain_bindings')
    node_id_snapshot = models.CharField(max_length=64)
    algorithm = models.CharField(max_length=20)
    key_id = models.CharField(max_length=64)
    key_version = models.PositiveIntegerField()
    key_ref = models.CharField(max_length=256)
    event_type = models.CharField(max_length=20)
    key_status = models.CharField(max_length=20)
    sequence = models.PositiveBigIntegerField()
    event_id = models.CharField(max_length=64, unique=True)
    metadata = models.TextField()
    metadata_digest = models.CharField(max_length=64)
    status = models.CharField(max_length=24, choices=STATES, default='PENDING', db_index=True)
    did = models.CharField(max_length=512, blank=True, default='')
    tx_id = models.CharField(max_length=256, blank=True, default='')
    nonce = models.TextField(blank=True, default='')
    submit_started = models.BooleanField(default=False)
    transaction_valid = models.BooleanField(default=False)
    metadata_matches = models.BooleanField(default=False)
    lease_token = models.CharField(max_length=32, blank=True, default='')
    lease_until = models.DateTimeField(null=True, blank=True)
    attempts = models.PositiveIntegerField(default=0)
    last_error = models.CharField(max_length=255, blank=True, default='')
    recorded_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = f'{table_prefix}pqkds_chain_key_bindings'
        ordering = ['node_id', 'sequence']
        constraints = [
            models.UniqueConstraint(fields=['provider', 'chain_id', 'namespace', 'key_ref', 'event_type', 'key_status'], name='pqkds_binding_uniq_event'),
            models.UniqueConstraint(fields=['node', 'sequence'], name='pqkds_binding_node_sequence'),
        ]
        indexes = [models.Index(fields=['node', 'status', 'sequence'], name='pqkds_binding_node_state')]


class NodeLongTermKey(CoreModel):
    """节点的长期密钥版本记录（计划 §6.1 / KMS-004）。

    为什么不能继续只用 `Node` 上那几列
    ---------------------------------
    `Node` 用 `kyber_public_key` / `gm_public_key` / `sscl_public_key` /
    `falcon_sign_public_key` 四个 TextField 表达"这个节点有哪些长期密钥"。
    这套表达缺三样东西，而三样都是计划明确要求的：

      * **版本** —— 轮换后旧公钥被覆盖，历史信封引用的那一版**再也查不回来**。
        而信封验签必须按"签名时那版公钥"验，不是按当前公钥；
      * **状态** —— `Node.status` 是**节点**的状态（active/pending/disabled），
        表达不了"这一把已回收"。此前只能靠把列清空来表达，而清空同时抹掉审计线索；
      * **归属与有效期** —— `expires_at` / `revoked_at` / `device_id` 无处可放。

    与 `NodeKeyVersion` 的关系
    -------------------------
    `NodeKeyVersion` 是 OneToOne(Node)、只有 kyber/falcon 两个版本号和两个哈希，
    是上一轮的半成品：连 SM2/SSCL 都没有，也存不下公钥本身（历史版本更是无从谈起）。
    本模型取代它。`NodeKeyVersion` 保留为只读历史 —— 迁移 0016 不碰它，
    因为它表达的是"当前版本号"，而当前版本号可以从本表 status=ACTIVE 的行推出。

    与 `Node.*_public_key` 的关系（**重要，别搞反**）
    ----------------------------------------------
    那四列**不删**，继续作为"当前生产版本"的加速读路径（大量既有代码直接
    `node.kyber_public_key` 取值，改遍所有读点收益只是少一处冗余）。
    本表是唯一事实来源，那四列是它的物化视图，由 `node_key_registry` 的登记
    路径保证同步。长期双写，不是临时过渡 —— 见 doc/kms-callsite-inventory.md §六。
    """

    node = models.ForeignKey(
        Node, on_delete=models.CASCADE, related_name='long_term_keys',
        verbose_name="所属节点",
    )
    #: 逻辑密钥标识。新建密钥产生新 key_id；**更新保留 key_id 只递增版本** ——
    #: 这是"更新"与"新建"在数据上的唯一区别（计划 §6.1）。
    key_id = models.CharField(max_length=64, db_index=True, verbose_name="密钥标识")
    key_version = models.PositiveIntegerField(default=1, verbose_name="密钥版本")
    algorithm = models.CharField(
        max_length=20,
        choices=[(a, a) for a in ('SM2', 'SSCL', 'KYBER', 'FALCON')],
        verbose_name="算法",
        help_text="SM2 / SSCL / KYBER 可保护 SM4；FALCON 只签名",
    )
    status = models.CharField(
        max_length=20, choices=list(KEY_STATUS_CHOICES), default=KEY_STATUS_PENDING,
        db_index=True, verbose_name="状态",
    )
    #: **`status` 的派生列**，不是独立状态：status=ACTIVE 时等于 algorithm，
    #: 其余情况为 NULL。存在的唯一目的是让下面那条唯一约束真的生效。
    #:
    #: 为什么不用「部分唯一索引」（`UniqueConstraint(condition=Q(status='ACTIVE'))`）：
    #: 本项目跑在 **MySQL** 上，而 MySQL 不支持部分索引。Django 遇到不支持的
    #: 后端时 `_create_unique_sql()` 直接 return None —— **不报错、不建索引**，
    #: 只在 `makemigrations` 的输出里看不出任何异常。也就是说那条约束会看起来
    #: 写在代码里、实际上从不存在，而"同一节点同一算法最多一个 ACTIVE"这条
    #: 不变量就只剩应用层判断 —— 并发下必然双双通过。
    #:
    #: 换个不依赖后端特性的写法：MySQL（与 SQLite/PostgreSQL）的唯一索引都
    #: **忽略 NULL**，所以 (node, active_slot) 上的普通唯一约束的效果恰好是
    #: "每个节点每种算法最多一行非 NULL" —— 正是要的那条规则。
    #:
    #: 由 `save()` 自动派生，调 `.update()` 的路径（见 node_key_registry）必须
    #: 自己带上它。
    active_slot = models.CharField(
        max_length=20, null=True, blank=True, default=None, editable=False,
        verbose_name="生产槽位", help_text="status=ACTIVE 时为算法名，否则 NULL",
    )
    public_key = models.TextField(verbose_name="公钥", help_text="公开量，可自由落库与展示")
    #: 公钥摘要，64 位十六进制 sha256。摘要算的是**存储形式的字符串**（Kyber 是
    #: base64、其余是小写 hex），不是解码后的字节 —— 因为不同编码的同一把密钥
    #: 字节相同而摘要不同，用存储形式才能保证"同一行永远同一摘要"。
    public_key_hash = models.CharField(max_length=64, verbose_name="公钥SHA256")
    security_level = models.CharField(
        max_length=20, blank=True, default='', verbose_name="安全级别",
        help_text="Kyber: 512/768/1024；Falcon: 512/1024；SM2/SSCL: sm2p256v1",
    )
    #: 私钥所在设备。与 `Node.key_device_id` 同源，但按**每个密钥版本**记录 ——
    #: 换了设备后重新生成的那一版属于新设备，旧版本仍属于旧设备。
    device_id = models.CharField(
        max_length=128, blank=True, default='', verbose_name="私钥所在设备",
        help_text="生成并持有该版本私钥的设备标识；换设备后新版本记新设备",
    )
    effective_at = models.DateTimeField(null=True, blank=True, verbose_name="生效时间")
    expires_at = models.DateTimeField(null=True, blank=True, verbose_name="过期时间")
    revoked_at = models.DateTimeField(null=True, blank=True, verbose_name="回收时间")
    revoked_reason = models.CharField(max_length=255, blank=True, default='', verbose_name="回收原因")
    #: 迁移 0016 回填的行。与 status=LEGACY 是**两件事**：
    #: `legacy=True` 表示"这行来自旧列的回填"，`status=LEGACY` 表示
    #: "来源不明、不可用于解封"。回填出来的**当前生产版本**是 legacy=True 但
    #: status=ACTIVE —— 把它标成 LEGACY 状态会让现网正在用的节点立刻不可用。
    legacy = models.BooleanField(default=False, verbose_name="回填的历史记录")
    legacy_source = models.CharField(
        max_length=64, blank=True, default='', verbose_name="回填来源列",
        help_text="从 Node 的哪一列回填而来；新登记路径写的行为空",
    )

    class Meta:
        verbose_name = "节点长期密钥"
        verbose_name_plural = "节点长期密钥"
        db_table = f"{table_prefix}pqkds_node_long_term_keys"
        ordering = ['node_id', 'algorithm', '-key_version']
        constraints = [
            models.UniqueConstraint(
                fields=['node', 'algorithm', 'key_id', 'key_version'],
                name='pqkds_ltk_uniq_node_alg_id_ver',
            ),
            # 计划 §6.1「同一节点、同一算法最多一个生产中的主版本」。
            # 靠 `active_slot`（status 的派生列，ACTIVE 时为算法名、否则 NULL）
            # 而不是部分唯一索引 —— 见 active_slot 字段上的注释：MySQL 不支持
            # 部分索引，Django 会**静默跳过**那条约束。
            models.UniqueConstraint(
                fields=['node', 'active_slot'],
                name='pqkds_ltk_uniq_active_per_node_alg',
            ),
        ]
        indexes = [
            models.Index(fields=['node', 'algorithm', 'status'], name='pqkds_ltk_node_alg_status'),
            models.Index(fields=['expires_at'], name='pqkds_ltk_expires_at'),
        ]

    def save(self, *args, **kwargs):
        """落库前派生 `active_slot`，使它与 `status` 不可能脱节。

        放在 `save()` 里而不是各调用点，是因为脱节的后果是**唯一约束静默失效**：
        status 改成 RETIRED 而 active_slot 仍是 'KYBER' 时，下一次登记会撞唯一约束
        （表现为"莫名其妙登记不上"）；反过来 status=ACTIVE 而 active_slot 为 NULL 时，
        约束根本拦不住第二个 ACTIVE（表现为"同一算法两把在产"）。两种都不会报错。
        """
        self.active_slot = self.algorithm if self.status == KEY_STATUS_ACTIVE else None
        update_fields = kwargs.get('update_fields')
        if update_fields is not None:
            update_fields = set(update_fields)
            if 'status' in update_fields or 'algorithm' in update_fields:
                update_fields.add('active_slot')
            kwargs['update_fields'] = update_fields
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.node.node_id}/{self.algorithm}/{self.key_id}/v{self.key_version}({self.status})"

    @property
    def is_expired(self) -> bool:
        """是否已过期。状态被显式标成 EXPIRED、或过期时间已到。"""
        if self.status == KEY_STATUS_EXPIRED:
            return True
        return bool(self.expires_at and self.expires_at <= timezone.now())

    @property
    def allows_new_work(self) -> bool:
        """能否用于**新**封装 / 新签名 / 新预分配。"""
        return key_status_allows_new_work(self.status) and not self.is_expired

    @property
    def allows_unwrap(self) -> bool:
        """能否用于解开**已存在**的信封。

        ⚠️ 与 `allows_new_work` 的差集就是"回收后禁止新分发"这句话：
            RETIRED / EXPIRED 允许解旧信封，但不允许产生新信封。
        """
        return key_status_allows_unwrap(self.status) and not self.is_expired

    @property
    def fingerprint(self) -> str:
        """公钥摘要，形如 `sha256:abcd…`。信封引用公钥版本时用它做对账。"""
        return f"sha256:{self.public_key_hash}"

    def mark_revoked(self, reason: str = '') -> None:
        """就地标记回收（不落库，由调用方 save）。"""
        self.status = KEY_STATUS_REVOKED
        self.revoked_at = timezone.now()
        self.revoked_reason = (reason or '')[:255]

class PreDistributedKey(CoreModel):
    """基于格的安全密钥预分配 - 密钥池模型"""
    ALGORITHM_CHOICES = [
        ('kyber_kem', 'Kyber KEM'),
        ('falcon_lattice', 'Falcon 格密码'),
    ]
    #: 密钥池项状态（KMS-013 归口）。
    #:
    #: 「什么算可用」「允许哪些迁移」由 `api_contract` 的
    #: `POOL_TRANSITIONS` / `pool_transition_allowed` 表达，服务层与页面
    #: 都从那一处取 —— 在这里另写一套必然漂移。
    #:
    #: ⚠️ `RESERVED` 是**保留值**：当前没有任何生产写入点，也刻意没有
    #: （消费是单事务的"选中 → 标记"，中间窗口为零，没有需要预留的时间段）。
    #: 留着它是为了不破坏既有取值面；`api_contract.POOL_TRANSITIONS` 里
    #: 也**没有**任何指向它的边，强行写入会被状态机拒绝。
    #:
    #: ⚠️ 旧值 `unused` / `used` / `distributed` 仍保留在 choices 里：
    #: 库里已有按旧值写入的历史行，收紧掉会让它们无法被任何查询命中。
    #: 读取方应统一用 `KeyPoolService.POOL_STATUS_READY_VALUES` /
    #: `api_contract.normalize_pool_status` 表达"什么算可用"，而不是在
    #: 各处分别兼容两套拼写。
    STATUS_CHOICES = [
        ('READY', '已预分配，可被会话取用'),
        ('RESERVED', '保留值：从未产生（见 api_contract.POOL_TRANSITIONS）'),
        ('CONSUMED', '已成功建立会话，不可再次使用'),
        ('EXPIRED', '超过有效期'),
        ('REVOKED', '依赖的长期密钥已回收或检测异常'),
        # --- 历史值（只读兼容，不再产生） ---
        ('unused', '未使用（历史值，等价 READY）'),
        ('used', '已使用（历史值，等价 CONSUMED）'),
        ('expired', '已过期（历史值，等价 EXPIRED）'),
        ('distributed', '已下发（历史值，等价 CONSUMED）'),
    ]
    #: 载荷层（被封装的那把对称密钥）用的算法。与上面的 `algorithm` 是两回事：
    #: `algorithm` 是**封装**算法（Kyber/Falcon），本字段是**载荷**算法。
    #: D3 之后载荷统一为 SM4；历史行为 AES-256，由迁移脚本回填为 aes_256。
    PAYLOAD_ALGORITHM_CHOICES = [
        ('sm4', '国密 SM4-GCM'),
        ('aes_256', 'AES-256-GCM（历史数据）'),
    ]
    pool_id = models.CharField(max_length=64, verbose_name="密钥池ID", help_text="标识一次批量预分配的批次ID")
    key_index = models.IntegerField(verbose_name="密钥序号", help_text="该密钥在批次中的序号")
    node1 = models.ForeignKey(Node, on_delete=models.CASCADE, related_name='predist_keys_as_node1', verbose_name="节点1", help_text="密钥对的第一个节点；用户发起时为收件节点")
    # `node2` 可空：这张表原本只表达**节点间**预分配（两个节点都不能少），
    # 而用户发起的「分发」只有**一个**收件节点 —— 硬要求 node2 会让那条路径无处落脚。
    # 计划 §4.3 当初另建 `user_key_envelopes` 正是为了绕开这个约束，
    # 但**节点那一份仍需一个落脚处**，所以这里放开为可空，
    # 并用 §4.1 新增的 `recipient_type` 区分两种语义。
    node2 = models.ForeignKey(Node, on_delete=models.CASCADE, related_name='predist_keys_as_node2',
                              null=True, blank=True, verbose_name="节点2",
                              help_text="密钥对的第二个节点；recipient_type=user 时为空")
    algorithm = models.CharField(max_length=20, choices=ALGORITHM_CHOICES, verbose_name="加密算法", help_text="预分配使用的格密码算法（封装算法）")
    payload_algorithm = models.CharField(
        max_length=20,
        choices=PAYLOAD_ALGORITHM_CHOICES,
        default='sm4',
        verbose_name="载荷算法",
        help_text="被封装的对称密钥所用算法：sm4（新）/ aes_256（历史数据，由迁移脚本回填）",
    )
    # --- 用户腿分发（P3）新增的三个字段 ---
    # `algorithm` 是**封装**算法，历史上只有 kyber_kem / falcon_lattice 两种取值；
    # D3+D4 之后需要表达"用哪把用户非对称密钥把载荷封给谁"，
    # 因此补上封装算法、来源密钥与收件人。`algorithm` 保留不删（兼容既有数据）。
    wrapping_algorithm = models.CharField(
        max_length=20, null=True, blank=True,
        verbose_name="封装算法",
        help_text="kyber_kem / falcon_lattice / sm2 / sscl；新逻辑一律读写本字段",
    )
    source_key_id = models.BigIntegerField(
        null=True, blank=True, verbose_name="来源密钥ID",
        help_text="用户所选非对称密钥的 kms.keymanage.key_id（逻辑引用，不建跨库外键）",
    )
    # --- KMS-007：记住"这一项是用哪把长期密钥封的" ---
    # 池项里的密文是用**某一把具体版本**的长期公钥封的。那把密钥一旦被回收，
    # 这一项就永远解不开了 —— 但在补齐这两列之前，表里**没有任何字段**记得住
    # 是哪一把：`algorithm` / `wrapping_algorithm` 只到算法家族（kyber_kem /
    # falcon_lattice），`source_key_id` 指的是**另一个库**的旧模型，只管用户腿。
    #
    # 后果是回收任何一个算法的一把密钥时，只能按 `node_id` 把该节点**全部**
    # READY/RESERVED 池项一次清空 —— 包括用其它仍然有效的算法封的那些。
    # 而 `revoke_pool_items_for_key(node_id, key_id, version)` 的签名收着
    # `key_id`/`version` 两个参数、日志里也逐字印着它们，读日志的人会以为
    # 它是精确失效的。**参数进不了查询，是因为数据本来就不在表里。**
    #
    # ⚠️ 两列都可空，且**历史行一律为 NULL**：迁移不回填（回填只能靠猜，
    #    而猜错的后果是"回收时漏掉本该失效的池项"，静默留下一条永远解不开
    #    却显示 READY 的条目 —— 正是这张表最该避免的那种失败）。
    #    回收路径对 NULL 行退化为"同节点 + 同算法"匹配，并在日志里如实写明
    #    退化范围，不假装精确。
    long_term_key_id = models.CharField(
        max_length=64, null=True, blank=True, verbose_name="长期密钥标识",
        help_text="封这一项时所用 NodeLongTermKey.key_id；历史行为 NULL（无法可靠回填）",
    )
    long_term_key_version = models.PositiveIntegerField(
        null=True, blank=True, verbose_name="长期密钥版本",
        help_text="封这一项时所用 NodeLongTermKey.key_version；历史行为 NULL",
    )
    recipient_type = models.CharField(
        max_length=10, default='node', verbose_name="收件人类型",
        help_text="pool=预分配池里的待取用资源；node=已取用/已交付给接收节点的信封；user=分发给用户本人",
    )
    recipient_user_id = models.BigIntegerField(
        null=True, blank=True, verbose_name="收件用户ID",
        help_text="recipient_type=user 时的 kms.sys_user.user_id（逻辑引用，不建外键）",
    )
    encrypted_key_data = models.TextField(verbose_name="加密的密钥数据", help_text="使用格密码封装后的对称会话密钥（JSON）")
    key_hash = models.CharField(max_length=64, verbose_name="密钥哈希", help_text="对称密钥的SHA256哈希，用于校验")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='READY', verbose_name="状态", help_text="密钥当前状态；可用性与迁移规则见 api_contract.POOL_TRANSITIONS")
    used_at = models.DateTimeField(null=True, blank=True, verbose_name="使用时间", help_text="密钥被消耗的时间")
    used_by_session = models.ForeignKey(SessionKey, on_delete=models.SET_NULL, null=True, blank=True, related_name='predist_key', verbose_name="使用该密钥的会话", help_text="消耗此密钥的会话")
    expires_at = models.DateTimeField(verbose_name="过期时间", help_text="密钥过期时间")
    generation_time_ms = models.FloatField(null=True, blank=True, verbose_name="生成耗时(ms)", help_text="单条密钥生成耗时")

    class Meta:
        verbose_name = "预分配密钥"
        verbose_name_plural = "预分配密钥"
        db_table = f"{table_prefix}pqkds_pre_distributed_keys"
        ordering = ['-create_datetime']
        unique_together = [('pool_id', 'key_index')]
        indexes = [
            models.Index(fields=['node1', 'node2', 'status', 'algorithm']),
            models.Index(fields=['pool_id']),
            models.Index(fields=['status', 'expires_at']),
        ]

    def __str__(self):
        return f"预分配密钥-{self.pool_id[:8]}#{self.key_index}({self.get_algorithm_display()})"


class SessionKeyInvalidation(CoreModel):
    INVALIDATION_REASON_CHOICES = [
        ('node1_key_updated', '节点1密钥已更新'),
        ('node2_key_updated', '节点2密钥已更新'),
        ('both_keys_updated', '两个节点密钥都已更新'),
        ('manual_revocation', '手动撤销'),
    ]
    session = models.ForeignKey(SessionKey, on_delete=models.CASCADE, related_name='invalidations', verbose_name="会话", help_text="被失效的会话")
    invalidated_node = models.ForeignKey(Node, on_delete=models.CASCADE, related_name='invalidated_sessions', verbose_name="触发失效的节点", help_text="密钥更新导致会话失效的节点")
    reason = models.CharField(max_length=30, choices=INVALIDATION_REASON_CHOICES, verbose_name="失效原因", help_text="会话失效的原因")
    kyber_version_before = models.IntegerField(null=True, blank=True, verbose_name="失效前Kyber版本", help_text="失效前节点的Kyber密钥版本")
    falcon_version_before = models.IntegerField(null=True, blank=True, verbose_name="失效前Falcon版本", help_text="失效前节点的Falcon密钥版本")
    kyber_version_after = models.IntegerField(null=True, blank=True, verbose_name="失效后Kyber版本", help_text="失效后节点的Kyber密钥版本")
    falcon_version_after = models.IntegerField(null=True, blank=True, verbose_name="失效后Falcon版本", help_text="失效后节点的Falcon密钥版本")
    invalidated_at = models.DateTimeField(auto_now_add=True, verbose_name="失效时间", help_text="会话失效的时间")
    class Meta:
        verbose_name = "会话密钥失效记录"
        verbose_name_plural = "会话密钥失效记录"
        db_table = f"{table_prefix}pqkds_session_key_invalidations"
        ordering = ['-invalidated_at']
        indexes = [
            models.Index(fields=['session', '-invalidated_at']),
            models.Index(fields=['invalidated_node', '-invalidated_at']),
        ]
    def __str__(self):
        return f"会话 {self.session.session_id[:8]}... - {self.reason}"

# =============================================================================
# 用户腿分发（P3）新增的三张表
# -----------------------------------------------------------------------------
# 身份打通说明（D7 / 计划 §4.5）：`falcon_kds` 侧一律用 `user_id` **逻辑引用**
# `kms.sys_user.user_id`，**不建跨库外键** —— MySQL 不支持跨库外键，
# 而且两库本就由不同服务负责，硬绑会让迁移相互阻塞。
# 主身份源永远是 `kms.sys_user`；`dvadmin_system_users` 只是节点侧附属信息。
# =============================================================================


class UserNodeAuthorization(CoreModel):
    """**通信授权**：某个登录主体可以向某个节点分发 / 与它建立会话。

    这张表同时承担两种关系，`user_id` 在两处都指 `kms.sys_user.user_id`：

    * **节点 ↔ 节点（当前）**：`user_id` 就是发起方节点的 `Node.sys_user_id`
      （建节点时由 `node_account_service.ensure_node_account` 建好，一一对应）。
      节点侧的「节点授权」页发起申请、管理员批准后写在这里 —— 见
      `NodeAuthorizationRequest`。
    * **用户 ↔ 节点（历史）**：旧「用户腿」分发里，`user_id` 是普通用户账号。
      `user_distribution_views` 那条路径还在用它。

    ⚠️ 早先本类的注释写的是"用户与节点是两个实体、属于待删语义"（因为当时
       只有用户腿）。节点多级授权落地后这句话不再成立：节点场景下 `user_id`
       与本节点是**同一实体**，这不是过渡写法，而是本表要长期承担的关系。
       **判据仍然只有一条**：`distribution_service.authorized_node_ids(user_id)`
       —— 申请审批只写本表，不做第二套放行判据（理由见 `NodeAuthorizationRequest`）。
    """

    STATUS_CHOICES = [
        ('active', '有效'),
        ('revoked', '已撤销'),
    ]

    user_id = models.BigIntegerField(verbose_name="用户ID", help_text="kms.sys_user.user_id（逻辑引用，不建跨库外键）；节点场景下即 Node.sys_user_id")
    node = models.ForeignKey(
        Node, on_delete=models.CASCADE, related_name='user_authorizations',
        verbose_name="节点", help_text="被授权的节点",
    )
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='active', verbose_name="状态")
    granted_by = models.CharField(max_length=64, null=True, blank=True, verbose_name="授权人", help_text="执行授权的管理员；节点审批路径写「审批:管理员名」")
    granted_at = models.DateTimeField(default=timezone.now, verbose_name="授权时间")
    revoked_at = models.DateTimeField(null=True, blank=True, verbose_name="撤销时间")
    remark = models.CharField(max_length=500, null=True, blank=True, verbose_name="备注")

    class Meta:
        verbose_name = "用户节点授权"
        verbose_name_plural = "用户节点授权"
        db_table = f"{table_prefix}pqkds_user_node_authorizations"
        ordering = ['-granted_at']
        # 同一用户对同一节点只应有一条记录：重复授权会让"到底有没有权限"依赖遍历顺序
        unique_together = [('user_id', 'node')]
        indexes = [
            models.Index(fields=['user_id', 'status']),
        ]

    def __str__(self):
        return f"用户{self.user_id}-节点{self.node_id}({self.status})"


class NodeAuthorizationRequest(CoreModel):
    """节点发起的**通信授权申请**（任务书「节点多级授权」）。

    流程：节点看到全网名录 → 选对端 → 发起申请（本表 `pending`）
          → 管理员批准/驳回 → 批准时**真的写出** `UserNodeAuthorization` 两行。

    <h2>为什么不复用已下线的 permission_request</h2>
    仓库原先有一整套申请审批（`kms-ops/mysql/init/06_permission_request.sql`），
    阶段 8 被整体下线，理由写在 `35_remove_permission_request_menu.sql`：
    它的 `approve()` **刻意不调用 `updateRoleLevel`** —— "审批通过不授予任何权限"，
    保留只会形成**第二套权限语义**（出事时没人能说清"当时到底凭什么被允许"）。

    ⚠️ 本表**不重蹈那个覆辙**：它只记录**过程**，一行权限都不表达。
       放行判据永远是 `UserNodeAuthorization`（唯一读点
       `distribution_service.authorized_node_ids`）。本表 `status='approved'`
       不构成任何放行理由 —— 批准动作本身就是"写那两行授权"。

    <h2>方向</h2>
    批准时默认**双向**：`requester.sys_user_id → target` 与
    `target.sys_user_id → requester` 各写一行。因此本表一条申请代表"这一对节点
    之间的互通"，而不是单向。管理员手工只授单向是允许的（既有页面做得到），
    名录会如实显示不对称并允许补齐 —— 见 `node_self_views.node_directory`。

    <h2>唯一性（含并发）</h2>
    同一对节点（**无序**）同时只允许一条 `pending`。`unique_together` 表达不了
    "无序对"，而**只在视图里查一遍是不够的** —— 同一个节点的两个标签页同时点
    「申请」时，`select_for_update` 锁的是**已存在的行**，两边的行都还不存在，
    于是两边都插入成功。所以唯一性落在下面这个列上：

      * `pending_key` 在 `status='pending'` 时是 `"{申请人id}-{目标id}"`，
        离开 pending（批准/驳回/撤回）即置 `NULL`；
      * 列上有 `unique=True`，而 MySQL（与 SQLite/PostgreSQL）的唯一索引
        **允许多个 NULL** —— 于是"同时只有一条 pending"由数据库保证，
        而历史行（NULL）不受任何限制。

    ⚠️ 写入/清除 `pending_key` **只允许经 `node_authorization_service`** ——
       在别处手写会漏掉某条路径（比如新加一种终态时忘了置 NULL），
       而漏掉的表现是"这一对节点再也申请不了"（旧 pending 的键一直占着）。

    被拒/撤回后可以再次申请：新起一行，旧行保留作审计。
    """

    STATUS_CHOICES = [
        ('pending', '待审批'),
        ('approved', '已批准'),
        ('rejected', '已驳回'),
        ('cancelled', '已撤回'),
    ]

    requester = models.ForeignKey(
        Node, on_delete=models.CASCADE, related_name='authorization_requests_out',
        verbose_name="申请节点", help_text="发起申请的节点",
    )
    target = models.ForeignKey(
        Node, on_delete=models.CASCADE, related_name='authorization_requests_in',
        verbose_name="目标节点", help_text="希望与之建立会话的节点",
    )
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending',
                              verbose_name="状态")
    reason = models.CharField(max_length=200, verbose_name="申请理由",
                              help_text="节点侧填写的用途，展示给审批人")
    decided_by = models.CharField(max_length=64, null=True, blank=True, verbose_name="审批人")
    decided_at = models.DateTimeField(null=True, blank=True, verbose_name="审批时间")
    decision_remark = models.CharField(max_length=500, null=True, blank=True, verbose_name="审批意见")
    #: 批准/驳回的链上哈希。空串 = 存证未成功（链不可用等），**如实留空** ——
    #: 与分发/更新/回收同一口径：不把"存证未成功"混成一句"成功"。
    chain_tx = models.CharField(max_length=128, null=True, blank=True, verbose_name="链上存证哈希")
    #: 只在 `status='pending'` 时有值（`"{申请人id}-{目标id}"`），其余状态为 NULL。
    #: 见类 docstring「唯一性（含并发）」—— 这是"一对节点同时只有一条 pending"
    #: 落在数据库上的表达；MySQL 唯一索引允许多个 NULL，历史行因此不受限。
    pending_key = models.CharField(max_length=64, null=True, blank=True, unique=True,
                                   verbose_name="未决去重键",
                                   help_text="pending 时 = {申请人id}-{目标id}，其余状态为 NULL")
    #: 一次**批量提交**的组号（`authreq-<yyyyMMddHHmmss>-<8hex>`，由节点侧生成）。
    #: NULL = 单目标申请（本列引入之前的历史行，以及仍走单目标路径的调用）。
    #:
    #: ⚠️ 组**只用于展示与批量操作**，**没有组级状态** —— 每条申请仍是独立一行、
    #:    独立生命周期。理由：管理员部分批准是真实需求（10 个里有一个不该放行），
    #:    而一旦引入"组已批准"，它就变成了第二个放行判据 ——
    #:    正是本类 docstring 开头那段"第二套权限语义"的历史教训。
    batch_id = models.CharField(max_length=64, null=True, blank=True, verbose_name="批量申请组号",
                                help_text="一次多选提交共用一个组号；单目标申请为 NULL")
    batch_seq = models.IntegerField(null=True, blank=True, verbose_name="组内序号",
                                    help_text="仅用于按提交顺序展示，不参与任何判据")

    class Meta:
        verbose_name = "节点授权申请"
        verbose_name_plural = "节点授权申请"
        db_table = f"{table_prefix}pqkds_node_authorization_requests"
        ordering = ['-create_datetime']
        indexes = [
            models.Index(fields=['status', 'create_datetime']),
            models.Index(fields=['requester', 'status']),
            models.Index(fields=['target', 'status']),
        ]

    def __str__(self):
        return f"{self.requester_id}→{self.target_id}({self.status})"


class UserKeyEnvelope(CoreModel):
    """分发到**用户本人**的对称密钥信封（计划 §4.3）。

    刻意不复用 `PreDistributedKey`：那张表的 `node1`/`node2` 都是 `NOT NULL`，
    而用户侧没有 `node2`，硬塞进去会产生大量可空外键。

    「对称密钥查看」页就读这张表。**不存明文对称密钥**，只有哈希与密文信封。
    """

    STATUS_CHOICES = [
        ('unused', '未使用'),
        ('used', '已使用'),
        ('expired', '已过期'),
    ]

    batch_id = models.CharField(max_length=64, verbose_name="批次号", help_text="一次分发动作的批次号")
    user_id = models.BigIntegerField(verbose_name="用户ID", help_text="kms.sys_user.user_id（逻辑引用）")
    key_hash = models.CharField(max_length=64, verbose_name="密钥哈希", help_text="SM4 密钥的 SHA256，用于核对，不存明文")
    encrypted_key_data = models.TextField(
        verbose_name="加密的密钥数据",
        help_text="用用户所选非对称密钥加密后的 SM4 密钥（JSON：算法 + 密文 + 目标公钥）",
    )
    wrapping_algorithm = models.CharField(
        max_length=20, verbose_name="封装算法", help_text="SM2 / SSCL（D17：用户腿只允许这两种）",
    )
    source_key_id = models.BigIntegerField(
        verbose_name="来源密钥ID", help_text="用户所选非对称密钥 kms.keymanage.key_id",
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='unused', verbose_name="状态")
    expires_at = models.DateTimeField(verbose_name="过期时间", help_text="固定 24 小时（D8）")

    class Meta:
        verbose_name = "用户对称密钥信封"
        verbose_name_plural = "用户对称密钥信封"
        db_table = f"{table_prefix}pqkds_user_key_envelopes"
        ordering = ['-create_datetime']
        indexes = [
            models.Index(fields=['user_id', 'expires_at']),
            models.Index(fields=['batch_id']),
        ]

    def __str__(self):
        return f"用户{self.user_id}信封-{self.batch_id[:8]}#{self.wrapping_algorithm}"


class DistributionBatch(CoreModel):
    """用户发起的一次「选节点 + 分发」动作（计划 §4.4）。

    有了它才能回答"这次分发发给了哪些节点、成功几个、用户那份成没成"。
    也是 P5 里工作台「分发记录」KPI 与「分发状态分布」图的新数据源
    （替换掉那条派生自 Kafka 的旧链路）。
    """

    STATUS_CHOICES = [
        ('pending', '进行中'),
        ('partial', '部分成功'),
        ('success', '全部成功'),
        ('failed', '失败'),
    ]

    batch_id = models.CharField(max_length=64, unique=True, verbose_name="批次号")
    user_id = models.BigIntegerField(verbose_name="发起用户ID", help_text="kms.sys_user.user_id（逻辑引用）")
    #: KMS-008 起可空：新的节点间分发**没有**"用户来源密钥"这个概念
    #: （旧用户腿流程才有 —— 用户选一把自己的非对称密钥来解封）。
    #: 可空而不是填 0：0 会被下游当成一把真的 `kms.keymanage.key_id` 去查，
    #: 查到的是"碰巧同号的另一把密钥"，比查不到糟得多。
    source_key_id = models.BigIntegerField(
        null=True, blank=True, verbose_name="来源密钥ID",
        help_text="旧用户腿流程里用户所选的非对称密钥；节点间分发为 NULL",
    )
    wrapping_algorithm = models.CharField(max_length=20, verbose_name="封装算法", help_text="SM2 / SSCL")
    node_ids = models.TextField(verbose_name="目标节点", help_text="JSON 数组，形如 [1,2,3]")
    node_success_count = models.IntegerField(default=0, verbose_name="节点成功数")
    user_envelope_ok = models.BooleanField(default=False, verbose_name="用户信封是否成功")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, verbose_name="状态")

    # --- 阶段 5（文档 §8.5）：跨域分发标记 ---
    # 第一版不部署多套独立 KMS，只把跨域**语义与审计数据**做完整：
    # 记录发起方所属域与各目标节点所属域，据此判定同域/跨域。
    #
    # 为什么存 source_domain_id 而不是每次回查发起人所属域：
    # 人的组织归属会变（部门调动、节点换域），而"这次分发当时是不是跨域"
    # 是一个**历史事实**，不该随后续变更而改写。
    source_domain_id = models.CharField(
        max_length=64, blank=True, default='',
        verbose_name="发起方所属域", help_text="分发发起时发起方的 domain_id 快照"
    )
    target_domain_ids = models.TextField(
        blank=True, default='',
        verbose_name="目标域集合", help_text="JSON 数组，各目标节点所属域的并集快照"
    )
    distribution_type = models.CharField(
        max_length=16, blank=True, default='',
        choices=[('same', '同域'), ('cross', '跨域'), ('mixed', '混合')],
        verbose_name="分发类型",
        help_text="same=全部同域 / cross=全部跨域 / mixed=两者都有"
    )

    class Meta:
        verbose_name = "分发批次"
        verbose_name_plural = "分发批次"
        db_table = f"{table_prefix}pqkds_distribution_batches"
        ordering = ['-create_datetime']
        indexes = [
            models.Index(fields=['user_id', '-create_datetime']),
            models.Index(fields=['status']),
        ]

    def __str__(self):
        return f"批次{self.batch_id[:8]}({self.status})"
