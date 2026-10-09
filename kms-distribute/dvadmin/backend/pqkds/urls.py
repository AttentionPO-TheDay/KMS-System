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
from .demo_context import demo_init_lease, demo_init_release
# ⚠️ 别名不是洁癖，是**必须的**：节点侧 `node_self_views` 里也有一个
#    `node_authorization_requests`（节点看自己的申请），而本文件后面又 import 了它 ——
#    两个同名名字被先后导入，**后者静默覆盖前者**，于是管理端那条路由指向了
#    节点侧视图（现象：管理员调审批列表被告知"当前账号未关联任何节点"，
#    而路由看起来完全正确）。下面两处都用带命名空间的前缀，杜绝这类覆盖。
from .admin_node_authorization_views import (
    admin_users,
    decide_node_authorization_request as admin_decide_authorization_request,
    decide_node_authorization_requests_batch as admin_decide_authorization_requests_batch,
    node_authorization_requests as admin_authorization_requests,
    node_authorizations,
    revoke_node_authorization,
)
from .user_distribution_views import (
    distribute_to_user,
    distribution_batches,
    user_nodes,
    user_symmetric_key_detail,
    user_symmetric_keys,
)
# 阶段 2：节点自助（首次登录后的密钥初始化）。身份取自令牌自省，见该模块 docstring。
from .node_self_views import (
    node_authorization_request_cancel,
    node_authorization_requests,
    node_directory,
    node_peer_keys,
    node_pool_consume,
    node_pool_preallocate,
    node_pool_summary,
    node_self,
    node_self_distributions,
    node_self_init,
    node_self_keys,
    node_self_keygen_issuances,
    node_self_keygen_authorizations,
    node_self_revoke_key,
)
# §6.5：节点取自己的信封 + 提交「我已恢复 K」的证明
# §10.10：节点自己的会话列表（服务端按外键隔离，见该函数的 docstring）
from .node_session_views import (
    node_envelope_recover,
    node_envelope_sign,
    node_envelope_verify,
    node_envelopes,
    node_session_close,
    node_session_confirm,
    node_session_versions,
    node_sessions,
)
# §3 激活 / §5 登录：设备凭据认证（节点**唯一的**登录方式，节点没有口令）。
# ⚠️ 这两个端点刻意**不要求登录态** —— 它们就是用来产生令牌的。
from .node_auth_views import node_activate, node_challenge, node_login, node_still_exists
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
    path('node-self/keygen/issuances/', node_self_keygen_issuances, name='node-self-keygen-issuances'),
    path('node-self/keygen/authorizations/', node_self_keygen_authorizations, name='node-self-keygen-authorizations'),
    # KMS-007：节点侧「密钥回收」菜单的落点。改的是 `NodeLongTermKey` 那一行，
    # 并连带失效依赖它的池项与会话；在此之前那个菜单删的是另一个服务的
    # `keymanage` 旧行，长期密钥原样不动（见该 view 的 docstring）。
    # ⚠️ 路径与 `node-self/keys/` 不同（后者无通配段，不会吃掉这条），
    #    但同样必须排在 router 之前。
    path('node-self/keys/revoke/', node_self_revoke_key, name='node-self-key-revoke'),
    path('node-self/init/', node_self_init, name='node-self-init'),
    path('node-self/demo-init/lease/', demo_init_lease, name='demo-init-lease'),
    path('node-self/demo-init/release/', demo_init_release, name='demo-init-release'),
    # §6.5：节点取**自己那腿**信封并在本地解封（服务端不代解、也没有私钥），
    # 再提交「我已恢复 K」的证明；双方证明一致即提升为 established。
    path('node-self/envelopes/', node_envelopes, name='node-self-envelopes'),
    # §10.10：本节点参与的会话。同样必须排在 router 之前，
    # 否则 `session-keys/<pk>/` 的通配段会把它吃掉。
    path('node-self/sessions/', node_sessions, name='node-self-sessions'),
    path('node-self/sessions/<str:session_id>/confirm/', node_session_confirm,
         name='node-self-session-confirm'),
    # KMS-012：关闭（终态）。双方可关；关闭后不再接受确认或状态变更。
    path('node-self/sessions/<str:session_id>/close/', node_session_close,
         name='node-self-session-close'),
    # KMS-011：接收方取信封的两条操作（§6.5 的第 ①② 条）。
    # `versions/` 只回"这条会话该用哪两版密钥"（发送方 Falcon 公钥 + 接收方
    # 那一版），是接收方本机验签/解封的入参；`verify` / `recover` 是它做完
    # 之后**如实回报**——服务端据此按状态机推进会话，并在 verify 里独立复核。
    path('node-self/sessions/<str:session_id>/versions/', node_session_versions,
         name='node-self-session-versions'),
    # ⚠️ `<int:envelope_pk>` 是 `PreDistributedKey` 的**整数主键**，不是批次号；
    #    约束成 int 让 `/envelopes/`（无通配段）与它互不吃掉。
    path('node-self/envelopes/<int:envelope_pk>/verify/', node_envelope_verify,
         name='node-self-envelope-verify'),
    path('node-self/envelopes/<int:envelope_pk>/recover/', node_envelope_recover,
         name='node-self-envelope-recover'),
    # ⚠️ **必须**与上面两条 `envelopes/<int:...>/` 紧挨着写，不能挪到文件的
    #    别处去：本路由表里有一条 `node-self/<something>/` 的通配（`node_self`、
    #    `node_self_keys` 那一族之前的写法），把这条放到它们后面会被整段吃掉
    #    —— 现象是 Django 直接 404，而日志只说 "Not Found: /api/pqkds/node-self/<...>/"，
    #    看不出是被哪一条匹配走的（实测过一次）。
    path('node-self/envelopes/<int:envelope_pk>/sign/', node_envelope_sign,
         name='node-self-envelope-sign'),

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

    # --- 任务书「节点多级授权」：名录 + 授权申请 ---
    # 节点看到全网名录 → 申请与某节点建立会话 → 管理员审批 → 双向放行。
    # 三条同样必须排在 router 之前（理由见本文件顶部说明）。
    # ⚠️ `<int:request_id>` 约束成 int：`authorization-requests/` 本身无通配段，
    #    两者不会互吃（与 envelopes 那对同一写法）。
    path('node-self/directory/', node_directory, name='node-self-directory'),
    path('node-self/authorization-requests/', node_authorization_requests,
         name='node-self-authorization-requests'),
    path('node-self/authorization-requests/<int:request_id>/cancel/',
         node_authorization_request_cancel, name='node-self-authorization-request-cancel'),

    # --- 任务书「预分配」：上传保护包 / 看余量 / 取用 / 补签名 ---
    # 生成与封装在**节点侧**（计划 §2.1：服务端不接触 SM4 明文），服务端只
    # 保存、调度、管理保护包。四条同样必须排在 router 之前。
    # ⚠️ `envelopes/<int:pk>/sign/` 与既有的 `envelopes/<int:envelope_pk>/verify/`、
    #    `.../recover/` 是**同一段通配路径上的兄弟**：三个转换器都约束成 int，
    #    末段不同，互不吃掉。
    path('node-self/pool/preallocate/', node_pool_preallocate,
         name='node-self-pool-preallocate'),
    path('node-self/pool/summary/', node_pool_summary, name='node-self-pool-summary'),
    path('node-self/pool/consume/', node_pool_consume, name='node-self-pool-consume'),
    # --- §3 激活 / §5 登录（设备凭据）---
    # ⚠️ 这三条**必须**排在 router 之前，且必须排在上面那些
    #    `node-self/` 路由**之前或之列**都可以 —— 它们路径不同，互不吃掉。
    #    （真正会吃掉它们的是 router 的 `nodes/<pk>/`，见本文件顶部说明。）
    # ⚠️ 注意它们与上面三条的区别：上面三条要求**已登录**（require_kms_user），
    #    下面三条恰恰是用来产生登录态的，不能要求登录态。
    path('node-self/activate/', node_activate, name='node-self-activate'),
    path('node-self/challenge/', node_challenge, name='node-self-challenge'),
    # 登录页校对**本机缓存**用：一台设备只保留一个节点的登录信息，而库里
    # 那个节点可能已经被删/被重置 —— 这条免鉴权，只回答"还在不在"（见其 docstring）。
    path('node-self/still-exists/', node_still_exists, name='node-self-still-exists'),
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
    # 任务书「节点多级授权」：审批节点发起的授权申请。
    # ⚠️ `node-authorization-requests/` 与上面的 `node-authorizations/` **不是同一条**，
    #    名字只差一个词，改路由时别串了（串了的现象是"申请列表"返回授权列表）。
    path('admin/node-authorization-requests/', admin_authorization_requests,
         name='admin-node-authorization-requests'),
    path('admin/node-authorization-requests/<int:pk>/decide/',
         admin_decide_authorization_request, name='admin-node-authorization-request-decide'),
    # 勾选多条、一次处置（任务书「多选提交权限确认请求」的批量侧）。
    # ⚠️ 必须排在 `<int:pk>/decide/` 之后**但仍在 router 之前**；路径里没有 pk，
    #    与上面那条不冲突（`decide-batch` 不会被 `<int:pk>` 吃掉 —— 那个转换器只认数字）。
    path('admin/node-authorization-requests/decide-batch/',
         admin_decide_authorization_requests_batch,
         name='admin-node-authorization-requests-decide-batch'),

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