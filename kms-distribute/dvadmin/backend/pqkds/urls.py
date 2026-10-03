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
# 阶段 2：节点自助（首次登录后的密钥初始化）。身份取自令牌自省，见该模块 docstring。
from .node_self_views import (
    node_peer_keys,
    node_self,
    node_self_distributions,
    node_self_init,
    node_self_keys,
    node_self_revoke_key,
)
# §6.5：节点取自己的信封 + 提交「我已恢复 K」的证明
# §10.10：节点自己的会话列表（服务端按外键隔离，见该函数的 docstring）
from .node_session_views import node_envelopes, node_session_confirm, node_sessions
# §3 激活 / §5 登录：设备凭据认证（节点**唯一的**登录方式，节点没有口令）。
# ⚠️ 这两个端点刻意**不要求登录态** —— 它们就是用来产生令牌的。
from .node_auth_views import node_activate, node_challenge, node_login
# 阶段 6：长期密钥回收后连带失效预分配池项（内部通道，X-Internal-Token 鉴权）
from .internal_pool_views import revoke_pool_by_key
# 阶段 7 §8.7：安全监控总览
from .security_monitor_views import security_summary
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

    # --- 阶段 2：节点自助 ---
    # 必须排在 router 之前，理由同下：router 的 `nodes/<pk>/` 通配段会把
    # `node-self/` 吃成 pk='node-self'，请求落到 NodeViewSet 返回 200 但没有 data，
    # 现象是"接口通了但字段全 undefined"。
    path('node-self/', node_self, name='node-self'),
    # §4.4：节点侧生成密钥后**只上传公钥**。必须与 init 分开 ——
    # 先逐个登记四套公钥，再由 init 收尾置 ACTIVE（见 node_service 的说明）。
    path('node-self/keys/', node_self_keys, name='node-self-keys'),
    # KMS-007：节点侧「密钥回收」菜单的落点。改的是 `NodeLongTermKey` 那一行，
    # 并连带失效依赖它的池项与会话；在此之前那个菜单删的是另一个服务的
    # `keymanage` 旧行，长期密钥原样不动（见该 view 的 docstring）。
    # ⚠️ 路径与 `node-self/keys/` 不同（后者无通配段，不会吃掉这条），
    #    但同样必须排在 router 之前。
    path('node-self/keys/revoke/', node_self_revoke_key, name='node-self-key-revoke'),
    path('node-self/init/', node_self_init, name='node-self-init'),
    # §6.5：节点取**自己那腿**信封并在本地解封（服务端不代解、也没有私钥），
    # 再提交「我已恢复 K」的证明；双方证明一致即提升为 established。
    path('node-self/envelopes/', node_envelopes, name='node-self-envelopes'),
    # §10.10：本节点参与的会话。同样必须排在 router 之前，
    # 否则 `session-keys/<pk>/` 的通配段会把它吃掉。
    path('node-self/sessions/', node_sessions, name='node-self-sessions'),
    path('node-self/sessions/<str:session_id>/confirm/', node_session_confirm,
         name='node-self-session-confirm'),

    # --- KMS-008：节点间分发的新请求契约（§16）---
    # `peers/<...>/keys/` 与 `distributions/` 都是**无通配段的固定前缀 +
    # 一个受约束的段**，不会被 router 的 `nodes/<pk>/` 吃掉；但同样必须排在
    # router 之前 —— 与上面几条同一理由，见本文件顶部说明。
    # ⚠️ `peers/<str:peer_node_id>/keys/` 里的 id 是**业务编号**（`Node.node_id`），
    #    不是主键；`<str:...>` 不匹配斜杠，所以不会把后面的 /keys/ 一起吃掉。
    path('node-self/peers/<str:peer_node_id>/keys/', node_peer_keys,
         name='node-self-peer-keys'),
    path('node-self/distributions/', node_self_distributions,
         name='node-self-distributions'),

    # --- §3 激活 / §5 登录（设备凭据）---
    # ⚠️ 这三条**必须**排在 router 之前，且必须排在上面那些
    #    `node-self/` 路由**之前或之列**都可以 —— 它们路径不同，互不吃掉。
    #    （真正会吃掉它们的是 router 的 `nodes/<pk>/`，见本文件顶部说明。）
    # ⚠️ 注意它们与上面三条的区别：上面三条要求**已登录**（require_kms_user），
    #    下面三条恰恰是用来产生登录态的，不能要求登录态。
    path('node-self/activate/', node_activate, name='node-self-activate'),
    path('node-self/challenge/', node_challenge, name='node-self-challenge'),
    path('node-self/login/', node_login, name='node-self-login'),

    # 阶段 6：内部通道（X-Internal-Token 鉴权，不对外暴露）。
    # 同样排在 router 之前，理由同上。
    path('internal/pool/revoke-by-key/', revoke_pool_by_key, name='revoke-pool-by-key'),

    # 阶段 7 §8.7：安全监控总览（管理员视角聚合统计，需登录态）
    path('security-monitor/summary/', security_summary, name='security-summary'),
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