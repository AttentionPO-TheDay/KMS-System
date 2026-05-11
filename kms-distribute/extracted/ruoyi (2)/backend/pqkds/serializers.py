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
            'kyber_security_level', 'falcon_security_level'
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
            'kyber_public_key', 'falcon_public_key'
        ]
class NodeUpdateSerializer(CustomModelSerializer):
    class Meta:
        model = Node
        fields = [
            'phone', 'email', 'contact_person',
            'organization', 'department', 'location',
            'node_type', 'hardware_spec', 'description', 'tags',
            'kyber_security_level', 'falcon_security_level'
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

    class Meta:
        model = PreDistributedKey
        fields = [
            'id', 'pool_id', 'key_index',
            'node1_id', 'node1_name', 'node2_id', 'node2_name',
            'algorithm', 'algorithm_display',
            'status', 'status_display',
            'key_hash', 'generation_time_ms',
            'used_at', 'expires_at',
            'create_datetime',
        ]
        read_only_fields = fields