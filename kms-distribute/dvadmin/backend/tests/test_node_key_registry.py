# -*- coding: utf-8 -*-
"""KMS-004 长期密钥登记的不变量自测（计划 §6.1 / §9.1）。

判据是什么
=========
计划 §13 要求"不以接口存在为完成"，所以这里断言的是**存储层的不变量**，
不是"函数返回了 success"：

  1. 登记必须**同时**写两处：`NodeLongTermKey` 一行 + `Node.<算法>_public_key`
     物化视图列；FALCON 还要一并写镜像列 `falcon_public_key`。只写一处不会
     报错，只会让"哪一处为准"取决于谁先读 —— 表现为"有时对"，比稳定错更难查。
  2. **同一节点同一算法最多一行 ACTIVE**，且必须在**数据库层**成立 ——
     应用层判断在并发下会双双通过。这条约束建在 `active_slot`（status 的派生列）
     上，因为 MySQL 不支持部分索引，而 Django 遇到不支持的后端会**静默跳过**
     那条约束；所以本脚本直接探数据库，而不是读代码确认它写了。
  3. 同一把公钥重复上报是**无操作**：节点初始化页每次进入都会重报四套公钥，
     不幂等的话每进一次页面就凭空多一个版本、把上一版降级成 RETIRED，
     而"当前版本号"正是信封要引用的东西。
  4. 回收必须**清空**物化视图列（含镜像列）。既有读路径大量直接取
     `node.<算法>_public_key`，不清空它们会把已回收的公钥当成可用 ——
     而失败是静默的：解密照样成功，只是本该被拒绝的分发通过了。

KMS-005 追加两组（keyId / 版本 —— 密钥身份的两段文本）
=====================================================
  5. `keyId` **不做任何静默更正**：首尾空白、越界字符（尤其 `/`）、超长一律拒绝，
     合法值逐字节落库。keyRef 是 `node/{节点}/{算法}/{keyId}/{版本}`，节点按它找
     私钥、服务端按它找信封；trim 或改大小写会让两边指向两个不同的 id，
     而两处各自"看起来都对"，只有按引用找密钥时才现形。
     校验还必须在**幂等分支之前**：否则重报同一把公钥时，非法 keyId 会被
     当成"已登记、无操作"吞掉，一个字都不落库、也不报错。
  6. `keyVersion` 只接受 ≥1 的整数，不做 `int()` 兜底（`int(1.9) → 1`、
     `int(True) → 1` 都是"以为存的是 X、实际存的是 Y"），且非法值**不落库**。
     与 keyId 相反，版本号 strip 之后收敛（两边最终都渲染成 `/1`），
     这个不对称是刻意的，别"顺手统一"。

KMS-006 追加两组（更新：显式身份与回收终态）
==========================================
  7. 更新（`rotate_public_key`）必须**显式携带** keyId 与 keyVersion ——
     计划 §6.1 禁止"依赖当前最新版本的隐式行为"。老的"取最新一行 +1"
     有三个都不报错的坏结果：回收终态被叠上新版本、**别的 keyId 被降级**
     （生产版本被换掉而请求成功）、服务端算出的版本与节点本地已封存的分叉。
     三类仍在的拒绝（KEY_NOT_FOUND / KEY_REVOKED / KEY_VERSION_MISMATCH）
     各自对应其中一种。
  8. 任何被拒的更新都不得留下半行、不得改动生产版本与物化视图 ——
     这是阶段 2 判据②③（"旧版本不能被误当成当前生产版本"、
     "任一步失败不得把服务端标成 ACTIVE"）在存储层的可执行形式。
     接口层（`store_node_public_key(rotate=True)`）另要保证**缺一不可**：
     只给 keyId 时服务端能算出"下一版"，但算出的那一版与节点本地
     已按 keyRef 封存的可能不是同一个，两边都不报错。

**它必须跑在 dvadmin3-django 容器里**（要 Django 环境与数据库）：

    docker cp "backend/pqkds/node_key_registry.py"      dvadmin3-django:/backend/pqkds/
    docker cp "backend/pqkds/node_service.py"           dvadmin3-django:/backend/pqkds/
    docker cp "backend/pqkds/api_contract.py"           dvadmin3-django:/backend/pqkds/
    docker cp "backend/pqkds/models.py"                 dvadmin3-django:/backend/pqkds/
    docker cp "backend/tests/test_node_key_registry.py" dvadmin3-django:/backend/tests/
    docker exec -w /backend dvadmin3-django python tests/test_node_key_registry.py

⚠️ 会**创建并删除**临时节点（`TESTKMS004-*`，每个用例一个，互不干扰）。跑在
   开发库上，结束时无论成败都会删掉它们（CASCADE 一并清掉长期密钥行）。
"""

import base64
import os
import sys
import uuid
from datetime import timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "application.settings")

import django  # noqa: E402

django.setup()

from django.db import IntegrityError, transaction  # noqa: E402
from django.utils import timezone  # noqa: E402

from pqkds import api_contract as C  # noqa: E402
from pqkds import node_key_registry as R  # noqa: E402
from pqkds.models import Node, NodeLongTermKey  # noqa: E402
from pqkds.node_service import NodeService  # noqa: E402


def _report(name, ok, detail=""):
    print(f"  [{'OK' if ok else 'FAIL'}] {name}" + (f"  {detail}" if detail else ""))
    return bool(ok)


def _b64_key(size):
    """一把**存储形式**的假公钥（base64）。大小按真实密钥取：Kyber-768=1184B、
    Falcon-512 公钥=897B。长度不影响本模块的不变量，但取真实值能让
    "物化视图列里躺的到底是什么"一眼可辨。"""
    return base64.b64encode(os.urandom(size)).decode('ascii')


def _hex_pub(byte_pair):
    """130 位十六进制、04 开头的 SM2/SSCL 形状的公钥。"""
    return '04' + byte_pair * 64


def _make_node(tag):
    node = Node.objects.create(
        node_id=f'TESTKMS004-{tag}-{uuid.uuid4().hex[:6]}',
        name=f'KMS-004 自测节点（{tag}）',
        ip_address='127.0.0.1',
        port=9010,
        status='PENDING_INIT',
    )
    return node


def _expect_contract_error(code, fn, *args, **kwargs):
    """断言 `fn(...)` 抛出以 `code` 结尾的 `ContractError`。

    返回 `(ok, detail)` 而不是直接 raise：调用点要把结论攒进 `results`，
    一组用例里几十个断言，第一个失败就中断的话剩下的一无所知。
    """
    try:
        fn(*args, **kwargs)
    except C.ContractError as exc:
        if exc.code == code:
            return True, ''
        return False, f'错误码不符：期望 {code}，实际 {exc.code}'
    except Exception as exc:  # noqa: BLE001
        return False, f'抛出了非 ContractError：{type(exc).__name__}: {exc}'
    return False, '没有抛异常（被静默接受了）'


def _rejects(code, fn, *args, needle='', **kwargs):
    """同上，但**额外**要求错误文案里出现 `needle` —— 用来区分同一个错误码下的
    不同分支（例如"首尾空白"与"越界字符"都是 `ERR_INVALID_PARAMETER`，
    只对错误码的话，把 trim 检查删掉也能过）。"""
    try:
        fn(*args, **kwargs)
    except C.ContractError as exc:
        if exc.code != code:
            return False, f'错误码不符：期望 {code}，实际 {exc.code}'
        if needle and needle not in exc.message:
            return False, f'文案里没有 {needle!r}（说明走的是别的分支）：{exc.message[:60]}'
        return True, ''
    except Exception as exc:  # noqa: BLE001
        return False, f'抛出了非 ContractError：{type(exc).__name__}: {exc}'
    return False, '没有抛异常（被静默接受了）'


# ---------------------------------------------------------------------------
# 一、登记：两处必须一起写
# ---------------------------------------------------------------------------

def test_registration_writes_both_places(node):
    results = []

    kyber = _b64_key(1184)
    row = R.register_public_key(node, algorithm='KYBER', public_key=kyber)
    fresh = Node.objects.get(pk=node.pk)

    results.append(_report(
        'KYBER：新表记一行且为 ACTIVE',
        row.status == C.KEY_STATUS_ACTIVE and row.active_slot == 'KYBER',
        f'status={row.status} active_slot={row.active_slot!r}',
    ))
    results.append(_report('KYBER：物化视图列已同步', fresh.kyber_public_key == kyber))
    results.append(_report(
        '登记 KYBER 没有误写别的算法列',
        not fresh.gm_public_key and not fresh.sscl_public_key
        and not fresh.falcon_sign_public_key and not fresh.falcon_public_key,
    ))

    falcon = _b64_key(897)
    for alg, material in (('SM2', _hex_pub('ab')), ('SSCL', _hex_pub('cd')),
                          ('FALCON', falcon)):
        R.register_public_key(node, algorithm=alg, public_key=material)
        fresh = Node.objects.get(pk=node.pk)
        column = C.NODE_PUBLIC_KEY_COLUMN[alg]
        results.append(_report(
            f'{alg}：物化视图列 {column} 已同步',
            getattr(fresh, column) == material,
        ))

    fresh = Node.objects.get(pk=node.pk)
    results.append(_report(
        'FALCON：镜像列 falcon_public_key 一并写入（旧读路径还在用它）',
        fresh.falcon_public_key == falcon,
    ))

    # activate=False 的行是"待启用"，不能抢生产版本，也不能覆盖物化视图列
    R.register_public_key(node, algorithm='KYBER', public_key=_b64_key(800),
                          activate=False)
    fresh = Node.objects.get(pk=node.pk)
    results.append(_report(
        'activate=False 不写物化视图列（不抢生产版本）',
        fresh.kyber_public_key == kyber,
    ))
    return all(results)


# ---------------------------------------------------------------------------
# 二、幂等：重复上报同一把公钥不产生新版本
# ---------------------------------------------------------------------------

def test_reregistration_is_noop(node):
    results = []

    material = _b64_key(1184)
    first = R.register_public_key(node, algorithm='KYBER', public_key=material)
    second = R.register_public_key(node, algorithm='KYBER', public_key=material,
                                   device_id='dev-1', security_level='768')

    results.append(_report('同一把公钥重复上报返回同一行', first.pk == second.pk))
    results.append(_report('不产生新版本', second.key_version == 1,
                           f'v{second.key_version}'))
    results.append(_report(
        '该算法只有一行',
        NodeLongTermKey.objects.filter(node=node, algorithm='KYBER').count() == 1,
    ))
    results.append(_report(
        '空字段被补上（device_id / security_level）',
        second.device_id == 'dev-1' and second.security_level == '768',
    ))

    third = R.register_public_key(node, algorithm='KYBER', public_key=material,
                                  device_id='dev-2', security_level='512')
    results.append(_report(
        '已有字段不被后续上报改写（那是密钥生成时的环境）',
        third.device_id == 'dev-1' and third.security_level == '768',
        f'device_id={third.device_id} level={third.security_level}',
    ))

    # 同 key_id + 同版本、但公钥不同 —— 这不是"重报"，是真冲突：必须明确拒绝，
    # 而不是静默覆盖（要换公钥应当走 rotate，语义是"新版本"而非"同名覆盖"）。
    try:
        R.register_public_key(node, algorithm='KYBER', public_key=_b64_key(1184),
                              key_id=first.key_id, key_version=first.key_version)
        results.append(_report('同 key_id+版本、不同公钥 → 明确拒绝', False, '没有抛异常'))
    except C.ContractError as exc:
        results.append(_report(
            '同 key_id+版本、不同公钥 → 明确拒绝',
            exc.code == C.ERR_KEY_VERSION_MISMATCH, f'code={exc.code}',
        ))
    return all(results)


# ---------------------------------------------------------------------------
# 三、轮换：新版本上位，旧版本降级且让出槽位
# ---------------------------------------------------------------------------

def test_rotation_demotes_previous(node):
    results = []

    v1_material = _b64_key(1184)
    v1 = R.register_public_key(node, algorithm='KYBER', public_key=v1_material)
    v2_material = _b64_key(1184)
    v2 = R.register_public_key(node, algorithm='KYBER', public_key=v2_material)
    v1.refresh_from_db()

    results.append(_report('旧版本降级为 RETIRED', v1.status == C.KEY_STATUS_RETIRED,
                           v1.status))
    results.append(_report(
        '降级后 active_slot 被清空（否则下一次登记会撞唯一约束）',
        v1.active_slot is None, repr(v1.active_slot),
    ))
    results.append(_report(
        '新版本为 ACTIVE',
        v2.status == C.KEY_STATUS_ACTIVE and v2.active_slot == 'KYBER',
    ))
    results.append(_report(
        '物化视图指向新版本',
        Node.objects.get(pk=node.pk).kyber_public_key == v2_material,
    ))
    results.append(_report('旧公钥仍保留在审计行里（版本可回溯）',
                           v1.public_key == v1_material))

    # 更新（KMS-006）：版本由调用方显式给出，服务端不再"取最新一行 +1"。
    # v1/v2 是两次**独立生成**（各自铸了新 keyId），这里要更新的正是 v2 这把 ——
    # 更新必须落在 v2 的身份上，而不是"碰巧最新"那一行。
    v3_material = _b64_key(1184)
    v3 = R.rotate_public_key(node, algorithm='KYBER', public_key=v3_material,
                             key_id=v2.key_id, key_version=v2.key_version + 1)
    v2.refresh_from_db()
    results.append(_report(
        '更新保留 key_id 并递增 key_version（计划 §6.1）',
        v3.key_id == v2.key_id and v3.key_version == v2.key_version + 1,
        f'{v3.key_id} v{v3.key_version}',
    ))
    results.append(_report('更新后上一版降级为 RETIRED',
                           v2.status == C.KEY_STATUS_RETIRED))
    return all(results)


# ---------------------------------------------------------------------------
# 四、数据库层唯一性真的生效（MySQL 部分索引静默失效的坑）
# ---------------------------------------------------------------------------

def test_db_enforces_single_active(node):
    results = []

    R.register_public_key(node, algorithm='SSCL', public_key=_hex_pub('11'))

    def probe(status_value):
        """直接插一行，绕过应用层降级逻辑，看数据库拦不拦。"""
        try:
            with transaction.atomic():
                NodeLongTermKey.objects.create(
                    node=node,
                    key_id=f'probe-{uuid.uuid4().hex[:8]}',
                    key_version=1,
                    algorithm='SSCL',
                    status=status_value,
                    public_key='probe',
                    public_key_hash=R.hash_public_key('probe'),
                )
            return True
        except IntegrityError:
            return False

    results.append(_report(
        '数据库拒绝第二个 ACTIVE（pqkds_ltk_uniq_active_per_node_alg 真建出来了）',
        not probe(C.KEY_STATUS_ACTIVE),
    ))
    results.append(_report(
        '非 ACTIVE 行（active_slot=NULL）不受约束影响，可以并存',
        probe(C.KEY_STATUS_PENDING) and probe(C.KEY_STATUS_PENDING),
        '唯一索引忽略 NULL —— 这正是本设计能在 MySQL 上成立的原因',
    ))
    return all(results)


# ---------------------------------------------------------------------------
# 五、回收：清空物化视图（含镜像列），但保住审计线索
# ---------------------------------------------------------------------------

def test_revoke_clears_node_columns(node):
    results = []

    kyber = R.register_public_key(node, algorithm='KYBER', public_key=_b64_key(1184))
    falcon = R.register_public_key(node, algorithm='FALCON', public_key=_b64_key(897))
    node.status = 'active'
    node.save(update_fields=['status'])

    R.revoke_public_key(kyber, '自测回收')
    kyber.refresh_from_db()
    fresh = Node.objects.get(pk=node.pk)

    results.append(_report('状态置为 REVOKED', kyber.status == C.KEY_STATUS_REVOKED))
    results.append(_report('保留 public_key 作审计线索（清空旧列不再丢证据）',
                           bool(kyber.public_key)))
    results.append(_report('回收原因落库', kyber.revoked_reason == '自测回收'))
    results.append(_report(
        '清空 kyber_public_key（否则既有读路径继续当成可用）',
        fresh.kyber_public_key == '', repr(fresh.kyber_public_key[:20]),
    ))
    results.append(_report(
        '不动其他算法列',
        bool(fresh.falcon_sign_public_key) and bool(fresh.falcon_public_key),
    ))
    results.append(_report(
        '不动 Node.status（撤一个算法 ≠ 节点没初始化；且两套状态拼写不同）',
        fresh.status == 'active', fresh.status,
    ))
    again = R.revoke_public_key(kyber, '重复回收')
    results.append(_report('重复回收是幂等无操作', again.revoked_reason == '自测回收'))

    R.revoke_public_key(falcon, '自测回收 Falcon')
    fresh = Node.objects.get(pk=node.pk)
    results.append(_report(
        'FALCON 回收时两列一起清空（规范列 + 镜像列）',
        fresh.falcon_sign_public_key == '' and fresh.falcon_public_key == '',
    ))
    return all(results)


# ---------------------------------------------------------------------------
# 六、require_usable_key：错误码要能区分"回收了"和"从来没有"
# ---------------------------------------------------------------------------

def test_require_usable_key_error_codes(node):
    results = []

    def code_of(fn, **kwargs):
        try:
            fn(**kwargs)
            return None
        except C.ContractError as exc:
            return exc.code

    results.append(_report(
        '未登记 → KEY_NOT_FOUND',
        code_of(R.require_usable_key, node=node, algorithm='SM2')
        == C.ERR_KEY_NOT_FOUND,
    ))

    v1 = R.register_public_key(node, algorithm='SM2', public_key=_hex_pub('ab'))
    results.append(_report(
        '已登记 → 返回生产版本',
        R.require_usable_key(node, 'SM2').pk == v1.pk,
    ))

    # 更新（KMS-006）：同 keyId 的新版本，身份与版本都由调用方显式给出。
    v2 = R.rotate_public_key(node, algorithm='SM2', public_key=_hex_pub('cd'),
                             key_id=v1.key_id, key_version=v1.key_version + 1)
    results.append(_report(
        '轮换后默认取新版本',
        R.require_usable_key(node, 'SM2').pk == v2.pk,
    ))
    results.append(_report(
        '解旧信封路径取到可用版本（不是 KEY_NOT_FOUND）',
        R.require_usable_key(node, 'SM2', for_new_work=False).pk == v2.pk,
    ))

    # 回收生产版本：新工作被拒；但 RETIRED 的旧版本对"解旧信封"仍须可用 ——
    # 旧信封是按当时那一版公钥封的，只看 ACTIVE 会让它报"密钥不存在"。
    R.revoke_public_key(v2, '自测')
    results.append(_report(
        '回收后要新分发 → KEY_REVOKED',
        code_of(R.require_usable_key, node=node, algorithm='SM2') == C.ERR_KEY_REVOKED,
    ))
    try:
        old = R.require_usable_key(node, 'SM2', for_new_work=False)
        results.append(_report(
            '回收后仍能取到 RETIRED 旧版本用于解封',
            old.pk == v1.pk, f'取到 v{old.key_version} {old.status}',
        ))
    except C.ContractError as exc:
        results.append(_report('回收后仍能取到 RETIRED 旧版本用于解封', False,
                               f'{exc.code}: {exc}'))

    # 只有 REVOKED 时，解封也必须拒绝：回收的语义就是"不许再用"
    kyber = R.register_public_key(node, algorithm='KYBER', public_key=_b64_key(1184))
    R.revoke_public_key(kyber, '自测')
    results.append(_report(
        '已回收的密钥不允许解封 → KEY_REVOKED',
        code_of(R.require_usable_key, node=node, algorithm='KYBER',
                for_new_work=False) == C.ERR_KEY_REVOKED,
    ))

    # 过期：两路都拒绝（计划 §9.1「回收、过期……均被拒绝」）
    R.register_public_key(node, algorithm='SSCL', public_key=_hex_pub('12'),
                          expires_at=timezone.now() - timedelta(hours=1))
    results.append(_report(
        '过期密钥不允许新分发 → KEY_EXPIRED',
        code_of(R.require_usable_key, node=node, algorithm='SSCL') == C.ERR_KEY_EXPIRED,
    ))
    results.append(_report(
        '过期密钥不允许解封 → KEY_EXPIRED',
        code_of(R.require_usable_key, node=node, algorithm='SSCL',
                for_new_work=False) == C.ERR_KEY_EXPIRED,
    ))

    # 迁移回填的 LEGACY 行（来源不明）刻意不在放行集合里：
    # 它可能根本没有对应私钥，"以为能解、解到一半才发现"比一开始就拒绝更糟。
    legacy = NodeLongTermKey.objects.create(
        node=node, key_id='legacy-自测', key_version=1, algorithm='FALCON',
        status=C.KEY_STATUS_LEGACY, public_key=_b64_key(897),
        public_key_hash=R.hash_public_key('legacy'),
    )
    results.append(_report('LEGACY 行不允许解封（来源不明可能没有私钥）',
                           not legacy.allows_unwrap))
    results.append(_report(
        'LEGACY 存在也不算能用 → KEY_NOT_FOUND',
        code_of(R.require_usable_key, node=node, algorithm='FALCON',
                for_new_work=False) == C.ERR_KEY_NOT_FOUND,
    ))
    return all(results)


# ---------------------------------------------------------------------------
# 七、节点级回收：一个节点的全部算法一起收（物化视图必须全清）
# ---------------------------------------------------------------------------

def test_revoke_all_for_node(node):
    results = []

    # 先把四个算法都登记上（本测试用独立节点，从零开始）
    for alg, material in (('KYBER', _b64_key(1184)), ('SM2', _hex_pub('ab')),
                          ('SSCL', _hex_pub('cd')), ('FALCON', _b64_key(897))):
        R.register_public_key(node, algorithm=alg, public_key=material)

    count = R.revoke_keys_for_node(node, '自测：节点整体回收')
    fresh = Node.objects.get(pk=node.pk)

    remaining = NodeLongTermKey.objects.filter(
        node=node).exclude(status=C.KEY_STATUS_REVOKED)
    results.append(_report('至少回收了四个算法的行', count >= 4, f'count={count}'))
    results.append(_report('没有留下未回收的行', not remaining.exists()))
    results.append(_report(
        '四列公钥（含 Falcon 镜像列）全部清空',
        not any([fresh.kyber_public_key, fresh.gm_public_key, fresh.sscl_public_key,
                 fresh.falcon_sign_public_key, fresh.falcon_public_key]),
    ))
    return all(results)


# ---------------------------------------------------------------------------
# 八、接口层：store_node_public_key 的归一化与设备一致性
# ---------------------------------------------------------------------------

def test_store_node_public_key_endpoint(node):
    results = []
    svc = NodeService(node.node_id)

    raw = os.urandom(1184)
    first = svc.store_node_public_key('KYBER', raw.hex(),
                                      security_level='768', device_id='dev-A')
    fresh = Node.objects.get(pk=node.pk)

    results.append(_report('上报成功', first.get('success') is True,
                           str(first.get('message'))))
    results.append(_report(
        'Kyber 公钥按 base64 落库（wrappers 按解码长度推断变体）',
        fresh.kyber_public_key == base64.b64encode(raw).decode(),
    ))
    results.append(_report('安全级别写入 kyber_security_level',
                           fresh.kyber_security_level == '768'))
    results.append(_report('设备标识绑定到节点', fresh.key_device_id == 'dev-A'))

    again = svc.store_node_public_key('KYBER', raw.hex(), security_level='768')
    results.append(_report(
        '重复上报仍是同一把（页面每次进入都会重报，不幂等会凭空轮换版本）',
        again.get('success') is True
        and NodeLongTermKey.objects.filter(node=node, algorithm='KYBER').count() == 1,
        f"count={NodeLongTermKey.objects.filter(node=node, algorithm='KYBER').count()}",
    ))

    bad_len = svc.store_node_public_key('KYBER', 'aabbcc')
    results.append(_report(
        '长度不对的 Kyber 公钥被拒绝',
        bad_len.get('success') is False and '800' in bad_len.get('message', ''),
        str(bad_len.get('message')),
    ))
    results.append(_report('非十六进制被拒绝',
                           svc.store_node_public_key('KYBER', 'zz' * 800).get('success') is False))

    # 历史别名指的是 CL-Falcon **格材料**，与标准 NIST Falcon 不兼容。
    # 收下来会被当成可用签名公钥登记，之后验签永远失败且看不出为什么。
    for alias in ('falcon_lattice', 'CL-FALCON', 'cl-falcon'):
        results.append(_report(f'历史别名 {alias} 被拒绝',
                               svc.store_node_public_key(alias, 'ab' * 100).get('success') is False))
    results.append(_report(
        '别名没有被误登记为 FALCON',
        not NodeLongTermKey.objects.filter(node=node, algorithm='FALCON').exists(),
    ))

    results.append(_report('同设备继续上报成功',
                           svc.store_node_public_key('SM2', _hex_pub('ef'),
                                                     device_id='dev-A').get('success') is True))
    mismatch = svc.store_node_public_key('SSCL', _hex_pub('12'), device_id='dev-B')
    results.append(_report(
        '换设备上报 → device_mismatch 且拒绝',
        mismatch.get('success') is False and mismatch.get('device_mismatch') is True,
        str(mismatch.get('message'))[:40],
    ))
    results.append(_report(
        '换设备被拒时没有登记进新表',
        not NodeLongTermKey.objects.filter(node=node, algorithm='SSCL').exists(),
    ))
    return all(results)


# ---------------------------------------------------------------------------
# 九、keyId：不做任何静默更正（判据"服务端记下的就是我本地那把"的文本一半）
# ---------------------------------------------------------------------------

def test_key_id_is_not_silently_corrected(node):
    """keyId 是**不透明文本**，一律逐字节比对。

    这里的每一条拒绝都对应一种"静默更正"的实现方式（trim / 转小写 / 截断 /
    放行分隔符）。它们都不报错，只是让服务端记的 id 与节点本地的 keyRef
    指向两个不同的密钥 —— 而两处各自"看起来都对"。
    """
    results = []

    # 1) 合法字符集逐字节落库（大小写也保留：不归一化）
    kid = 'Node_1.KYBER-2'
    row = R.register_public_key(node, algorithm='KYBER', public_key=_b64_key(1184),
                                key_id=kid)
    results.append(_report('合法 keyId 原样落库（含大小写）', row.key_id == kid,
                           f'key_id={row.key_id!r}'))

    # 2) 首尾空白：拒绝，**不是 trim 后接受**
    for bad in (' abc', 'abc ', ' abc ', '\tabc'):
        ok, detail = _rejects(C.ERR_INVALID_PARAMETER, R.register_public_key, node,
                              algorithm='SM2', public_key=_hex_pub('ab'), key_id=bad,
                              needle='空白')
        results.append(_report(f'首尾空白被拒而不是被 trim：{bad!r}', ok, detail))

    # 3) 越界字符。"分隔符"单独点名：keyRef 按 / 切段，切错段不报错，只会找不到密钥。
    ok, detail = _rejects(C.ERR_INVALID_PARAMETER, R.register_public_key, node,
                          algorithm='SM2', public_key=_hex_pub('ab'), key_id='a/b',
                          needle='/')
    results.append(_report('含 "/" 被拒（它会把 keyRef 切错段）', ok, detail))
    for bad in ('a b', 'a*b', 'a?b', 'a#b', 'Node@1', '中文'):
        ok, detail = _rejects(C.ERR_INVALID_PARAMETER, R.register_public_key, node,
                              algorithm='SM2', public_key=_hex_pub('ab'), key_id=bad,
                              needle='只允许')
        results.append(_report(f'越界字符被拒：{bad!r}', ok, detail))

    # 4) 长度上限必须与模型列宽（varchar(64)）一致：
    #    超了在严格模式是插入报错、在非严格模式是**静默截断**，后者更糟。
    ok, detail = _rejects(C.ERR_INVALID_PARAMETER, R.register_public_key, node,
                          algorithm='SSCL', public_key=_hex_pub('cd'), key_id='k' * 65,
                          needle='长度')
    results.append(_report('长度 65 被拒', ok, detail))
    row64 = R.register_public_key(node, algorithm='SSCL', public_key=_hex_pub('cd'),
                                  key_id='k' * 64)
    results.append(_report('长度 64 接受（正好等于列宽）', row64.key_id == 'k' * 64))

    # 5) 不给 keyId → 服务端铸一个（形状与前端 key-ref.js 的 mintKeyId 一致）
    minted = R.register_public_key(node, algorithm='FALCON', public_key=_b64_key(897))
    suffix = minted.key_id.rsplit('-', 1)[-1]
    results.append(_report(
        '不给 keyId 时铸一个 {节点}-{算法}-{8位随机}',
        minted.key_id.startswith(f'{node.node_id}-FALCON-')
        and len(suffix) == 8 and all(ch in '0123456789abcdef' for ch in suffix),
        f'key_id={minted.key_id!r}',
    ))

    # 6) 校验必须发生在**幂等分支之前**：重报同一把公钥（最常见的调用形态）
    #    时若先命中"已登记、无操作"，非法 keyId 会被整个吞掉 ——
    #    不落库、不报错，调用方以为服务端记下了它给的 id。
    material = _hex_pub('ab')
    R.register_public_key(node, algorithm='SM2', public_key=material)
    ok, detail = _expect_contract_error(
        C.ERR_INVALID_PARAMETER, R.register_public_key, node,
        algorithm='SM2', public_key=material, key_id='bad/id')
    results.append(_report('重报同一把公钥时非法 keyId 仍被拒', ok, detail))

    sm2_rows = NodeLongTermKey.objects.filter(node=node, algorithm='SM2').count()
    results.append(_report('被拒的登记一律没有落库', sm2_rows == 1, f'count={sm2_rows}'))
    return all(results)


# ---------------------------------------------------------------------------
# 十、接口层：keyId / keyVersion 转发（"新逻辑密钥"与"重报"的分界）
# ---------------------------------------------------------------------------

def test_store_node_public_key_forwards_identity(node):
    """`store_node_public_key` 是节点上报公钥的唯一入口（`POST /node-self/keys/`）。

    这一组断言的是**回传值 = 落库值 = 请求值**：节点拿回传的 keyId 去核对自己
    本地铸的那个，任何一处被"顺手归一"都会让核对失去意义（两边都显示"成功"，
    而 keyRef 已经指向别处）。

    计划 §7 阶段 1 判据④（新逻辑密钥不复用旧 SM2/SSCL 的 `u`）的**服务端一半**
    在第 E 段：新 keyId 必须落成**新行**、旧行保留但不再 ACTIVE。
    "u 不是旧的那个"本身是节点侧属性（`u` 与私钥一起在节点浏览器里重新生成），
    由 `tools/verify-generate-loop.mjs` 在真实浏览器里判定。
    """
    results = []
    svc = NodeService(node.node_id)

    # --- A. 节点上报路径：不给 keyId，服务端铸一个并回传 ---
    raw = os.urandom(1184)
    first = svc.store_node_public_key('KYBER', raw.hex(), security_level='768')
    row = NodeLongTermKey.objects.filter(node=node, algorithm='KYBER').first()
    results.append(_report(
        'KYBER 上报成功，回传的 keyId/版本/状态与落库一致（节点据此核对本地那把）',
        first.get('success') is True and row is not None
        and first.get('key_id') == row.key_id and bool(row.key_id)
        and first.get('key_version') == row.key_version == 1
        and first.get('status') == C.KEY_STATUS_ACTIVE,
        f"回传={first.get('key_id')!r} v{first.get('key_version')} "
        f"落库={getattr(row, 'key_id', None)!r}",
    ))

    # --- B. 显式 keyId/keyVersion 原样转发 ---
    kid = 'Node_1.SM2-x9'
    up = _hex_pub('AB').upper()
    stored = svc.store_node_public_key('SM2', up, key_id=kid, key_version=7)
    row = NodeLongTermKey.objects.filter(node=node, algorithm='SM2').first()
    results.append(_report(
        'keyId / keyVersion 原样转发（请求 = 落库 = 回传）',
        stored.get('success') is True and row is not None
        and row.key_id == kid and row.key_version == 7
        and stored.get('key_id') == kid and stored.get('key_version') == 7,
        f"落库={getattr(row, 'key_id', None)!r} v{getattr(row, 'key_version', None)}",
    ))
    # 同一行里两段文本的口径**刻意相反**：公钥按既有约定归一小写（物化视图列与
    # wrappers 都按小写 hex 取），keyId 一个字符都不动。谁"顺手统一"其中一边，
    # 破坏的都是静默的对齐关系。
    results.append(_report(
        '公钥归一小写、keyId 不归一（两者口径刻意相反）',
        row is not None and row.public_key == up.lower() and row.key_id == kid,
        f'公钥前 10 位={getattr(row, "public_key", "")[:10]!r}',
    ))

    # --- C. 同一 keyId + 同版本 + 同公钥：无操作 ---
    before = NodeLongTermKey.objects.filter(node=node, algorithm='SM2').count()
    again = svc.store_node_public_key('SM2', _hex_pub('ab'), key_id=kid, key_version=7)
    after = NodeLongTermKey.objects.filter(node=node, algorithm='SM2').count()
    results.append(_report(
        '同 keyId 同版本重报是无操作（不产生新版本、不降级自己）',
        again.get('success') is True and after == before and before == 1,
        f'{before} → {after}',
    ))

    # --- D. 同 keyId + 同版本 + **不同公钥**：版本冲突，不是静默覆盖 ---
    conflict = svc.store_node_public_key('SM2', _hex_pub('cd'), key_id=kid,
                                         key_version=7)
    still = NodeLongTermKey.objects.filter(node=node, algorithm='SM2').first()
    results.append(_report(
        '同 keyId 同版本换公钥 → 版本冲突（覆盖会让旧信封永久解不开且无人知道）',
        conflict.get('success') is False
        and conflict.get('code') == C.ERR_KEY_VERSION_MISMATCH
        and still.public_key == _hex_pub('ab'),
        str(conflict.get('message'))[:60],
    ))

    # --- E. 新 keyId：新的一行，旧行保留但让出 ACTIVE（判据④的服务端一半）---
    kid2 = 'Node_1.SM2-y3'
    grew = svc.store_node_public_key('SM2', _hex_pub('ef'), key_id=kid2, key_version=1)
    rows = list(NodeLongTermKey.objects.filter(node=node, algorithm='SM2').order_by('id'))
    old = next((r for r in rows if r.key_id == kid), None)
    new = next((r for r in rows if r.key_id == kid2), None)
    fresh = Node.objects.get(pk=node.pk)
    results.append(_report(
        '新 keyId 落成新的一行（判据④的前提：新逻辑密钥不复用旧身份）',
        grew.get('success') is True and len(rows) == 2 and new is not None,
        f'rows={[r.key_id for r in rows]}',
    ))
    results.append(_report(
        '旧行降级 RETIRED 但**仍在**且保留公钥（历史信封要能追回它用的那一版）',
        old is not None and old.status == C.KEY_STATUS_RETIRED and bool(old.public_key),
        f'status={getattr(old, "status", None)}',
    ))
    results.append(_report(
        '新行 ACTIVE，物化视图列指向新公钥（旧公钥不再被任何读路径当成可用）',
        new is not None and new.status == C.KEY_STATUS_ACTIVE
        and fresh.gm_public_key == _hex_pub('ef'),
    ))
    results.append(_report(
        '数据库层仍只有一行 ACTIVE',
        NodeLongTermKey.objects.filter(node=node, algorithm='SM2',
                                       status=C.KEY_STATUS_ACTIVE).count() == 1,
    ))

    # --- F. 非法 keyVersion：拒绝而不是 int() 兜底，且不落库 ---
    falcon_material = _b64_key(897)
    for bad in (0, -1, '1.9', 'abc', True):
        res = svc.store_node_public_key('FALCON', falcon_material, key_id='KF-1',
                                        key_version=bad)
        results.append(_report(
            f'非法 keyVersion 被拒（不做 int() 兜底）：{bad!r}',
            res.get('success') is False and res.get('code') == C.ERR_INVALID_PARAMETER,
            str(res.get('message'))[:50],
        ))
    results.append(_report(
        '非法版本一律没有落库',
        not NodeLongTermKey.objects.filter(node=node, algorithm='FALCON').exists(),
    ))

    # --- G. keyVersion 的两侧空白与空串：收敛为 1（与 keyId 的"不许空白"刻意相反）---
    spaced = svc.store_node_public_key('FALCON', falcon_material, key_id='KF-2',
                                       key_version=' 1 ')
    blank = svc.store_node_public_key('FALCON', falcon_material, key_id='KF-3',
                                      key_version='')
    results.append(_report(
        "keyVersion 是数值：' 1 ' 与 ''（≡未提供）都收敛为 1",
        spaced.get('success') is True and spaced.get('key_version') == 1
        and blank.get('success') is True and blank.get('key_version') == 1,
        f"' 1 '→{spaced.get('key_version')} ''→{blank.get('key_version')}",
    ))
    return all(results)


# ---------------------------------------------------------------------------
# 十一、更新（rotate）：显式身份、三类拒绝、被拒即不落库（KMS-006）
# ---------------------------------------------------------------------------

def test_rotate_requires_explicit_identity(node):
    """阶段 2 判据①②在存储层的可执行形式。

    每一条拒绝都对应旧实现"取该算法最新一行、版本 +1"的一种**静默**坏结果：
    回收终态被叠上新版本、别的 keyId 被降级（生产版本被换掉而请求成功）、
    服务端算出的版本与节点本地已封存的分叉。所以这里不只断言"被拒"，
    还断言**被拒之后库里没有任何变化** —— 拒绝本身也可能留下半行。
    """
    results = []

    # --- A. 正常更新：同 keyId、版本 +1，旧版本 RETIRED，生产版本切换 ---
    v1_material = _hex_pub('ab')
    v1 = R.register_public_key(node, algorithm='SM2', public_key=v1_material)
    v2_material = _hex_pub('cd')
    v2 = R.rotate_public_key(node, algorithm='SM2', public_key=v2_material,
                             key_id=v1.key_id, key_version=v1.key_version + 1)
    v1.refresh_from_db()
    fresh = Node.objects.get(pk=node.pk)
    results.append(_report(
        '更新保留 key_id、版本递增（判据①）',
        v2.key_id == v1.key_id and v2.key_version == v1.key_version + 1,
        f'{v2.key_id} v{v1.key_version}→v{v2.key_version}',
    ))
    results.append(_report(
        '上一版降级 RETIRED 且让出 active_slot（不占着唯一约束）',
        v1.status == C.KEY_STATUS_RETIRED and v1.active_slot is None,
        f'status={v1.status} slot={v1.active_slot!r}',
    ))
    results.append(_report(
        '旧版本不再被任何读路径当成生产版本（判据②）：新版本是唯一 ACTIVE，'
        '物化视图指向新公钥',
        v2.status == C.KEY_STATUS_ACTIVE and fresh.gm_public_key == v2_material
        and NodeLongTermKey.objects.filter(node=node, algorithm='SM2',
                                           status=C.KEY_STATUS_ACTIVE).count() == 1,
        f'gm_public_key={fresh.gm_public_key[:10]}…',
    ))
    results.append(_report('"要新工作"取到的就是新版本',
                           R.require_usable_key(node, 'SM2').pk == v2.pk))

    # --- B. 版本 = 最新：重试路径。同公钥 → 无操作；异公钥 → 真冲突 ---
    before = NodeLongTermKey.objects.filter(node=node, algorithm='SM2').count()
    same = R.rotate_public_key(node, algorithm='SM2', public_key=v2_material,
                               key_id=v1.key_id, key_version=v2.key_version)
    after = NodeLongTermKey.objects.filter(node=node, algorithm='SM2').count()
    results.append(_report(
        '重试（同版本同公钥）是无操作：返回同一行、不叠版本',
        same.pk == v2.pk and before == after == 2, f'{before} → {after}',
    ))
    ok, detail = _rejects(C.ERR_KEY_VERSION_MISMATCH, R.rotate_public_key, node,
                          algorithm='SM2', public_key=_hex_pub('ef'),
                          key_id=v1.key_id, key_version=v2.key_version,
                          needle='同名覆盖')
    results.append(_report('重试（同版本不同公钥）是冲突，不是静默覆盖', ok, detail))

    # --- C. 版本回退：只增不减 ---
    ok, detail = _rejects(C.ERR_KEY_VERSION_MISMATCH, R.rotate_public_key, node,
                          algorithm='SM2', public_key=_hex_pub('12'),
                          key_id=v1.key_id, key_version=v2.key_version - 1,
                          needle='更旧')
    results.append(_report('版本回退被拒（旧版本号不能重开）', ok, detail))

    # --- D. 跨版：必须逐版递增，否则中间版本在历史里凭空消失 ---
    ok, detail = _rejects(C.ERR_KEY_VERSION_MISMATCH, R.rotate_public_key, node,
                          algorithm='SM2', public_key=_hex_pub('12'),
                          key_id=v1.key_id, key_version=v2.key_version + 2,
                          needle='逐版递增')
    results.append(_report('跨过中间版本被拒（必须逐版递增）', ok, detail))

    # --- E. keyId 未登记：调用方以为登记过、实际没成功 ---
    ok, detail = _rejects(C.ERR_KEY_NOT_FOUND, R.rotate_public_key, node,
                          algorithm='SM2', public_key=_hex_pub('12'),
                          key_id='never-registered', key_version=2,
                          needle='无法更新')
    results.append(_report('未登记的 keyId → KEY_NOT_FOUND（退回"先登记"那一步）',
                           ok, detail))

    # --- F. 身份与版本缺失 / 非法：拒绝，不替调用方推断、不做 int() 兜底 ---
    ok, detail = _rejects(C.ERR_INVALID_PARAMETER, R.rotate_public_key, node,
                          algorithm='SM2', public_key=_hex_pub('12'), key_id='',
                          key_version=2, needle='不再替你推断')
    results.append(_report('缺 keyId 被拒（不推断"要更新哪一把"）', ok, detail))
    for bad in (None, True, 1.9, '二', 0, -1, '1.5'):
        ok, detail = _rejects(C.ERR_INVALID_PARAMETER, R.rotate_public_key, node,
                              algorithm='SM2', public_key=_hex_pub('12'),
                              key_id=v1.key_id, key_version=bad,
                              needle='keyVersion')
        results.append(_report(f'非法版本被拒（不做 int() 兜底）：{bad!r}', ok, detail))

    # --- G. 判据③：以上全部被拒之后，一行都没多、生产版本没被改过 ---
    active = NodeLongTermKey.objects.filter(node=node, algorithm='SM2',
                                            status=C.KEY_STATUS_ACTIVE).first()
    fresh = Node.objects.get(pk=node.pk)
    results.append(_report(
        '全部被拒之后：仍只有两行、生产版本还是 v2、物化视图未动',
        NodeLongTermKey.objects.filter(node=node, algorithm='SM2').count() == 2
        and active is not None and active.pk == v2.pk
        and fresh.gm_public_key == v2_material,
        f'count={NodeLongTermKey.objects.filter(node=node, algorithm="SM2").count()} '
        f'active=v{getattr(active, "key_version", None)}',
    ))
    return all(results)


# ---------------------------------------------------------------------------
# 十二、接口层 rotate=True 与回收终态（`POST /node-self/keys/` 走的这条）
# ---------------------------------------------------------------------------

def test_store_node_public_key_rotate(node):
    """`rotate=True` 的两种失败形态与回收终态，全部断言到库。

    "缺一不可"不是形式要求：节点已经在本地按那个版本号封存了新私钥
    （keyRef 末段就是它），服务端另算一个版本号会让两边对同一个 keyRef
    的记账分叉 —— 分叉不报错，表现是"密钥在、查不到"。
    """
    results = []
    svc = NodeService(node.node_id)

    # --- A. rotate=True 但缺 keyId / 缺 keyVersion：拒绝，且不落库 ---
    material = _hex_pub('ab')
    first = svc.store_node_public_key('SM2', material, device_id='dev-R')
    kid = first.get('key_id')
    results.append(_report('先走登记路径种一行（拿到服务端回传的 keyId）',
                           first.get('success') is True and bool(kid), str(kid)))

    no_id = svc.store_node_public_key('SM2', _hex_pub('cd'), device_id='dev-R',
                                      rotate=True, key_version=2)
    results.append(_report(
        'rotate=True 缺 keyId → 参数错误（不推断更新哪一把）',
        no_id.get('success') is False and no_id.get('code') == C.ERR_INVALID_PARAMETER,
        str(no_id.get('message'))[:60],
    ))
    no_version = svc.store_node_public_key('SM2', _hex_pub('cd'), device_id='dev-R',
                                           rotate=True, key_id=kid)
    results.append(_report(
        'rotate=True 缺 keyVersion → 参数错误（服务端不另算版本号）',
        no_version.get('success') is False
        and no_version.get('code') == C.ERR_INVALID_PARAMETER,
        str(no_version.get('message'))[:60],
    ))
    results.append(_report(
        '两次被拒都没有落库、物化视图未动',
        NodeLongTermKey.objects.filter(node=node, algorithm='SM2').count() == 1
        and Node.objects.get(pk=node.pk).gm_public_key == material,
    ))

    # --- B. rotate=True 正常更新：回传 rotated 与链上要用的整数句柄 ---
    v2 = svc.store_node_public_key('SM2', _hex_pub('cd'), device_id='dev-R',
                                   rotate=True, key_id=kid, key_version=2)
    row = NodeLongTermKey.objects.filter(node=node, algorithm='SM2',
                                         key_version=2).first()
    results.append(_report(
        '更新成功：keyId 不变、版本 2 落库并与回传一致',
        v2.get('success') is True and row is not None
        and v2.get('key_id') == kid and row.key_id == kid
        and v2.get('key_version') == 2 and row.key_version == 2,
        f"回传 v{v2.get('key_version')}",
    ))
    results.append(_report(
        '回传 rotated=True 且 key_pk / public_key_hash 指向刚落的这一行'
        '（接口层据此补 KEY_UPDATED 存证）',
        v2.get('rotated') is True and v2.get('key_pk') == row.pk
        and v2.get('public_key_hash') == row.public_key_hash,
        f"pk={v2.get('key_pk')}",
    ))
    results.append(_report(
        '登记路径的 rotated 是 False（不产生更新存证）',
        first.get('rotated') is False and first.get('key_pk') is not None,
    ))

    # --- B2. 重试（同版本同公钥）是幂等的，且**不能**再报一次"已更新" ---
    # "响应丢失后刷新重试"是设计内的恢复路径，不是异常路径，所以这一支会被真实走到。
    # 若仍报 rotated=True，接口层会补第二条 KEY_UPDATED —— 一次更新在链上留下两条
    # 存证，其中一条什么都没改；页面还会说"已更新为 v2"，而库里根本没变。
    again = svc.store_node_public_key('SM2', _hex_pub('cd'), device_id='dev-R',
                                      rotate=True, key_id=kid, key_version=2)
    results.append(_report(
        '重试（同版本同公钥）不报 rotated、不说"已更新"（链上不补假存证）',
        again.get('success') is True and again.get('rotated') is False
        and again.get('key_pk') == row.pk
        and '未做改动' in str(again.get('message')),
        str(again.get('message'))[:64],
    ))

    # --- C. 回收是终态：不能靠"更新"复活 ---
    R.revoke_public_key(NodeLongTermKey.objects.get(pk=row.pk), '自测：回收终态')
    ok, detail = _rejects(C.ERR_KEY_REVOKED, R.rotate_public_key, node,
                          algorithm='SM2', public_key=_hex_pub('ef'),
                          key_id=kid, key_version=3, needle='已回收')
    results.append(_report('已回收的 keyId 不能更新 → KEY_REVOKED（终态）', ok, detail))
    results.append(_report(
        '回收后物化视图已清空，且没有被"更新"重新填回来',
        Node.objects.get(pk=node.pk).gm_public_key == '',
    ))

    # --- D. 生产槽位归属：该算法在产的是**别的** keyId 时，拒绝更新手里这把 ---
    # 形态就是"换过设备 / 两次更新并发"：按老实现（最新一行 +1）会把在产那把
    # 降级、把手里这把扶正 —— 生产版本被换掉，而请求返回成功。
    old = R.register_public_key(node, algorithm='KYBER', public_key=_b64_key(1184))
    prod_material = _b64_key(1184)
    prod = R.register_public_key(node, algorithm='KYBER', public_key=prod_material)
    ok, detail = _rejects(C.ERR_KEY_VERSION_MISMATCH, R.rotate_public_key, node,
                          algorithm='KYBER', public_key=_b64_key(1184),
                          key_id=old.key_id, key_version=2,
                          needle='不是请求要更新的')
    results.append(_report(
        '更新一把非生产的 keyId → KEY_VERSION_MISMATCH（否则在产那把会被换掉）',
        ok, detail,
    ))
    kyber_active = NodeLongTermKey.objects.filter(
        node=node, algorithm='KYBER', status=C.KEY_STATUS_ACTIVE).first()
    results.append(_report(
        '被拒之后：生产版本仍是原来那把、物化视图未动、没有多出半行',
        kyber_active is not None and kyber_active.pk == prod.pk
        and Node.objects.get(pk=node.pk).kyber_public_key == prod_material
        and NodeLongTermKey.objects.filter(node=node, algorithm='KYBER').count() == 2,
    ))
    return all(results)


def test_register_path_cannot_add_version(node):
    """登记口不能给一把**已存在**的 keyId 加版本 —— 那是 rotate 的语义。

    ---- 这是复核查出来的绕过口 ----

    节点侧 `/node-self/keys/` 自 KMS-005 起就接收 `keyId` 与 `keyVersion`。只要
    **不带** `rotate`，请求就走 `register_public_key`，而它不做回收终态、生产槽位
    归属、逐版递增这三道校验 —— 那三道只在 `rotate_public_key` 里。于是同一个端点
    有两种行为，取决于一个布尔字段，两种静默坏结果都回来了：

      * 已回收的 keyId 可以被"登记"复活 —— 审计里那一行还带着 `revoked_at`，
        业务上却又能用；"回收是终态"只在前端和 rotate 口成立。
      * 在产那把可以被降级、换成调用方指定的另一把，而请求返回"已登记" ——
        调用方看不出自己刚把生产版本换掉了（判据②的失败形态）。

    所以登记口必须**拒绝**，而不是替调用方猜意图：猜成"加版本"就等于放行上面两种，
    猜成"新登记"等于丢弃调用方写的版本号。
    """
    results = []
    svc = NodeService(node.node_id)

    # --- A. 不带 keyId 的正常登记（KMS-005 生成页走的就是这条）必须照常可用 ---
    first = svc.store_node_public_key('SM2', _hex_pub('11'), device_id='dev-N')
    kid = first.get('key_id')
    results.append(_report(
        '不带 keyId 的正常登记仍可用（守卫没有误伤 KMS-005 那条路）',
        first.get('success') is True and bool(kid), str(kid),
    ))

    # --- B. 同 keyId + 同版本 + 同公钥的重报仍是幂等无操作 ---
    # 节点初始化页每次进入都会把四套公钥重报一遍，不幂等的话每进一次页面就
    # 凭空轮换一次密钥。这条是本次守卫**最可能误伤**的地方，必须显式钉住。
    again = svc.store_node_public_key('SM2', _hex_pub('11'), device_id='dev-N',
                                      key_id=kid, key_version=1)
    results.append(_report(
        '同 keyId + 同版本 + 同公钥的重报仍是幂等（初始化页每次进页面都做）',
        again.get('success') is True and again.get('key_id') == kid,
    ))

    # --- C. 带 keyId + 更大版本、但不带 rotate → 想加版本，拒绝并指路 ---
    add_version = svc.store_node_public_key('SM2', _hex_pub('22'), device_id='dev-N',
                                            key_id=kid, key_version=2)
    results.append(_report(
        '登记口给已有 keyId 加版本 → 拒绝，且消息指路 rotate',
        add_version.get('success') is False
        and add_version.get('code') == C.ERR_KEY_VERSION_MISMATCH
        and 'rotate' in str(add_version.get('message')),
        str(add_version.get('message'))[:70],
    ))

    # --- D. 通过登记口换生产版本：必须换不掉 ---
    other = R.register_public_key(node, algorithm='KYBER', public_key=_b64_key(1184))
    prod_material = _b64_key(1184)
    prod = R.register_public_key(node, algorithm='KYBER', public_key=prod_material)
    swap = svc.store_node_public_key('KYBER', _b64_key(1184), device_id='dev-N',
                                     key_id=other.key_id, key_version=2)
    kyber_active = NodeLongTermKey.objects.filter(
        node=node, algorithm='KYBER', status=C.KEY_STATUS_ACTIVE).first()
    results.append(_report(
        '登记口换不掉生产版本：在产那把没被降级、物化列没动、没多出半行',
        swap.get('success') is False and kyber_active is not None
        and kyber_active.pk == prod.pk
        and Node.objects.get(pk=node.pk).kyber_public_key == prod_material
        and NodeLongTermKey.objects.filter(node=node, algorithm='KYBER').count() == 2,
        str(swap.get('message'))[:70],
    ))

    # --- E. 已回收的 keyId 不能靠登记口复活 ---
    R.revoke_public_key(
        NodeLongTermKey.objects.filter(node=node, algorithm='SM2', key_id=kid)
        .order_by('-key_version').first(),
        '自测：回收终态',
    )
    revive = svc.store_node_public_key('SM2', _hex_pub('33'), device_id='dev-N',
                                       key_id=kid, key_version=2)
    results.append(_report(
        '已回收的 keyId 不能靠登记口复活（否则"回收是终态"只在一条路径上成立）',
        revive.get('success') is False
        and Node.objects.get(pk=node.pk).gm_public_key == '',
        str(revive.get('message'))[:70],
    ))

    # --- F. 全部被拒之后：库里没有任何多余的行 ---
    sm2_rows = NodeLongTermKey.objects.filter(node=node, algorithm='SM2').count()
    results.append(_report(
        '全部被拒之后：SM2 仍只有被回收的那一行',
        sm2_rows == 1, f'count={sm2_rows}',
    ))
    return all(results)


def _main():
    print("== KMS-004 长期密钥登记不变量自测 ==\n")

    # 每个用例一个**全新节点**：它们各自都从"这个算法还没登记"起步，
    # 共用节点会让前一个用例留下的行改变后一个用例的判据（例如
    # "该算法只有一行"），而那种失败看起来像被测代码错了。
    tests = [
        ("登记同时写两处（含 Falcon 镜像列）", test_registration_writes_both_places),
        ("重复上报是幂等无操作", test_reregistration_is_noop),
        ("轮换降级旧版本并让出槽位", test_rotation_demotes_previous),
        ("数据库层唯一性真的生效", test_db_enforces_single_active),
        ("回收清空物化视图（含镜像列）", test_revoke_clears_node_columns),
        ("错误码可区分回收/不存在/过期", test_require_usable_key_error_codes),
        ("节点级回收清空全部公钥列", test_revoke_all_for_node),
        ("接口层：归一化与设备一致性", test_store_node_public_key_endpoint),
        ("keyId 不做任何静默更正", test_key_id_is_not_silently_corrected),
        ("接口层：keyId / 版本转发与新逻辑密钥", test_store_node_public_key_forwards_identity),
        ("更新：显式身份、三类拒绝与失败不落库", test_rotate_requires_explicit_identity),
        ("接口层：rotate 与回收终态、生产槽位归属", test_store_node_public_key_rotate),
        ("登记口不能给已有 keyId 加版本", test_register_path_cannot_add_version),
    ]

    failed = []
    created = []
    try:
        for index, (name, fn) in enumerate(tests, start=1):
            node = _make_node(f'{index:02d}')
            created.append(node)
            print(f"-- {name}")
            try:
                if not fn(node):
                    failed.append(name)
            except Exception as exc:  # noqa: BLE001
                import traceback
                traceback.print_exc()
                failed.append(name)
                print(f"  [FAIL] 抛异常: {type(exc).__name__}: {exc}")
            print()
    finally:
        ids = [n.pk for n in created]
        deleted, _ = Node.objects.filter(pk__in=ids).delete()
        print(f"== 清理：已删除 {len(ids)} 个临时节点及其关联行（共 {deleted} 行）==")

    print(f"== 结果：{len(tests) - len(failed)} 组通过 / {len(failed)} 组失败 ==")
    if failed:
        for name in failed:
            print(f"  失败 {name}")
        return 1
    print("长期密钥的登记、版本、状态与物化视图同步均符合计划 §6.1。")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
