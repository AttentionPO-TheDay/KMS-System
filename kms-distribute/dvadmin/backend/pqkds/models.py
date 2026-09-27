from django.db import models
from django.utils import timezone
from dvadmin.utils.models import CoreModel, table_prefix
import json
import hashlib
from typing import Dict, Any
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
    #   那张表是「某个用户**被授权**可以向某个节点分发」—— 用户与节点是**两个实体**；
    #   本字段是「这个节点**就是**这个账号」—— 节点与账号是**同一实体**。
    #   文档 §3 明确前者与设定二冲突，属于待删语义；本字段才是目标模型。
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
    blockchain_synced = models.BooleanField(default=False, verbose_name="是否同步到区块链", help_text="节点信息是否已同步到区块链")
    blockchain_sync_time = models.DateTimeField(null=True, blank=True, verbose_name="同步时间", help_text="节点同步到区块链的时间")
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
            ('kyber_kem', 'Kyber密钥协商')
        ],
        default='aes_falcon',
        verbose_name="会话类型",
        help_text="会话建立的协议类型"
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
    class Meta:
        verbose_name = "会话密钥"
        verbose_name_plural = "会话密钥"
        db_table = f"{table_prefix}pqkds_session_keys"
    def __str__(self):
        return f"会话-{self.node1.name}↔{self.node2.name}"
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
class PreDistributedKey(CoreModel):
    """基于格的安全密钥预分配 - 密钥池模型"""
    ALGORITHM_CHOICES = [
        ('kyber_kem', 'Kyber KEM'),
        ('falcon_lattice', 'Falcon 格密码'),
    ]
    #: 密钥池项状态（阶段 6，文档 §7.5）。
    #:
    #: 正常流转：READY → RESERVED → CONSUMED。预分配密钥**必须一次性消费**，
    #: 不能被多个会话重复使用 —— 这是整张表存在的意义所在。
    #:
    #: ⚠️ 旧值 `unused` / `used` / `distributed` 仍保留在 choices 里：
    #: 库里已有按旧值写入的历史行，收紧掉会让它们无法被任何查询命中。
    #: 读取方应统一用 `KeyPoolService.POOL_STATUS_READY_VALUES` 表达"什么算可用"
    #: （见 key_pool_service），而不是在各处分别兼容两套拼写。
    STATUS_CHOICES = [
        ('READY', '已预分配，可被会话取用'),
        ('RESERVED', '正在被某次会话占用'),
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
    recipient_type = models.CharField(
        max_length=10, default='node', verbose_name="收件人类型",
        help_text="node=节点间预分配；user=分发给用户本人",
    )
    recipient_user_id = models.BigIntegerField(
        null=True, blank=True, verbose_name="收件用户ID",
        help_text="recipient_type=user 时的 kms.sys_user.user_id（逻辑引用，不建外键）",
    )
    encrypted_key_data = models.TextField(verbose_name="加密的密钥数据", help_text="使用格密码封装后的对称会话密钥（JSON）")
    key_hash = models.CharField(max_length=64, verbose_name="密钥哈希", help_text="对称密钥的SHA256哈希，用于校验")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='READY', verbose_name="状态", help_text="密钥当前状态")
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
    """用户 ↔ 节点授权（即「节点鉴权」，计划 §4.2）。

    `Node` 模型原本**没有任何 user 外键**，而 D5 要求用户只能选择"自己有权的节点"。
    分发接口必须据此在**服务端**校验，不能只靠前端下拉过滤。
    """

    STATUS_CHOICES = [
        ('active', '有效'),
        ('revoked', '已撤销'),
    ]

    user_id = models.BigIntegerField(verbose_name="用户ID", help_text="kms.sys_user.user_id（逻辑引用，不建跨库外键）")
    node = models.ForeignKey(
        Node, on_delete=models.CASCADE, related_name='user_authorizations',
        verbose_name="节点", help_text="被授权的节点",
    )
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='active', verbose_name="状态")
    granted_by = models.CharField(max_length=64, null=True, blank=True, verbose_name="授权人", help_text="执行授权的管理员")
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
    source_key_id = models.BigIntegerField(verbose_name="来源密钥ID", help_text="用户所选非对称密钥")
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
