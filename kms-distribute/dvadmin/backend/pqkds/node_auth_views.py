# -*- coding: utf-8 -*-
"""节点设备凭据认证（文档 §3 激活 / §5 登录）。

    POST /node-self/activate/          节点名 + 一次性激活凭证 → 登记设备公钥 + 换发令牌
    GET  /node-self/challenge/?nodeId= 签发一次性随机挑战
    POST /node-self/login/             签名挑战 → 验签 → 换发令牌

为什么单独一个模块
------------------
这三件事是**同一个信任链的三步**，拆开放会看不见它们互为前提：
    激活（凭证证明"管理员允许这个节点上线"）
      → 登记设备公钥（把"这台设备"与节点绑定）
      → 挑战-应答（此后每次登录证明"我还是这台设备"）

为什么节点没有口令
------------------
文档 §3 的原设计是「节点名称 + 一次性激活码」，**没有口令**。本模块按这个来：
节点账号在 `sys_user` 里的口令是一个**随机且从不披露**的哈希（见
`node_account_service`），因此"用口令登录节点"在服务端层面不可能成功 ——
不是界面上藏了入口，而是根本没有可用的口令。

身份从哪来
----------
⚠️ 与前缀 `/node-self/` 下其它模块**不同**：那三个端点（`node_self` /
`init` / `keys`）都要求**已经在登录态**（`require_kms_user` 解析令牌）。
本模块的 `activate` 与 `login` 恰恰是**用来产生令牌**的，所以它们
**不能**要求登录态 —— 否则就成了"要登录才能登录"。

代价是这两个端点必须自己扛住未认证流量，因此：
  * 激活凭证 一次性 + 有有效期 + 恒定时间比较 + 只存哈希；
  * 挑战 随机 32 字节 + 短 TTL + **用即删**（防重放）。
两者任一不成立都会让"无口令"变成"无防护"。

⚠️ 铸令牌走内部通道（`kms_service_client.issue_session`），不在这里自己造令牌 ——
   本仓库的令牌只有 RuoYi 一个来源（D7），复制一份 JWT 签发逻辑会让身份源变成两处。
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import secrets
from datetime import timedelta

from django.core.cache import cache
from django.db import transaction
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from . import kms_service_client
from .models import Node

logger = logging.getLogger(__name__)

#: 激活凭证有效期。文档 §3 只要求"有有效期"，没给具体值 ——
#: 取 24 小时：够管理员把凭证交给节点操作者，又不至于长期有效。
ACTIVATION_TTL = timedelta(hours=24)

#: 挑战有效期（秒）。登录是交互动作，2 分钟足够，短一点更安全。
CHALLENGE_TTL = 120

#: 挑战在缓存里的键前缀。与 pqkds 的 KEY_PREFIX 叠加后形如
#: `pqkds:node-auth:challenge:<id>`。
CHALLENGE_KEY = 'node-auth:challenge:{}'

#: 签名接受的曲线。写死一处，验签与前端生成都必须与它一致。
DEVICE_AUTH_ALGORITHM = 'ECDSA-P256'


def _ok(data=None, msg='操作成功'):
    return JsonResponse({'code': 200, 'msg': msg, 'data': data})


def _error(msg, code=400):
    # 与 node_self_views / node_session_views 保持**同一套**约定：
    # HTTP 恒为 200，错误放在业务码里，字段名是 `msg`。
    # （本仓库 Django 侧另有一套 `{code,message}` + 真实状态码的约定，
    #   但 `/node-self/` 这个命名空间下只用这一种。混用会让每个调用方
    #   都得写 `body?.msg || body?.message` 再叠一层状态码判断。）
    return JsonResponse({'code': code, 'msg': msg, 'data': None}, status=200)


def _hash_code(code: str) -> str:
    """凭证只存哈希。用 SHA-256 而非 bcrypt：
    凭证是 32 字节的高熵随机串（不是人选的口令），无需抗字典攻击，
    而激活是**在线**动作 —— bcrypt 的成本在这里只换来延迟。
    """
    return hashlib.sha256(code.encode('utf-8')).hexdigest()


def issue_activation_code(node: Node) -> str:
    """为一个节点签发（或重签）一次性激活凭证，返回**明文**。

    明文只在这个返回值里出现一次，调用方负责只回传给管理员一次；库里只留哈希。
    重签会**立即作废**旧凭证（同一列被覆盖），符合文档 §3「支持管理员重新签发」。
    """
    code = secrets.token_urlsafe(32)
    now = timezone.now()
    node.activation_code_hash = _hash_code(code)
    node.activation_code_issued_at = now
    node.activation_code_expires_at = now + ACTIVATION_TTL
    node.save(update_fields=[
        'activation_code_hash', 'activation_code_issued_at', 'activation_code_expires_at',
    ])
    return code


def _verify_and_consume_code(node: Node, code: str) -> tuple[bool, str]:
    """校验凭证并**立即作废**。

    返回 `(是否通过, 失败原因)`。

    ⚠️ 顺序很重要：先做**恒定时间**比较，再判断过期。
       若先判过期再比较，攻击者可以靠响应差异区分"凭证不存在"与"已过期"，
       从而枚举出哪些节点正在等待激活。
    """
    stored = (node.activation_code_hash or '').strip()
    if not stored:
        return False, '该节点没有待使用的激活凭证，请联系管理员重新签发'

    if not secrets.compare_digest(stored, _hash_code(code)):
        return False, '激活凭证不正确'

    expires_at = node.activation_code_expires_at
    if expires_at and timezone.now() > expires_at:
        return False, '激活凭证已过期，请联系管理员重新签发'

    # 一次性：无论后续成功与否，校验通过即作废，杜绝同一凭证被用两次
    # （并发下两个请求同时通过校验 → 后写的覆盖前者，设备公钥只留最后一个；
    #   这是可接受的：后到的那次会成为"这台设备"，先到的需要重新激活。）
    node.activation_code_hash = ''
    node.activation_code_expires_at = None
    return True, ''


@csrf_exempt
@require_http_methods(['POST'])
def node_activate(request):
    """节点首次激活（文档 §3）：节点名 + 一次性凭证 → 登记设备公钥。

    请求体：
        {"nodeId": "Node-001", "code": "...", "devicePublicKey": {...}, "deviceAlgorithm": "ECDSA-P256"}

    `devicePublicKey` 是 **JWK JSON 对象**（WebCrypto 导出的公钥形状）。
    服务端只收公钥 —— 私钥不可导出，也从未离开浏览器。

    成功返回 `{token, node}`：令牌是标准 RuoYi 令牌，前端拿它就能进站。
    """
    try:
        payload = json.loads(request.body or b'{}')
    except (ValueError, TypeError):
        return _error('请求体不是合法 JSON')
    if not isinstance(payload, dict):
        return _error('请求体应为 JSON 对象')

    node_id = str(payload.get('nodeId') or '').strip()
    code = str(payload.get('code') or '').strip()
    public_key = payload.get('devicePublicKey')
    algorithm = str(payload.get('deviceAlgorithm') or DEVICE_AUTH_ALGORITHM).strip()

    if not node_id or not code:
        return _error('缺少节点名称或激活凭证')
    if not isinstance(public_key, dict) or not public_key:
        return _error('缺少设备公钥（应为 JWK 对象）')

    # ⚠️ 显式拒绝任何私钥字段名。与 node_self_views 里登记公钥时同一道闸：
    #    私钥一旦被顺手传上来，整套"私钥不出本机"就不成立了。
    forbidden = [k for k in public_key if 'private' in str(k).lower() or str(k).lower() == 'd']
    if forbidden:
        return _error('设备公钥中不得包含私钥字段：' + '、'.join(forbidden))

    if algorithm != DEVICE_AUTH_ALGORITHM:
        return _error(f'不支持的设备认证算法：{algorithm}')

    node = Node.objects.filter(node_id=node_id).first()
    if node is None:
        # ⚠️ 不区分"节点不存在"与"凭证不对"，避免用激活接口枚举节点是否存在。
        #    这与登录失败不透露"用户名是否存在"是同一条原则。
        return _error('节点不存在或激活凭证不正确')

    with transaction.atomic():
        ok, reason = _verify_and_consume_code(node, code)
        if not ok:
            return _error(reason)

        node.device_auth_public_key = json.dumps(public_key, separators=(',', ':'))
        node.device_auth_algorithm = algorithm
        # key_device_id 保留并写入**公钥指纹**：它是可验证的量，
        # 比原来浏览器自报的随机串有信息量（见 models.py 里那段注释的演进）。
        node.key_device_id = _public_key_fingerprint(public_key)
        node.activated_at = timezone.now()
        node.save(update_fields=[
            'device_auth_public_key', 'device_auth_algorithm',
            'key_device_id', 'activated_at',
            # 上面 _verify_and_consume_code 已把这两列清空，一并落库
            'activation_code_hash', 'activation_code_expires_at',
        ])

    if not node.sys_user_id:
        # 建节点流程会给每个 Node 配一个 sys_user（node_account_service）。
        # 走到这里说明数据不一致 —— 与其铸一个没有主体的令牌，不如说清楚。
        return _error('该节点尚未绑定登录账号，请联系管理员重新创建节点', 500)

    try:
        token = kms_service_client.issue_session(int(node.sys_user_id))
    except kms_service_client.KmsServiceError as exc:
        logger.exception('节点 %s 激活后铸令牌失败', node_id)
        return _error(f'激活成功但登录令牌签发失败：{exc}', 500)

    return _ok({'token': token, 'nodeId': node.node_id, 'name': node.name},
               msg='激活成功')


@csrf_exempt
@require_http_methods(['GET'])
def node_challenge(request):
    """签发一次性登录挑战（文档 §5）。

    查询参数 `?nodeId=Node-001`。

    ⚠️ 挑战**必须**服务端生成，不能让客户端传 —— 客户端可控的挑战等于没有挑战
       （攻击者固定一个已知值，就能重放一次抓到的签名）。
    """
    node_id = str(request.GET.get('nodeId') or '').strip()
    if not node_id:
        return _error('缺少 nodeId')

    node = Node.objects.filter(node_id=node_id).only(
        'node_id', 'status', 'device_auth_public_key').first()
    if node is None:
        return _error('节点不存在或尚未激活')

    # 没登记设备公钥 = 还没激活过，走激活流程而不是登录流程。
    # 明确区分这两者，前端才能给出"去激活"而不是"登录失败"。
    if not (node.device_auth_public_key or '').strip():
        return _error('该节点尚未在本机激活，请先用激活凭证完成激活', 409)

    challenge_id = secrets.token_urlsafe(18)
    challenge = secrets.token_hex(32)
    cache.set(
        CHALLENGE_KEY.format(challenge_id),
        {'nodeId': node.node_id, 'challenge': challenge},
        CHALLENGE_TTL,
    )
    # 挑战明文返回给客户端让它签名；challengeId 用于登录时取回。
    # 两者都不是秘密（挑战本就是公开量），秘密是**只有那台设备才签得出来**。
    return _ok({'challengeId': challenge_id, 'challenge': challenge, 'ttl': CHALLENGE_TTL})


@csrf_exempt
@require_http_methods(['GET'])
def node_still_exists(request):
    """批量问"这些节点还在不在"（登录页校对**本机缓存**用）。

    查询参数：`?nodeIds=A,B,C`（业务编号，逗号分隔，上限 50）
    返回：`{'exists': {'A': true, 'B': false}}`

    <h2>为什么需要它</h2>
    一台设备只应保留**一个**节点的登录信息（本机绑定文件 + 设备凭据），
    而"本机记录"与"服务端事实"会分叉：管理员删了节点、整个库被重置、
    节点被重建 —— 这时浏览器里仍留着一个点进去必然失败的条目，
    而用户看不出它已经作废。

    登录页在**拿到令牌之前**没有任何带鉴权的接口可用（这时它还没登录），
    所以这条校对接口必须免鉴权。它**只回答存在性**，不回名字/状态/公钥/IP ——
    需要的只是"还要不要留着这条本地记录"。

    <h2>信息暴露的边界（如实记录，不粉饰）</h2>
    本接口是一个**存在性 oracle**，与 `node_challenge` 已有的
    "节点不存在或尚未激活"是同一量级。之所以可接受：
      * 只对**已知编号**回答，不能枚举（不知道编号就问不出什么）；
      * 不回任何可用信息（拿到 true 也没法登录 —— 登录要设备私钥签名）；
      * 限流由网关承担，与其它免鉴权端点一致。
    即便如此也**不扩围**：不要在这里加"节点列表"或任何字段。
    """
    raw = str(request.GET.get('nodeIds') or '')
    wanted = [part.strip() for part in raw.split(',') if part.strip()]
    if not wanted:
        return _error('缺少 nodeIds')
    if len(wanted) > 50:
        # 上限不是性能考量（这条查询很便宜），是**防枚举**：一次问 50 个
        # 与一个个问，成本相同；但没有上限就等于给了一个批量探测口。
        return _error('一次最多校对 50 个节点', 400)

    found = set(
        Node.objects.filter(node_id__in=wanted).values_list('node_id', flat=True)
    )
    return _ok({'exists': {node_id: node_id in found for node_id in wanted}})


@csrf_exempt
@require_http_methods(['POST'])
def node_login(request):
    """挑战-应答登录（文档 §5）。

    请求体：`{"nodeId": "Node-001", "challengeId": "...", "signature": "<base64>"}`

    验证过程：
      1. 取回并**立即删除**挑战（用即删 → 天然防重放）；
      2. 确认挑战确实属于该节点；
      3. 用登记的设备公钥验签。
    """
    try:
        import json as _json
        payload = _json.loads(request.body or b'{}')
    except (ValueError, TypeError):
        return _error('请求体不是合法 JSON')
    if not isinstance(payload, dict):
        return _error('请求体应为 JSON 对象')

    node_id = str(payload.get('nodeId') or '').strip()
    challenge_id = str(payload.get('challengeId') or '').strip()
    signature = str(payload.get('signature') or '').strip()

    if not node_id or not challenge_id or not signature:
        return _error('缺少 nodeId / challengeId / signature')

    node = Node.objects.filter(node_id=node_id).first()
    if node is None:
        return _error('节点不存在')

    if node.status in ('disabled', 'inactive'):
        return _error('该节点已被停用，请联系管理员', 403)

    key = CHALLENGE_KEY.format(challenge_id)
    stored = cache.get(key)
    # 用即删：无论后续验签成功与否都删掉。
    # 放在验签**之前**，否则验签失败时挑战仍在，就成了可反复试签名的窗口。
    cache.delete(key)

    if not stored:
        return _error('挑战不存在或已过期，请重新发起登录', 409)

    if stored.get('nodeId') != node.node_id:
        # 挑战是给别的节点的 —— 说明有人在跨节点套用。
        # 不透露挑战属于谁，如实拒绝即可。
        return _error('挑战与节点不匹配', 403)

    public_key_json = (node.device_auth_public_key or '').strip()
    if not public_key_json:
        return _error('该节点尚未在本机激活，请先用激活凭证完成激活', 409)

    try:
        public_key = json.loads(public_key_json)
    except (ValueError, TypeError):
        logger.exception('节点 %s 的设备公钥无法解析', node_id)
        return _error('设备公钥数据损坏，请联系管理员重新激活', 500)

    verified = verify_device_signature(
        public_key=public_key,
        message=str(stored.get('challenge') or ''),
        signature_b64=signature,
        algorithm=node.device_auth_algorithm or DEVICE_AUTH_ALGORITHM,
    )
    if not verified:
        # 不区分"签名格式错"与"签名对不上"：对调用方都是"你不是那台设备"。
        return _error('设备签名验证失败：本机凭据与该节点登记的不一致', 403)

    if not node.sys_user_id:
        return _error('该节点尚未绑定登录账号，请联系管理员重新创建节点', 500)

    try:
        token = kms_service_client.issue_session(int(node.sys_user_id))
    except kms_service_client.KmsServiceError as exc:
        logger.exception('节点 %s 登录铸令牌失败', node_id)
        return _error(f'登录令牌签发失败：{exc}', 500)

    return _ok({'token': token, 'nodeId': node.node_id, 'name': node.name}, msg='登录成功')


# ---------------------------------------------------------------------------
# 设备签名验签
# ---------------------------------------------------------------------------
def verify_device_signature(public_key: dict, message: str, signature_b64: str, algorithm: str) -> bool:
    """用登记的设备公钥验证挑战签名。

    公钥是 WebCrypto 导出的 **JWK**（`{kty:'EC', crv:'P-256', x:..., y:...}`），
    签名是 WebCrypto ECDSA 的 **raw r||s**（64 字节）—— 注意这不是 DER！

    ⚠️ 这两个格式差异是最容易踩的坑：
       * 用 `cryptography` 的 `load_pem_public_key` 解 JWK 会失败（JWK 不是 PEM）；
       * 把 raw r||s 当 DER 喂给 `verify()` 会直接抛异常而非返回 False，
         表现为"验签报错"而不是"验签不通过"，容易误判成服务端故障。
       所以这里显式用 `EllipticCurvePublicNumbers` 构造点、
       再把 raw 签名拆成 (r, s) 用 `encode_dss_signature` 转成 DER。
    """
    if algorithm != DEVICE_AUTH_ALGORITHM:
        logger.warning('不支持的设备签名算法：%s', algorithm)
        return False
    if public_key.get('kty') != 'EC' or public_key.get('crv') != 'P-256':
        logger.warning('设备公钥不是 P-256 EC：kty=%s crv=%s', public_key.get('kty'), public_key.get('crv'))
        return False

    try:
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature

        x = _b64url_to_int(public_key.get('x'))
        y = _b64url_to_int(public_key.get('y'))
        if x is None or y is None:
            return False

        pub = ec.EllipticCurvePublicNumbers(x, y, ec.SECP256R1()).public_key()

        raw = base64.b64decode(signature_b64)
        if len(raw) != 64:
            logger.warning('设备签名长度不是 64 字节（应为 raw r||s）：%d', len(raw))
            return False
        r = int.from_bytes(raw[:32], 'big')
        s = int.from_bytes(raw[32:], 'big')

        pub.verify(
            encode_dss_signature(r, s),
            message.encode('utf-8'),
            ec.ECDSA(hashes.SHA256()),
        )
        return True
    except InvalidSignature:
        # 这是**预期内**的结果（不是那台设备），不该记成异常日志刷屏
        return False
    except Exception:  # noqa: BLE001
        logger.exception('设备签名验签过程异常')
        return False


def _b64url_to_int(value) -> int | None:
    """JWK 里的 x/y 是 base64url 无填充的定长大端整数。"""
    if not value:
        return None
    padded = str(value) + '=' * (-len(str(value)) % 4)
    return int.from_bytes(base64.urlsafe_b64decode(padded), 'big')


def _public_key_fingerprint(public_key: dict) -> str:
    """设备公钥指纹（SHA-256 前 16 字节十六进制）。

    用途：让管理员一眼看出"这个节点绑的设备有没有换"。
    它是**公开量**，不构成秘密，与私钥无关。
    """
    raw = f"{public_key.get('crv','')}|{public_key.get('x','')}|{public_key.get('y','')}"
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()[:32]
