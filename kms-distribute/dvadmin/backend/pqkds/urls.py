from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    SystemParametersViewSet, NodeViewSet, BlockViewSet, TransactionViewSet,
    SessionKeyViewSet, MessageViewSet, BlockchainConfigViewSet,
    FalconKeyPairViewSet, KeyDistributionLogViewSet, SystemStatsViewSet,
    KeyPoolViewSet,
    generate_falcon_keypair_with_scheme, save_falcon_keys,
    generate_gm_keypair,
    get_and_verify_falcon_public_key, verify_falcon_public_key_integrity,
    batch_verify_falcon_public_keys, kms_generate_key, kms_generate_record, kms_lifecycle_record
)
from . import chat_urls
from .admin_node_authorization_views import admin_users, node_authorizations, revoke_node_authorization
from .user_distribution_views import (
    distribute_to_user,
    distribution_batches,
    user_nodes,
    user_symmetric_key_detail,
    user_symmetric_keys,
)
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
    # ⚠️ 用户侧分发（P3 / §5.1）必须排在 router **之前**。
    # DRF 的 router 会为 `key-pool` 生成详情路由 `key-pool/<pk>/`，
    # 它能把 `key-pool/distribute-to-user/` 一并吃掉（把 pk 当成 "distribute-to-user"），
    # 结果是请求落到 KeyPoolViewSet、返回 200 但没有任何 data ——
    # 现象是"接口通了但字段全 undefined"，很难反查到是路由顺序问题。
    # Django 按顺序取第一个匹配，所以这里必须在前。
    path('user-nodes/', user_nodes, name='user-nodes'),
    path('user-symmetric-keys/', user_symmetric_keys, name='user-symmetric-keys'),
    path('user-symmetric-keys/<int:pk>/', user_symmetric_key_detail, name='user-symmetric-key-detail'),
    path('distribution-batches/', distribution_batches, name='distribution-batches'),
    path('key-pool/distribute-to-user/', distribute_to_user, name='distribute-to-user'),

    # --- 管理端「节点鉴权」（P3 步骤 10）---
    # 同样必须排在 router 之前（理由同上：router 的通配段会吃掉这些路径）。
    path('admin/users/', admin_users, name='admin-users'),
    path('admin/node-authorizations/', node_authorizations, name='admin-node-authorizations'),
    path('admin/node-authorizations/<int:pk>/revoke/', revoke_node_authorization,
         name='admin-node-authorization-revoke'),

    path('', include(router.urls)),
    path('kms/generate-record/', kms_generate_record, name='kms-generate-record'),
    path('kms/lifecycle-record/', kms_lifecycle_record, name='kms-lifecycle-record'),
    path('kms/generate-key/', kms_generate_key, name='kms-generate-key'),
    path('node/generate-falcon-keypair/', generate_falcon_keypair_with_scheme, name='generate-falcon-keypair-with-scheme'),
    path('node/save-falcon-keys/', save_falcon_keys, name='save-falcon-keys'),
    # 国密节点密钥（SM2 + SSCL 各一对）：节点腿算法可选 kyber_kem / falcon_lattice /
    # gm_sm2 / gm_sscl，后两者要求节点已有对应国密公钥，这个接口就是补这一步的入口。
    path('node/generate-gm-keypair/', generate_gm_keypair, name='generate-gm-keypair'),
    path('falcon/verify/<str:node_id>/', get_and_verify_falcon_public_key, name='get-and-verify-falcon-public-key'),
    path('falcon/verify-integrity/', verify_falcon_public_key_integrity, name='verify-falcon-public-key-integrity'),
    path('falcon/batch-verify/', batch_verify_falcon_public_keys, name='batch-verify-falcon-public-keys'),
    path('chat/', include(chat_urls)),
]