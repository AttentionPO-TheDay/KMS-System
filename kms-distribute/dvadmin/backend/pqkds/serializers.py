from rest_framework import serializers
from dvadmin.utils.serializers import CustomModelSerializer
from .models import (
    SystemParameters, Node, Block, Transaction,
    SessionKey, Message, BlockchainConfig,
    FalconKeyPair, KeyDistributionLog, PreDistributedKey
)
class SystemParametersSerializer(CustomModelSerializer):
    class Meta:
        model = SystemParameters
        fields = '__all__'
        read_only_fields = ['matrix_a', 'kgc_public_key']
class NodeSerializer(CustomModelSerializer):
    class Meta:
        model = Node
        fields = '__all__'
        extra_kwargs = {
            'kyber_private_key': {'write_only': True},
            'falcon_private_key': {'write_only': True},
            'kyber_partial_key_data': {'write_only': True},
            'falcon_partial_key_data': {'write_only': True},
            'partial_key_data': {'write_only': True}
        }
class NodeCreateSerializer(CustomModelSerializer):
    class Meta:
        model = Node
        fields = [
            'node_id', 'name', 'ip_address', 'port',
            'phone', 'email', 'contact_person',
            'organization', 'department', 'location',
            'node_type', 'hardware_spec', 'description', 'tags',
            'kyber_security_level', 'falcon_security_level',
            # 阶段 2：管理员建节点时一并指定多级授权与所属域。
            # ⚠️ 漏在 fields 外面的字段会被 DRF **静默丢弃** —— 请求带着
            # permission_level='L2' 进来、模型却落默认值 'L1'，且没有任何报错
            # （2026-09-27 实测踩到：建完节点查库才发现是 L1）。
            'permission_level', 'domain_id',
        ]
    def validate_node_id(self, value):
        from rest_framework import serializers
        if Node.objects.filter(node_id=value).exists():
            raise serializers.ValidationError('该节点ID已注册')
        return value
    def validate(self, attrs):
        from rest_framework import serializers
        ip_address = attrs.get('ip_address')
        port = attrs.get('port')
        if Node.objects.filter(ip_address=ip_address, port=port).exists():
            existing_node = Node.objects.filter(ip_address=ip_address, port=port).first()
            raise serializers.ValidationError({
                'ip_address': f'IP地址和端口组合已被节点 "{existing_node.name}" 使用'
            })
        return attrs
class NodeDetailSerializer(CustomModelSerializer):
    class Meta:
        model = Node
        fields = [
            'id', 'node_id', 'name', 'ip_address', 'port',
            'phone', 'email', 'contact_person',
            'organization', 'department', 'location',
            'node_type', 'hardware_spec', 'description', 'tags',
            'status', 'partial_key_received', 'last_active', 'create_datetime',
            'kyber_public_key', 'falcon_public_key',
            # 国密（SM2 / SSCL）与安全级别 —— 2026-09-26 补。
            #
            # 为什么必须补：节点管理页的「国密密钥」列与「密钥」弹窗都靠这些字段
            # 判断"已就绪"，而这里原先**没有它们**，于是那一列永远显示"未生成"，
            # 连带按钮文案不会变成"重新生成"、覆盖告警也不会弹。
            'gm_public_key', 'sscl_public_key',
            'kyber_security_level', 'falcon_security_level',
        ]


class NodeListSerializer(CustomModelSerializer):
    """**列表专用**序列化器 —— 不带两个公钥大字段。

    为什么需要单独一个：`NodeDetailSerializer` 会把 `falcon_public_key` 一起返回，
    而它实测 **7.8MB/节点**（`falcon_public_key` 约 7.8MB、`kyber_public_key` 约 1KB）。
    节点管理页只为判断"是否已生成"，却因此拉走全部公钥：

        实测（3 个节点）：/nodes/?limit=500 → 23.4MB、0.74s

    节点数一多就会顶到 gunicorn 的 `timeout=120`，页面直接超时。

    改法：列表只回**就绪布尔值**（`*_key_ready`），公钥本身仍由
    `/nodes/{id}/keys/` 在打开「密钥」弹窗时按需取 —— 那时才真的要看内容。

    前端 `views/nodes/index.vue` 只对这些字段做布尔判断，因此改回布尔值无需改前端逻辑。
    """

    kyber_key_ready = serializers.SerializerMethodField()
    falcon_key_ready = serializers.SerializerMethodField()
    gm_key_ready = serializers.SerializerMethodField()
    sscl_key_ready = serializers.SerializerMethodField()

    class Meta:
        model = Node
        fields = [
            'id', 'node_id', 'name', 'ip_address', 'port',
            'phone', 'email', 'contact_person',
            'organization', 'department', 'location',
            'node_type', 'hardware_spec', 'description', 'tags',
            'status', 'partial_key_received', 'last_active', 'create_datetime',
            'kyber_security_level', 'falcon_security_level',
            # 阶段 2：管理页要能显示"这个节点属于哪个账号、授权等级多少、
            # 在哪个域、有没有完成首次初始化"。这几项都不含大字段，可以安全进列表。
            'permission_level', 'domain_id', 'sys_user_id', 'initialized_at',
            'kyber_key_ready', 'falcon_key_ready', 'gm_key_ready', 'sscl_key_ready',
        ]

    def get_kyber_key_ready(self, obj):
        return bool(obj.kyber_public_key)

    def get_falcon_key_ready(self, obj):
        return bool(obj.falcon_public_key)

    def get_gm_key_ready(self, obj):
        return bool(obj.gm_public_key)

    def get_sscl_key_ready(self, obj):
        return bool(obj.sscl_public_key)


class NodeUpdateSerializer(CustomModelSerializer):
    class Meta:
        model = Node
        fields = [
            'phone', 'email', 'contact_person',
            'organization', 'department', 'location',
            'node_type', 'hardware_spec', 'description', 'tags',
            'kyber_security_level', 'falcon_security_level',
            # 阶段 2：管理员可改节点的授权等级与所属域（文档 §8.4/§8.5）。
            # `sys_user_id` 刻意**不在**这里 —— 账号映射由建节点流程建立，
            # 手工改它会让 Node 与 sys_user 的一一映射被任意破坏。
            'permission_level', 'domain_id',
        ]
        read_only_fields = [
            'id', 'node_id', 'name', 'ip_address', 'port',
            'status', 'partial_key_received', 'last_active',
            'create_datetime', 'update_datetime',
            'kyber_public_key', 'kyber_private_key',
            'falcon_public_key', 'falcon_private_key',
            'partial_key_data', 'blockchain_config'
        ]
class BlockSerializer(CustomModelSerializer):
    class Meta:
        model = Block
        fields = '__all__'
class TransactionSerializer(CustomModelSerializer):
    from_node_name = serializers.CharField(source='from_node.name', read_only=True)
    to_node_name = serializers.CharField(source='to_node.name', read_only=True)
    class Meta:
        model = Transaction
        fields = '__all__'
class SessionKeySerializer(CustomModelSerializer):
    node1_name = serializers.CharField(source='node1.node_id', read_only=True)
    node2_name = serializers.CharField(source='node2.node_id', read_only=True)
    class Meta:
        model = SessionKey
        fields = '__all__'
        extra_kwargs = {
            'encrypted_session_key': {'write_only': True}
        }
class SessionKeyCreateSerializer(CustomModelSerializer):
    class Meta:
        model = SessionKey
        fields = ['node1', 'node2']
class MessageSerializer(CustomModelSerializer):
    sender_name = serializers.CharField(source='sender.name', read_only=True)
    receiver_name = serializers.CharField(source='receiver.name', read_only=True)
    class Meta:
        model = Message
        fields = '__all__'
        extra_kwargs = {
            'encrypted_content': {'write_only': True}
        }
class MessageCreateSerializer(CustomModelSerializer):
    class Meta:
        model = Message
        fields = ['session', 'sender', 'receiver', 'message_type', 'encrypted_content']
class BlockchainConfigSerializer(CustomModelSerializer):
    class Meta:
        model = BlockchainConfig
        fields = '__all__'
        extra_kwargs = {
            'private_key': {'write_only': True}
        }
class BlockchainConfigCreateSerializer(CustomModelSerializer):
    class Meta:
        model = BlockchainConfig
        fields = ['name', 'provider_url', 'contract_address', 'private_key', 'account_address', 'network_id']
class FalconKeyPairSerializer(CustomModelSerializer):
    node_name = serializers.CharField(source='node.name', read_only=True)
    class Meta:
        model = FalconKeyPair
        fields = '__all__'
        extra_kwargs = {
            'secret_key': {'write_only': True},
            'secret_value': {'write_only': True},
            'partial_key': {'write_only': True}
        }
class FalconKeyPairDetailSerializer(CustomModelSerializer):
    node_name = serializers.CharField(source='node.name', read_only=True)
    class Meta:
        model = FalconKeyPair
        fields = [
            'id', 'user_id', 'node', 'node_name', 'public_key',
            'status', 'blockchain_stored', 'blockchain_tx_hash',
            'create_datetime', 'update_datetime'
        ]
class KeyDistributionLogSerializer(CustomModelSerializer):
    node_name = serializers.CharField(source='node.name', read_only=True)
    class Meta:
        model = KeyDistributionLog
        fields = '__all__'
class SystemStatsSerializer(serializers.Serializer):
    total_nodes = serializers.IntegerField()
    active_nodes = serializers.IntegerField()
    total_transactions = serializers.IntegerField()
    total_sessions = serializers.IntegerField()
    total_messages = serializers.IntegerField()
    latest_block = serializers.IntegerField()
class NodeStatsSerializer(serializers.Serializer):
    node_id = serializers.CharField()
    name = serializers.CharField()
    status = serializers.CharField()
    kyber_key_generated = serializers.BooleanField()
    falcon_key_generated = serializers.BooleanField()
    partial_key_received = serializers.BooleanField()
    sessions_count = serializers.IntegerField()
    messages_sent = serializers.IntegerField()
    messages_received = serializers.IntegerField()
class BlockchainStatsSerializer(serializers.Serializer):
    total_blocks = serializers.IntegerField()
    total_transactions = serializers.IntegerField()
    kyber_uploads = serializers.IntegerField()
    falcon_uploads = serializers.IntegerField()
    session_exchanges = serializers.IntegerField()
    latest_block_hash = serializers.CharField()
    latest_block_time = serializers.DateTimeField()
class APIResponseSerializer(serializers.Serializer):
    success = serializers.BooleanField()
    message = serializers.CharField()
    data = serializers.JSONField(required=False)
class NodeRegistrationResponseSerializer(serializers.Serializer):
    success = serializers.BooleanField()
    message = serializers.CharField()
    node_info = NodeDetailSerializer(required=False)
    kyber_public_key = serializers.CharField(required=False)
class KeyGenerationResponseSerializer(serializers.Serializer):
    success = serializers.BooleanField()
    message = serializers.CharField()
    falcon_public_key = serializers.CharField(required=False)
    blockchain_tx_hash = serializers.CharField(required=False)
class SessionKeyExchangeResponseSerializer(serializers.Serializer):
    success = serializers.BooleanField()
    message = serializers.CharField()
    session_id = serializers.CharField(required=False)
    key_package = serializers.JSONField(required=False)


class PreDistributedKeySerializer(CustomModelSerializer):
    node1_id = serializers.CharField(source='node1.node_id', read_only=True)
    node1_name = serializers.CharField(source='node1.name', read_only=True)
    node2_id = serializers.CharField(source='node2.node_id', read_only=True)
    node2_name = serializers.CharField(source='node2.name', read_only=True)
    algorithm_display = serializers.CharField(source='get_algorithm_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    # KMS-013：状态**回退** —— 行还是 READY 但已过期的，页面必须显示"已过期"
    # 而不是"可被会话取用"。列表页的自动清理只删其中一部分（见 `get_queryset`），
    # 而消费判据（`consume_key` 的 `expires_at__gt=now`）**不认**过期行 ——
    # 不回退的话页面说"可用"、消费说"没有"，两个数字都出自服务端却互相矛盾。
    effective_status = serializers.SerializerMethodField()

    def get_effective_status(self, obj):
        from .api_contract import (
            POOL_EXPIRED,
            POOL_STATUS_USABLE_FOR_NEW_WORK,
            POOL_TERMINAL_STATUSES,
            normalize_pool_status,
        )
        status = normalize_pool_status(obj.status)
        if status in POOL_STATUS_USABLE_FOR_NEW_WORK and obj.expires_at:
            from django.utils import timezone
            if obj.expires_at <= timezone.now():
                return POOL_EXPIRED
        return status

    # KMS-013：这一项是**用哪把长期密钥**封的（计划 §8.4「接收密钥版本」）。
    # 消费前的可用性复核（`consume_key`）就按这两列查登记表，页面把它显示
    # 出来，用户看到"已回收"与池项"仍可用"时才知道该核对什么。
    #
    # ⚠️ `used_by_session_id` 必须**显式声明**：它是 FK 的 `attname`，
    #    不在 DRF 的模型字段名集合里（那里是 `used_by_session`）——
    #    只写进 Meta.fields 会在加载时抛 ImproperlyConfigured。
    used_by_session_id = serializers.IntegerField(read_only=True)

    class Meta:
        model = PreDistributedKey
        fields = [
            'id', 'pool_id', 'key_index',
            'node1_id', 'node1_name', 'node2_id', 'node2_name',
            'algorithm', 'algorithm_display',
            'status', 'status_display', 'effective_status',
            'long_term_key_id', 'long_term_key_version',
            'used_by_session_id', 'used_at',
            'key_hash', 'generation_time_ms',
            'expires_at',
            'create_datetime',
        ]
        read_only_fields = fields