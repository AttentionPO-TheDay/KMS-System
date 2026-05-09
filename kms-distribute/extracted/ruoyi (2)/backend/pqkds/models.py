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
    kyber_keygen_time = models.DateTimeField(null=True, blank=True, verbose_name="Kyber密钥生成时间", help_text="Kyber密钥对生成的时间")
    kyber_keygen_duration = models.FloatField(null=True, blank=True, verbose_name="Kyber密钥生成耗时", help_text="Kyber密钥对生成花费的时间（秒）")
    falcon_keygen_time = models.DateTimeField(null=True, blank=True, verbose_name="Falcon密钥生成时间", help_text="Falcon密钥对生成的时间")
    falcon_keygen_duration = models.FloatField(null=True, blank=True, verbose_name="Falcon密钥生成耗时", help_text="Falcon密钥对生成花费的时间（秒）")
    status = models.CharField(
        max_length=20,
        choices=[
            ('registered', '已注册'),
            ('kyber_uploaded', 'Kyber公钥已上传'),
            ('partial_key_received', '部分私钥已接收'),
            ('falcon_generated', 'Falcon密钥已生成'),
            ('active', '活跃'),
            ('inactive', '非活跃')
        ],
        default='registered',
        verbose_name="节点状态",
        help_text="节点当前状态"
    )
    last_active = models.DateTimeField(default=timezone.now, verbose_name="最后活跃时间", help_text="节点最后活跃时间")
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
    STATUS_CHOICES = [
        ('unused', '未使用'),
        ('used', '已使用'),
        ('expired', '已过期'),
        ('distributed', '已下发'),
    ]
    pool_id = models.CharField(max_length=64, verbose_name="密钥池ID", help_text="标识一次批量预分配的批次ID")
    key_index = models.IntegerField(verbose_name="密钥序号", help_text="该密钥在批次中的序号")
    node1 = models.ForeignKey(Node, on_delete=models.CASCADE, related_name='predist_keys_as_node1', verbose_name="节点1", help_text="密钥对的第一个节点")
    node2 = models.ForeignKey(Node, on_delete=models.CASCADE, related_name='predist_keys_as_node2', verbose_name="节点2", help_text="密钥对的第二个节点")
    algorithm = models.CharField(max_length=20, choices=ALGORITHM_CHOICES, verbose_name="加密算法", help_text="预分配使用的格密码算法")
    encrypted_key_data = models.TextField(verbose_name="加密的密钥数据", help_text="使用格密码加密后的AES会话密钥（JSON）")
    key_hash = models.CharField(max_length=64, verbose_name="密钥哈希", help_text="AES密钥的SHA256哈希，用于校验")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='unused', verbose_name="状态", help_text="密钥当前状态")
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