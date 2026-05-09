from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    SystemParametersViewSet, NodeViewSet, BlockViewSet, TransactionViewSet,
    SessionKeyViewSet, MessageViewSet, BlockchainConfigViewSet,
    FalconKeyPairViewSet, KeyDistributionLogViewSet, SystemStatsViewSet,
    KeyPoolViewSet,
    generate_falcon_keypair_with_scheme, save_falcon_keys,
    get_and_verify_falcon_public_key, verify_falcon_public_key_integrity,
    batch_verify_falcon_public_keys
)
from . import chat_urls
app_name = 'pqkds'
router = DefaultRouter()
router.register(r'system-parameters', SystemParametersViewSet, basename='systemparameters')
router.register(r'nodes', NodeViewSet, basename='nodes')
router.register(r'blocks', BlockViewSet, basename='blocks')
router.register(r'transactions', TransactionViewSet, basename='transactions')
router.register(r'session-keys', SessionKeyViewSet, basename='sessionkeys')
router.register(r'messages', MessageViewSet, basename='messages')
router.register(r'blockchain-config', BlockchainConfigViewSet, basename='blockchainconfig')
router.register(r'falcon-keypairs', FalconKeyPairViewSet, basename='falconkeypairs')
router.register(r'logs', KeyDistributionLogViewSet, basename='logs')
router.register(r'stats', SystemStatsViewSet, basename='stats')
router.register(r'key-pool', KeyPoolViewSet, basename='keypool')
urlpatterns = [
    path('', include(router.urls)),
    path('node/generate-falcon-keypair/', generate_falcon_keypair_with_scheme, name='generate-falcon-keypair-with-scheme'),
    path('node/save-falcon-keys/', save_falcon_keys, name='save-falcon-keys'),
    path('falcon/verify/<str:node_id>/', get_and_verify_falcon_public_key, name='get-and-verify-falcon-public-key'),
    path('falcon/verify-integrity/', verify_falcon_public_key_integrity, name='verify-falcon-public-key-integrity'),
    path('falcon/batch-verify/', batch_verify_falcon_public_keys, name='batch-verify-falcon-public-keys'),
    path('chat/', include(chat_urls)),
]