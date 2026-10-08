# -*- coding: utf-8 -*-
"""节点到节点分发的**编排层**（KMS-008 / 计划 §7 阶段 3 的请求模型）。

这一层负责什么
--------------
把"发送方节点 → 接收方节点"的一次分发，按**请求里显式指定的那一版接收方公钥**
封装成一份信封，并把由此产生的四样副作用一次做完：

    1. 落一条 `PreDistributedKey`（接收方取信封的入口就是查这张表）；
    2. 建一条 `DistributionBatch`（批次历史 / 链上存证的批次号）；
    3. 建一条 `initiated` 会话（双方据此继续 stage 4 的验签与确认）；
    4. 在事务**提交之后**补一条 `KEY_DISTRIBUTED` 链上存证。

为什么另起一个模块，而不是继续写进视图
--------------------------------------
视图层的 `distribute_to_user` 把编排、用户腿、节点腿、响应组装混在一个
两百行的函数里；KMS-008 需要在**不改变旧流程**的前提下长出第二条路径，
把新逻辑再塞进去会让"哪条路径做了什么"彻底看不出来。

更要紧的是**可测性**：本模块不出 HTTP 就能被 `tests/test_node_key_registry.py`
直接调用（与 KMS-007 的 `key_revocation_service` 同一条路数）。视图层只剩
参数解析与响应组装。

搬进来的三条助手
----------------
`create_initiated_sessions` / `record_distribution_chain_event` /
`classify_distribution` 原本是 `user_distribution_views` 的私有函数，
但它们是**新旧两条路径共用的副作用**。新服务若反过来从视图模块 import 它们，
依赖方向就成了"服务层 → 视图层"，而视图层又要 import 本模块组成响应 ——
那是一个循环的前身。所以移到这里，由视图层 import 本模块。

这次**不做**什么（KMS-009/010 的边界）
-------------------------------------
* 不在**节点侧**生成 SM4：本次仍由服务端生成、服务端封装（过渡实现），
  但**按请求指定的那一版公钥**封 —— 这正是 KMS-009 要接手的那个位置；
* 不做 Falcon 签名（KMS-010 补齐验签后，"没有签名就不能发送"才落得下）；
* 不写用户腿信封：新模型是节点到节点，没有"发起用户自己的那一份"，
  旧用户腿接口保留一段迁移期但已标记 deprecated。

KMS-010（已落地）
-----------------
上面两条"不做"里的签名与验签都已接上：SM4 与封装在 KMS-009 搬进了发送节点
浏览器，KMS-010 把 `verify_node_envelope` 接进 `create_node_distribution` ——
信封必须由**请求里显式指定的那一版**发送方 Falcon 长期密钥验得过才登记
（失败 `SIGNATURE_INVALID`），验过了才回 `signatureVerified`。
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from django.db import IntegrityError, transaction
from django.utils import timezone

from . import api_contract as C
from . import kms_service_client as kms
from .envelope_signature import ciphertext_digest, verify_node_envelope
from .models import DistributionBatch, Node, PreDistributedKey, SessionKey, UserNodeAuthorization
from .node_key_registry import require_key_version
from .sm4_crypto import PAYLOAD_ALGORITHM_SM4
from .wrappers import NODE_WRAPPING_BY_CANONICAL, NODE_WRAPPING_CHOICES

logger = logging.getLogger(__name__)

#: 信封默认有效期（小时）。旧用户腿流程把它**写死**成 24（D8：有效期一旦可调，
#: "对称密钥有时限"这条属性就会随部署漂移，而用户无从知道当前是多少）。
#: 新请求模型允许调用方显式给出 `expiresInHours`（§16.2 把有效期列为契约字段），
#: 但**限幅**——上限见下，理由同样是"不允许无期限的会话密钥"。
DEFAULT_EXPIRES_HOURS = 24

#: 有效期上限（7 天）。超过它直接拒绝而不是截断：
#: 截断会让"用户以为设了 30 天、实际只有 7 天"，而没有任何一处会告诉他。
MAX_EXPIRES_HOURS = 168


def _as_expires_at(raw: Any) -> "timezone.datetime":
    """把调用方给的**绝对有效期**收敛成一个合法的时间点。**认不出就拒绝，不猜。**

    ⚠️ KMS-009 起收的是绝对时间而不是"多少小时"：签名要覆盖 `expires_at`，
       节点就必须在**签名之前**知道它是哪个时刻 —— 服务端事后再算，
       节点签的就是一份"还不知道有效期"的信。

    ⚠️ "客户端给值"不等于"客户端说了算"：**范围与上界仍由服务端强制**。
       允许客户端随便定有效期，等于把"会话密钥有时限"这条安全属性交给调用方。
    """
    if raw is None or raw == '':
        raise C.ContractError(
            '缺少 expiresAt：有效期必须由调用方给出（签名要覆盖它）',
            code=C.ERR_INVALID_PARAMETER,
        )
    if isinstance(raw, datetime):
        moment = raw
    else:
        text = str(raw).strip()
        if not text:
            raise C.ContractError('expiresAt 不能为空', code=C.ERR_INVALID_PARAMETER)
        try:
            moment = datetime.fromisoformat(text.replace('Z', '+00:00'))
        except ValueError as exc:
            raise C.ContractError(
                f'expiresAt 应为 ISO8601 时间串，收到 {raw!r}', code=C.ERR_INVALID_PARAMETER,
            ) from exc
    if timezone.is_aware(moment):
        # ⚠️ 本仓库 `USE_TZ = False`（settings.py），`timezone.now()` 返回**朴素**
        #    时间（与库里所有 datetime 列一致）。带上时区的时间点必须**转换到
        #    本地时区后去掉 tzinfo**，否则一比较就抛
        #    "can't compare offset-naive and offset-aware datetimes" ——
        #    那是 500，不是拒绝，看起来像服务端坏了。
        moment = timezone.make_naive(moment, timezone.get_current_timezone())
    else:
        # 不带时区的时间点按**服务器本地时区**解释（与库里的存量行同一口径）。
        # 这不是"猜"：契约里要求 ISO8601，而调用方（页面）用的是本地时间或 UTC ——
        # 两者都靠"转换到服务器时区"归一到同一把尺子上。
        moment = moment

    now = timezone.now()
    if moment <= now:
        raise C.ContractError('expiresAt 已经过去了', code=C.ERR_INVALID_PARAMETER)
    if moment > now + timedelta(hours=MAX_EXPIRES_HOURS):
        raise C.ContractError(
            f'expiresAt 距现在不能超过 {MAX_EXPIRES_HOURS} 小时'
            f'（{DEFAULT_EXPIRES_HOURS} 是默认值）',
            code=C.ERR_INVALID_PARAMETER,
        )
    return moment


#: 批次号的形状：`dist-<yyyyMMddHHmmss>-<8位十六进制>`。
#: 与 KMS-008 之前服务端自铸的那一串同形 —— 它被写进会话 ID
#: （`{batch_id}-n{pk}`）与链事件的批次字段，形状变了会波及那些读取方。
_BATCH_ID_RE = re.compile(r'^dist-\d{14}-[0-9a-f]{8}$')


def _as_batch_id(raw: Any) -> str:
    """校验调用方给的批次号。**形状与长度都要管**，但不查重。

    ⚠️ 不查重是刻意的：查重会**先查后写**，两次请求之间仍可能撞上（竞态），
       而 `DistributionBatch.batch_id` 上有**唯一约束**——真正的守门人是它。
       这里再查一次只会给人一种"已经防住了"的错觉（并发下并不成立）。
       撞号由数据库拦下，服务端把它转成一句人话（见 `_batch_id_taken`）。

    ⚠️ 长度上限取模型字段的 64：超长会撞 MySQL 的列宽，报出来的是驱动层
       的截断/报错，看起来与本模块无关。
    """
    text = str(raw or '').strip()
    if not text:
        raise C.ContractError(
            '缺少 batchId：批次号必须由调用方给出（签名要覆盖它）',
            code=C.ERR_INVALID_PARAMETER,
        )
    if len(text) > 64 or not _BATCH_ID_RE.match(text):
        raise C.ContractError(
            f'batchId 形状非法：应为 dist-<14位时间>-<8位十六进制>，收到 {text!r}',
            code=C.ERR_INVALID_PARAMETER,
        )
    return text


def _as_envelope(raw: Any) -> Dict[str, Any]:
    """校验节点交上来的信封本体是**这一版契约要求的形状**。

    只做形状与必需字段的检查，不碰密码学（那是 KMS-010 的验签）。形状检查要
    在**加密运算之前**完成，否则畸形信封会一路走到签名校验，
    报出来的是一句"验签失败"——而那看起来像伪造。
    """
    if not isinstance(raw, dict) or not raw:
        raise C.ContractError('缺少 envelope：分发信封必须由发送节点在本地封装', code=C.ERR_INVALID_PARAMETER)

    wrapping = str(raw.get('wrapping_algorithm') or '').strip().lower()
    if wrapping == 'kyber_kem':
        required = ('kem_ciphertext', 'encrypted_key', 'nonce', 'tag')
    elif wrapping in ('gm_sm2', 'gm_sscl'):
        required = ('ciphertext',)
    else:
        raise C.ContractError(
            f"信封的 wrapping_algorithm 非法：{wrapping or '(空)'}"
            f'（可选 {"、".join(NODE_WRAPPING_CHOICES)}）',
            code=C.ERR_ALGORITHM_NOT_ALLOWED,
        )
    missing = [name for name in required if not str(raw.get(name) or '').strip()]
    if missing:
        raise C.ContractError(
            f'{wrapping} 信封缺少必需字段：{", ".join(missing)}',
            code=C.ERR_INVALID_PARAMETER,
        )
    # 承载签名的字段也要在：签名是对"整份信封的规范字段集"算的，
    # 其中 `ciphertext_digest` 由节点算出并写进信封（与服务端重算的比对见调用方）。
    if not str(raw.get('ciphertext_digest') or '').strip():
        raise C.ContractError(
            '信封缺少 ciphertext_digest：签名要覆盖它，不能事后补',
            code=C.ERR_INVALID_PARAMETER,
        )
    return raw


def _canonical_inner_json(envelope: Dict[str, Any], canonical: str) -> str:
    """按**内层密文字段**重建紧凑 JSON —— 与校验摘要时的口径一致。

    这是"摘要算的是什么"的**唯一**一份定义：只有密文那几项，
    **不含** `batch_id` / `expires_at` / 签名等后加字段。
    含进去会让摘要依赖它自己（自指），历史上已经踩过一次
    （见 `envelope_signature.SIGNED_FIELDS` 的注释）。
    """
    if canonical == 'KYBER':
        inner = {
            'kem_ciphertext': envelope.get('kem_ciphertext'),
            'encrypted_key': envelope.get('encrypted_key'),
            'nonce': envelope.get('nonce'),
            'tag': envelope.get('tag'),
            'payload_algorithm': envelope.get('payload_algorithm') or PAYLOAD_ALGORITHM_SM4,
            'wrapping_algorithm': envelope.get('wrapping_algorithm') or 'kyber_kem',
        }
    else:
        inner = {
            'algorithm': envelope.get('algorithm') or 'sm2',
            'ciphertext': envelope.get('ciphertext'),
            'public_key': envelope.get('public_key'),
            'payload_algorithm': envelope.get('payload_algorithm') or PAYLOAD_ALGORITHM_SM4,
            'wrapping_algorithm': envelope.get('wrapping_algorithm'),
            'recipient_public_key': envelope.get('recipient_public_key'),
        }
        if envelope.get('key_system'):
            inner['key_system'] = envelope.get('key_system')
    return json.dumps(inner, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def _as_key_hash(raw: Any) -> str:
    """载荷密钥的 SHA256（hex，64 位）。**形状必须对**，值无法在服务端核对。

    ⚠️ 服务端没有 K，所以它**永远无法验证**这个值 —— 这不是缺口，是设计：
       它是留给接收方解出 K 之后自查的（解出来的那把是不是发送方声称的那把）。
       这里只保证形状，免得一个乱码在接收方那边被当成"密钥不对"。
    """
    text = str(raw or '').strip().lower()
    if len(text) != 64 or not all(ch in '0123456789abcdef' for ch in text):
        raise C.ContractError(
            'keyHash 应为 64 位十六进制（SM4 载荷密钥的 SHA256）',
            code=C.ERR_INVALID_PARAMETER,
        )
    return text


def authorized_node_ids(user_id: int) -> List[int]:
    """该用户当前有效的节点授权 ID 列表（**主键**，不是业务编号）。

    ⚠️ **这是全系统唯一的"能不能与某节点通信"判据。**
       节点授权申请/审批（`node_authorization_service`）只负责往
       `UserNodeAuthorization` 写行，**不得**在这里加任何"是否来自审批"的判断：
       加一个这样的分支，就等于让"申请单的状态"变成第二套权限事实 ——
       而仓库里被下线的 `permission_request` 审批流正是这么坏的
       （见 `kms-ops/mysql/init/35_remove_permission_request_menu.sql`）。
       申请单只记录过程，放行永远问本函数。

    这里返回的是 `UserNodeAuthorization.node_id` 存的东西 —— 那是个外键
    （`ForeignKey(Node)`，无 `to_field`），所以是 `Node.pk`。
    调用方拿它去比 `node.id`；写成业务编号比会**恒不命中却不报错**，
    表现是"明明授权了却说你没权限"。
    """
    return list(
        UserNodeAuthorization.objects.filter(user_id=user_id, status='active')
        .values_list('node_id', flat=True)
    )


def create_initiated_sessions(sender_node, node_map, succeeded_node_ids, batch_id,
                              expires_at, *, dispatch: str = 'user_distribution',
                              session_type: str = 'kyber_kem',
                              recipient_key=None, falcon_key=None,
                              recipient_key_versions=None) -> int:
    """为本次分发成功送达的每个节点登记一条 **initiated** 会话（文档 §6.5）。

    发起方是**发送节点**。取不到发送节点时（管理员发起的旧流程）**不建会话**：
    会话是"两个节点之间"的东西，没有发起节点就不存在这条边。

    只建 initiated，不建 established —— 理由见调用点的说明：
    验签（§6.3/§6.4）尚未实现，建 established 等于宣称一个没验证过的属性。

    幂等：session_id 由 batch_id + 节点后缀构成并带唯一约束，
    重复执行同一批次不会产生重复会话（走 get_or_create）。

    @param dispatch      写进 `key_exchange_data` 的"哪条分发路径建的"（排障入口）
    @param session_type  会话类型。KMS-008 起传**本次实际用的保护算法拼写**
                        （kyber_kem / gm_sm2 / gm_sscl）—— 该字段在
                        `node_session_views` 里就是以 `protectionAlgorithm` 的名义
                        下发的，旧流程一律硬编码 kyber_kem 是既有失真，新路径不再沿用。
    @param recipient_key / falcon_key  KMS-011：把"这条会话关联的具体密钥版本"
                        落进会话行（计划 §7 阶段 4 第 1 条）。新分发路径两条都传
                        （`require_key_version` 查到的那两行）；旧用户腿路径只传
                        `falcon_key`（它没有"接收方指定版本"这个概念，接收密钥
                        版本列留空 —— 与 `PreDistributedKey.long_term_key_id`
                        对历史行留空同一条纪律：**不编**）。
    @param recipient_key_versions  备用形状（批量）—— 目前调用方都按"整批同一版"传
                        `recipient_key`，本参数留给"一批里各节点版本不同"的将来；
                        给了它就**不读** `recipient_key`。
    """
    if sender_node is None:
        logger.info('分发批次 %s：发起方未映射到节点，不建会话', batch_id)
        return 0

    created = 0
    for node_db_id in succeeded_node_ids:
        target = node_map.get(node_db_id)
        if target is None or target.id == sender_node.id:
            # 自己和自己不建会话（节点向自己分发的场景没有意义）
            continue
        session_id = f'{batch_id}-n{target.id}'
        # 每个接收节点取自己那一版（批量形状优先，否则整批同一版）。
        target_recipient_key = recipient_key
        if recipient_key_versions:
            target_recipient_key = recipient_key_versions.get(node_db_id) or recipient_key
        try:
            _, was_created = SessionKey.objects.get_or_create(
                session_id=session_id,
                defaults={
                    'node1': sender_node,
                    'node2': target,
                    'session_type': session_type,
                    # 会话密钥本体不在服务端 —— 服务端只有包给双方的密文，
                    # 所以这两列如实标注"材料在信封里，不在本表"，
                    # 而不是塞一个占位明文进去（那会让"服务端不存明文"这条不变量失真）。
                    'encrypted_session_key': f'see envelopes of batch {batch_id}',
                    'key_exchange_data': json.dumps({
                        'batch_id': batch_id,
                        'dispatch': dispatch,
                        'note': '会话密钥经信封分发，服务端不持有明文',
                    }, ensure_ascii=False),
                    'status': 'initiated',
                    'expires_at': expires_at,
                    # KMS-011：关联的具体密钥版本（取信封/验签/显示都靠它）。
                    # 取不到就留 None —— 见 docstring 的说明。
                    'recipient_key_id': getattr(target_recipient_key, 'key_id', None),
                    'recipient_key_version': getattr(target_recipient_key, 'key_version', None),
                    'falcon_key_id': getattr(falcon_key, 'key_id', None),
                    'falcon_key_version': getattr(falcon_key, 'key_version', None),
                },
            )
            if was_created:
                created += 1
        except Exception as exc:  # noqa: BLE001
            # 单节点建会话失败不该让整次分发回滚 —— 信封已经发给它了，
            # 回滚反而会造成"用户以为没发、节点其实收到了"的更糟状态。
            logger.warning('批次 %s 为节点 %s 建会话失败: %s', batch_id, target.node_id, exc)

    if created:
        logger.info('分发批次 %s：登记 %d 条 initiated 会话（发送方 %s）',
                    batch_id, created, sender_node.node_id)
    return created


def record_distribution_chain_event(event_type: str, key_id: int, key_version: int,
                                    owner_node_code: str, material_digest: str,
                                    batch_id: str) -> Optional[str]:
    """把一次分发记到链上（文档 §8.6 的 KEY_DISTRIBUTED）。

    <h2>为什么失败不影响分发结果</h2>
    <b>因为分发已经成功了</b> —— 信封已经落库、密钥已经在接收方手里。
    存证是**旁路增强**：链上少一条记录不会让已发生的事变成没发生。
    如果这里抛异常并回滚分发，就变成"链写不进去 ⇒ 接收方拿不到密钥"，
    把可用性问题升级成功能问题。

    所以：失败只记日志、**不改分发结论**。但调用方会把结果回显到响应里
    （`chainHash` 字段），让"存证没成功"这件事在界面上看得见 ——
    静默吞掉才是真正危险的：审计缺口会变成不可见。

    <h2>三个字段的口径（KMS-006/007 已确立，新路径沿用）</h2>
    * `key_id` —— **被用于建立会话的那把长期密钥**的整数主键。新流程里
      它就是**接收方**那一行 `NodeLongTermKey`（保护 SM4 的正是它）；
      旧流程传的是用户腿的 `kms.keymanage.key_id`。
    * `node_id` —— **keyId 的归属节点**（新流程 = 接收节点）。这条不变量
      与 KEY_UPDATED / KEY_REVOKED 一致，别在这里改成发送方：链上的
      "哪台机器的哪把钥匙"一旦分叉，回读时就无法回答"谁受影响"。

      ⚠️ Java 侧 `UpdatedelChainConsumer` 目前对 KEY_DISTRIBUTED 只记一条
         info、不做状态变更（那是对的：分发不是状态变迁）。所以这里传
         pqkds 的整数主键不会被拿去查 updatedel 的 `keymanage` 表。
    * `material_digest` —— 信封密文的 SHA256 摘要，不是密文本身，
      更不是任何密钥材料。

    ⚠️ 上链的是**摘要**：链上只需要能核验"是不是同一份东西"。
    """
    if not owner_node_code:
        # 没有归属节点就没有"谁的哪把钥匙"这个事实。宁可不上链，
        # 也不要编一个 owner 出来 —— 链上的记录一旦写错就撤不回来。
        logger.info('批次 %s：缺少密钥归属节点，跳过链上存证', batch_id)
        return None
    try:
        tx_hash = kms.record_chain_event(
            event_type,
            int(key_id),
            int(key_version or 0),
            owner_node_code,
            str(material_digest or ''),
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning('批次 %s 链上存证失败: %s', batch_id, exc)
        return None
    if tx_hash:
        logger.info('批次 %s 已上链存证: %s keyId=%s tx=%s',
                    batch_id, event_type, key_id, tx_hash)
    return tx_hash


def classify_distribution(source_node, target_nodes) -> Tuple[str, List[str], str]:
    """阶段 5（文档 §8.5）：判定本次分发是同域还是跨域。

    返回 `(发起方域, 目标域列表, 'same'|'cross'|'mixed')`。

    发起方域的取法：本系统的分发发起人是 `kms.sys_user`，而"域"是**节点**的属性
    （Node.domain_id，阶段 2 引入）。旧流程按 userId 反查节点，新流程的发起方
    本来就是节点，所以本函数直接收节点 —— 取不到节点时（管理员发起）返回空串。

    取不到时**整体判为 mixed** —— "不知道发起方在哪"时不应擅自断言成"同域"，
    那会把跨域分发粉饰成同域，正好掩盖了这个标记要暴露的东西。
    """
    source_domain = (getattr(source_node, 'domain_id', '') or '').strip()

    target_domains = sorted({
        (getattr(n, 'domain_id', '') or '').strip()
        for n in target_nodes
        if (getattr(n, 'domain_id', '') or '').strip()
    })

    if not source_domain or not target_domains:
        return source_domain, target_domains, 'mixed'

    same = [d for d in target_domains if d == source_domain]
    cross = [d for d in target_domains if d != source_domain]
    if cross and same:
        dist_type = 'mixed'
    elif cross:
        dist_type = 'cross'
    else:
        dist_type = 'same'
    return source_domain, target_domains, dist_type


def create_node_distribution(sender: Node, receiver: Node, *,
                             protection_algorithm: str,
                             recipient_key_id: Any,
                             recipient_key_version: Any,
                             batch_id: Any,
                             expires_at: Any,
                             envelope: Any,
                             signature: Any,
                             falcon_key_id: Any,
                             falcon_key_version: Any,
                             key_hash: Any) -> Dict[str, Any]:
    """发送节点 → 接收节点的一次分发：**登记节点产出的信封**（KMS-009）。

    KMS-008 时这里还在服务端生成 SM4 并封装（过渡实现）。KMS-009 把那份工作
    搬到了发送节点的浏览器里（`provider.wrapForPeer` + `signNodeEnvelope`），
    KMS-010 起本函数再加**一道验签**：只有用请求指定的那一版发送方 Falcon
    公钥验得过的信封才会被登记（表见下）。

    | | 谁做 |
    |---|---|
    | 生成 SM4、用接收方那一版公钥封装 | 发送节点（浏览器） |
    | 用本地 Falcon 私钥签名 | 发送节点（浏览器） |
    | 校验密钥版本可用、批次号/有效期合法、摘要自洽 | 服务端（本函数） |
    | **验签**（用请求指定的那一版发送方 Falcon 公钥） | 服务端（本函数，KMS-010） |

    ⚠️ **服务端从头到尾拿不到 SM4 明文**（计划 §2.1）：节点交上来的是已加密的
       信封与它的哈希，服务端只做搬运、验签与登记。
    ⚠️ `key_hash` 由节点给出，服务端**无法自算**（没有 K）——它不是这里的判据，
       而是留给**接收方**解出 K 之后自查的（KMS-011/012）。

    `batch_id` / `expires_at` 由**调用方给**（KMS-009 起）：签名要覆盖它们，
    服务端就不能在事后赋值。服务端仍负责校验它们的合法性（形状、上界、
    不与既有批次撞号），所以"客户端说了算"只限**值**，不限**约束**。

    <h2>KMS-010：验签为什么用「请求指定的那一版」而不是「发送方当前生产版本」</h2>
    计划 §6.1「所有请求显式携带版本；不允许依赖'当前最新版本'的隐式行为」。
    按物化列/当前生产版本去查的失败方式很安静：发送方在**签名之后、服务端
    验签之前**轮换过 Falcon（更新页随时可能发生），验签就会拿另一把公钥去验
    一份用旧私钥签的信 —— 报出来的是 `SIGNATURE_INVALID`（一个**安全事件**
    的措辞），而实际只是并发轮换。签名者必须与验签者用的是**同一版**的公钥，
    所以版本由请求显式给出，与接收方密钥版本同一口径
    （`require_key_version(sender, 'FALCON', ...)`）。

    抛 `C.ContractError`：
      * 算法不在保护白名单（含 FALCON）→ `ALGORITHM_NOT_ALLOWED`；
      * 缺签名 → `SIGNATURE_REQUIRED`；摘要对不上 → `ENVELOPE_TAMPERED`；
      * **签名验不过 → `SIGNATURE_INVALID`**（KMS-010）；
      * 批次号/有效期/信封形状非法 → `INVALID_PARAMETER`；
      * 接收方或发送方 Falcon 那一版不可用 → `require_key_version` 的四种码，
        原样透出（`KEY_NOT_FOUND` / `KEY_REVOKED` / `KEY_EXPIRED` /
        `KEY_VERSION_MISMATCH`）。

    返回 dict（不是 HTTP 响应）：`{batch, batch_id, key_hash, digest,
    recipient_key, session_count, chain_hash, expires_at, signature_verified}`。
    """
    canonical = C.canonical_algorithm(protection_algorithm)
    if canonical not in C.PROTECTION_ALGORITHMS:
        # Falcon 走到这里也要给**这条**解释：它不是"不认识的算法"，
        # 而是职责不同 —— 它是签名算法，包不了 SM4（计划 §3）。
        raise C.ContractError(
            f'{protection_algorithm or "(空)"} 不能作为保护算法：'
            f'可选 {"/".join(C.PROTECTION_ALGORITHMS)}；Falcon 只用于签名与验签',
            code=C.ERR_ALGORITHM_NOT_ALLOWED,
        )
    wrapping = NODE_WRAPPING_BY_CANONICAL[canonical]

    # 指定哪版就查哪版 —— 查询先于登记发生，这是"版本真进了请求"的判据。
    # 它同时回答"这个节点这个算法有没有可用版本"，是 KMS-008 起就有的判据。
    key = require_key_version(receiver, canonical, recipient_key_id, recipient_key_version)

    # KMS-010：**签名者那一版** Falcon 长期密钥。与接收方那一版同一套校验
    # （KEY_NOT_FOUND / KEY_REVOKED / KEY_EXPIRED / KEY_VERSION_MISMATCH
    # 原样透出）—— 已回收的签名密钥不能继续发新信，这是"回收禁止新签名"
    # 在节点间分发这条路径上的落点。
    #
    # ⚠️ `for_new_work=True`（默认）是刻意的：信封是**新工作**。
    #    解旧信封那条路（准 RETIRED）不属于这里。
    # ⚠️ 这一步**先于**摘要与签名检查：版本不可用时，调用方该做的第一件事是
    #    换一版，而不是去查签名。顺序反过来的话，一把已回收的密钥会先得到
    #    "签名无效"（像伪造），而真正的原因只是它被撤了。
    signing_key = require_key_version(sender, 'FALCON', falcon_key_id, falcon_key_version)

    batch_id = _as_batch_id(batch_id)
    expires_at = _as_expires_at(expires_at)

    # --- 以下三样全部由**发送节点**产出（KMS-009）---
    # 服务端不再生成 SM4、不再封装。它在这里做的事只有"收下、核形状、验签、落库"：
    #   * `envelope` 是节点用接收方**那一版公钥**封好的密文（含待签字段）；
    #   * `signature` 是节点用本地 Falcon 私钥对规范字节串的签名；
    #   * `key_hash` 是那把 SM4 的 SHA256（服务端没有 K，无法自算 —— 见 docstring）。
    envelope = _as_envelope(envelope)
    signature = str(signature or '').strip()
    if not signature:
        # 没有签名就**不收**。这是"移除服务端代签名"的落点：服务端既不签，
        # 也不接受"没签的"——留一条无签名的入口，等于把签名变成可选，
        # 而"可选的安全属性"在实践中总是退化成"没有"。
        raise C.ContractError(
            '缺少签名：分发信封必须由发送节点用本地 Falcon 私钥签名后提交',
            code=C.ERR_SIGNATURE_REQUIRED,
        )
    key_hash = _as_key_hash(key_hash)

    inner_json = _canonical_inner_json(envelope, canonical)
    digest = ciphertext_digest(inner_json)
    declared_digest = str(envelope.get('ciphertext_digest') or '').strip()
    if declared_digest and declared_digest != digest:
        # 节点声明的摘要与服务端重算的对不上 —— 只可能是两边的规范化口径漂移了。
        # **不收**：等 KMS-010 拿它去验签时才发现的话，报出来的会是"签名无效"，
        # 而那看起来像伪造（安全事件），实际只是序列化不一致。
        #
        # ⚠️ 这一条必须**先于**验签（它排在下面那段之前）。两者报的都是"这封信
        #    有问题"，但处置完全不同：这里是"我们改了规范"，那里是安全事件。
        #    顺序反了的话，序列化漂移会全部伪装成伪造。
        raise C.ContractError(
            '信封的密文摘要与服务端重算的不一致：两侧的规范化序列化口径可能漂移了',
            code=C.ERR_ENVELOPE_TAMPERED,
        )

    # --- KMS-010：验签。失败方向必须是**拒绝**，不能是放行 ---
    # 公钥来自**登记表**那一行（`NodeLongTermKey.public_key`，**hex**），
    # `verify_node_envelope` 内部按形状认编码（`_decode_registry_key_material`）
    # —— 用用户腿那套 base64 解码会**永远验不过**且不报编码错（KMS-009 实测）。
    #
    # ⚠️ 验签覆盖的字段集（`NODE_ENVELOPE_SIGNED_FIELDS`）包含 `sender_node_id`
    #    等元数据，所以"用别的节点私钥签、却声称是本节点发的"必然验不过 ——
    #    签名绑住了发送者身份，这里不只是检查"有没有签名"。
    #
    # ⚠️ 验签用的信封就是**待落库的那一份**（含 batch_id/expires_at 等）——
    #    重建被签字节串的 `node_canonical_payload` 取的是同一批字段，而它们
    #    刚才已经过了形状与摘要检查。服务端**不**把签名写进这份 dict 再验
    #    （签名字段不在被签字段集里，写不写都不影响，但少动一份更不容易错）。
    if not verify_node_envelope(envelope, signature, signing_key.public_key):
        raise C.ContractError(
            f'信封签名校验失败：签名与发送节点 {sender.node_id} 的 FALCON 密钥 '
            f'{signing_key.key_id} v{signing_key.key_version} 不匹配，'
            f'或信封内容在签名之后被改动过',
            code=C.ERR_SIGNATURE_INVALID,
        )

    stored_json = json.dumps(
        {**envelope, 'signature': signature},
        ensure_ascii=False, sort_keys=True, separators=(',', ':'),
    )

    try:
        with transaction.atomic():
            PreDistributedKey.objects.create(
                pool_id=batch_id,
                key_index=0,
                # `node1` = 收件节点（`node_session_views` 取信封就是按
                # `node1=<自己> AND recipient_type='node'` 查的）。
                node1=receiver,
                node2=None,
                algorithm=wrapping,
                wrapping_algorithm=wrapping,
                payload_algorithm=PAYLOAD_ALGORITHM_SM4,
                # 新模型没有"用户来源密钥"。留 NULL 而不是编一个 0：
                # 0 会被下游当成一把真的 key_id 去查。
                source_key_id=None,
                recipient_type='node',
                encrypted_key_data=stored_json,
                key_hash=key_hash,
                status='distributed',
                expires_at=expires_at,
                # KMS-007 为"这一项是用哪把长期密钥封的"补的两列 —— 新流程里
                # 它从"生成时顺手记下的"升级为"**请求指定的、封装实际用的**那一版"，
                # 于是回收时的精确失效天然命中，不需要任何退化匹配。
                long_term_key_id=key.key_id,
                long_term_key_version=key.key_version,
            )

            src_domain, target_domains, dist_type = classify_distribution(sender, [receiver])
            batch = DistributionBatch.objects.create(
                batch_id=batch_id,
                user_id=sender.sys_user_id,
                # 同上：新模型没有用户来源密钥。
                source_key_id=None,
                wrapping_algorithm=wrapping,
                node_ids=json.dumps([receiver.id]),
                node_success_count=1,
                # 没有用户腿，这一列如实记 False（旧流程它表示"用户那份也成功了"）。
                user_envelope_ok=False,
                status='success',
                source_domain_id=src_domain,
                target_domain_ids=json.dumps(target_domains, ensure_ascii=False),
                distribution_type=dist_type,
            )

            session_count = create_initiated_sessions(
                sender, {receiver.id: receiver}, [receiver.id], batch_id, expires_at,
                dispatch='node_distribution', session_type=wrapping,
                # KMS-011：会话记录关联的具体密钥版本 —— 就是本次实际用的
                # 那两行（接收方那一版 + 发送方签名那一版）。验收签/取信封
                # 与页面显示都读它们，不再靠 batch_id 反查。
                recipient_key=key, falcon_key=signing_key,
            )
    except IntegrityError as exc:
        # `batch_id` 撞唯一约束。KMS-009 起批次号由**调用方**生成，所以撞号是
        # 真会发生的事（页面生成的随机后缀撞上、或同一个批次被提交两次）。
        #
        # ⚠️ 不把它原样抛出去：Django 的 IntegrityError 里带着表名与索引名，
        #    接口层兜底 except 会把它们一起回给调用方（看起来像库坏了）。
        #    而且**必须**在这里转，因为撞号是**可重试**的业务冲突，
        #    与"写信封时出错"（500）不是一回事。
        if 'batch_id' in str(exc):
            raise C.ContractError(
                f'批次号 {batch_id} 已被使用：同一次分发不要重复提交，'
                f'或重新生成一个批次号',
                code=C.ERR_INVALID_PARAMETER,
            ) from exc
        raise

    # 上链在事务**提交之后**（与 KMS-006/007 同口径）：存证失败不该回滚一次
    # 已经成立的分发 —— 信封已经落库、接收方已经能取到它。
    chain_hash = record_distribution_chain_event(
        'KEY_DISTRIBUTED',
        key.pk,
        key.key_version,
        receiver.node_id,
        digest,
        batch_id,
    )

    # KMS-012：把**这条分发对应的会话**一并回给调用方。发起方要拿它做两件事：
    #   1. 把本机那把 K 存进本地会话密钥库（KMS-012 的"本地保存"那条）；
    #   2. 提交自己的持有证明（确认）—— 会话 ID 是 proof 的消息，
    #      让调用方从批次号去拼（`{batch}-n{pk}`）等于把命名约定泄露给每个调用方，
    #      拼错的表现是"确认提交了、对方却永远等不到"。
    session = SessionKey.objects.filter(session_id=f'{batch_id}-n{receiver.id}').first()

    return {
        'batch': batch,
        'batch_id': batch_id,
        # 回显本次用的两个拼写：规范名（请求口径）与封装拼写（库内口径）。
        # 分开回显是因为它们**不是一回事**（KYBER ↔ kyber_kem），
        # 排障时"请求说的"与"库里记的"对不上是最常见的困惑。
        'protection_algorithm': canonical,
        'wrapping_algorithm': wrapping,
        'key_hash': key_hash,
        'digest': digest,
        'recipient_key': key,
        # KMS-010：签名者那一版（回显给接口层，回执里如实说"验过了"）。
        # 走到这里它必然非空 —— 上面验签不过会抛 SIGNATURE_INVALID。
        'signing_key': signing_key,
        'signature_verified': True,
        'session_count': session_count,
        # KMS-012：这条分发建出来的会话（发起方据此保存 K 并提交确认）。
        # 取不到时如实为 None —— 旧用户腿路径不建"节点到节点会话"的那种情形。
        'session_id': session.session_id if session else None,
        'session_status': session.status if session else None,
        'chain_hash': chain_hash,
        'expires_at': expires_at,
    }


__all__ = [
    'DEFAULT_EXPIRES_HOURS',
    'MAX_EXPIRES_HOURS',
    'authorized_node_ids',
    'create_initiated_sessions',
    'record_distribution_chain_event',
    'classify_distribution',
    'create_node_distribution',
]
