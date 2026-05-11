from django.contrib import admin
from .models import (
    SystemParameters, Node, Block, Transaction, 
    SessionKey, Message, BlockchainConfig, 
    FalconKeyPair, KeyDistributionLog
)
@admin.register(SystemParameters)
class SystemParametersAdmin(admin.ModelAdmin):
    list_display = ['name', 'n', 'm', 'q', 'sigma', 'is_active', 'create_datetime']
    list_filter = ['is_active', 'create_datetime']
    search_fields = ['name']
    readonly_fields = ['matrix_a', 'kgc_public_key']
@admin.register(Node)
class NodeAdmin(admin.ModelAdmin):
    list_display = ['node_id', 'name', 'ip_address', 'port', 'status', 'partial_key_received', 'last_active']
    list_filter = ['status', 'partial_key_received']
    search_fields = ['node_id', 'name', 'ip_address']
    readonly_fields = ['kyber_private_key', 'falcon_private_key', 'partial_key_data']
@admin.register(Block)
class BlockAdmin(admin.ModelAdmin):
    list_display = ['block_number', 'block_hash', 'timestamp', 'nonce']
    list_filter = ['timestamp']
    search_fields = ['block_hash', 'previous_hash']
    ordering = ['-block_number']
@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ['tx_hash', 'tx_type', 'from_node', 'to_node', 'confirmed', 'timestamp']
    list_filter = ['tx_type', 'confirmed', 'timestamp']
    search_fields = ['tx_hash', 'from_node__name', 'to_node__name']
@admin.register(SessionKey)
class SessionKeyAdmin(admin.ModelAdmin):
    list_display = ['session_id', 'node1', 'node2', 'status', 'expires_at']
    list_filter = ['status']
    search_fields = ['session_id', 'node1__name', 'node2__name']
@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ['message_id', 'sender', 'receiver', 'message_type', 'delivered', 'read', 'timestamp']
    list_filter = ['message_type', 'delivered', 'read', 'timestamp']
    search_fields = ['message_id', 'sender__name', 'receiver__name']
@admin.register(BlockchainConfig)
class BlockchainConfigAdmin(admin.ModelAdmin):
    list_display = ['name', 'provider_url', 'account_address', 'network_id', 'is_active']
    list_filter = ['is_active', 'network_id']
    search_fields = ['name', 'account_address']
    readonly_fields = ['private_key']
@admin.register(FalconKeyPair)
class FalconKeyPairAdmin(admin.ModelAdmin):
    list_display = ['user_id', 'node', 'status', 'blockchain_stored']
    list_filter = ['status', 'blockchain_stored']
    search_fields = ['user_id', 'node__name']
    readonly_fields = ['secret_key', 'secret_value', 'partial_key']
@admin.register(KeyDistributionLog)
class KeyDistributionLogAdmin(admin.ModelAdmin):
    list_display = ['action', 'node', 'success', 'timestamp', 'ip_address']
    list_filter = ['action', 'success', 'timestamp']
    search_fields = ['node__name', 'details', 'blockchain_tx_hash']
    readonly_fields = ['timestamp']