# -*- coding: utf-8 -*-
"""KMS-004 长期密钥登记的不变量自测（计划 §6.1 / §9.1）。

判据是什么
=========
计划 §13 要求"不以接口存在为完成"，所以这里断言的是**存储层的不变量**，
不是"函数返回了 success"：

  1. 登记必须**同时**写两处：`NodeLongTermKey` 一行 + `Node.<算法>_public_key`
     物化视图列。只写一处不会报错，只会让"哪一处为准"取决于谁先读 ——
     表现为"有时对"，比稳定错更难查。
     ⚠️ KMS-015 起 FALCON 的**镜像列 `falcon_public_key` 停写**（读路径已切
     到 `falcon_sign_public_key` 优先）；但回收时镜像列的**存量旧值**仍要
     被清掉 —— "停写"与"不清理"是两回事，两条都有断言。
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

KMS-006 追加三组（更新：显式身份、失败不落库、登记口不给已有 keyId 加版本）
=========================================================================
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
  9. **登记口不能给一把已存在的 keyId 加版本** —— 节点侧上报口
     （`POST /node-self/keys/`）与更新口是**同一个端点**，只看 `rotate`
     一个布尔字段。不带它时走的是登记路径，而登记路径不做上面那三道校验。
     于是同一个端点有两种行为，两种静默坏结果都回来了：已回收的 keyId 被
     重新置为 ACTIVE（审计行里还带着 `revoked_at`，业务上却又能用），以及
     在产那把被降级、换成调用方指定的另一把而请求返回"已登记"。
     所以登记口必须**拒绝**并指路 rotate，不替调用方猜意图 —— 猜成"加版本"
     等于放行上面两种，猜成"新登记"等于丢弃调用方写的版本号。
     ⚠️ 这条守卫的第一版把 rotate 自己的**每一次合法更新**也拦下了（更新
     落库正是转调同一个函数，两者在库里的样子一模一样），4 组自测同时失败
     却报"请走 rotate"，看起来像调用方用错了。存储层无法从参数分辨意图，
     只能由调用方声明（`_via_rotate`）；删掉那个标志之前先读
     `node_key_registry.py` 里它上方的说明。

KMS-007 追加一组（回收的影响面：顺序、重试、以及"撤的是哪一个版本"）
====================================================================
 10. 回收不只是一行状态。撤掉一把长期密钥会让**已经发出去的东西变成废纸**：
     用它封过的池项永远解不开、正在用它跑的会话再也谈不下去。`revoke_long_term_key`
     把这三件事编排成一步，本组钉住它的四条性质：

     * **撤的是哪一个版本必须由调用方说了算**。`keyVersion: true` 在 Python 里
       会被 `int()` 收成 1（`bool` 是 `int` 的子类），静默变成"撤 v1" ——
       而那可能正是生产中的那一版，且响应照常成功。`0` / 负数 / 小数 / 字符串
       同样不接受。这类错误的后果与"参数没写对"完全不成比例，所以一律拒绝。
     * **重试必须能把没做完的补上**。三步的顺序是"先撤密钥 → 再池项 → 最后会话"，
       所以中途失败留下的状态是"密钥已撤、影响面没处理完"。这种状态下再调一次，
       函数**刻意不早返回**（那会把半成品永久固化，重试看起来成功、实际什么都没补）。
       本组真的造出这个半成品：直调 `revoke_public_key` 只做第一步，再走一次完整
       回收，断言 `alreadyRevoked=True` **且**池项确实被补上了。
     * **"这次撤的"与"早就撤了"必须可区分**。它决定要不要发 KEY_REVOKED 存证 ——
       重试若无条件上链，同一次回收会在链上留下多条记录，"回收了几次"就没有
       可信答案了。
     * **指定的那一行不存在时报 KEY_NOT_FOUND，且不顺手清场**。报"不存在"而不是
       "已回收"，是因为调用方以为找对了行、实际撤了别的东西，是最坏的一种"成功"。

     会话那一半另要看 `sessionsOk`：会话失效函数**在它自己的原子块里吞异常**，
     失败时返回 `{'success': False}` 而不是抛出。拿 `sessions == 0` 当"没有会话
     受影响"就会把"密钥已回收、会话还活着"读成一切正常。

KMS-013 追加一组（池项消费：能跑之后，真正要钉的是它拒绝什么）
================================================================
 11. `consume_key` 在 KMS-013 之前**从未成功执行过**（裸名常量 → NameError；
     修掉后还有 `select_for_update` 无外层事务 → TransactionManagementError）。
     所以第 17 组先钉"它能跑"，再钉它**拒绝**什么：已消费的行取不到第二次、
     过期的行取不出来（与页面的 `effective_status` 同判）、引用的长期密钥
     登记行被回收时消费口自己拒（`KEY_REVOKED`，不依赖池项被标记 ——
     标记可能被绕过）。另有正对照（换新引用后照常可消费），防"闸门恒拒绝"
     也能让拒绝面全绿。状态机与旧拼写别名的**单一出处**在
     `api_contract.POOL_TRANSITIONS` / `POOL_LEGACY_STATUS_ALIASES`。

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
import json
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
from pqkds.key_pool_service import KeyPoolService  # noqa: E402
from pqkds.key_revocation_service import revoke_long_term_key  # noqa: E402
from pqkds.models import (  # noqa: E402
    Node,
    NodeLongTermKey,
    PreDistributedKey,
    SessionKey,
    SessionKeyInvalidation,
)
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


def _make_node(tag, *, with_user=False):
    """一个临时节点。`with_user=True` 时给一个 `sys_user_id` —— 只有
    需要跑 `create_node_distribution` 的组才要（分发批次行有 NOT NULL 的
    `user_id`，而那是 `Node.sys_user_id` 的镜像；不给值会在落批次行时炸
    IntegrityError，看着像"验收代码写错"，实际只是夹具缺一列）。"""
    node = Node.objects.create(
        node_id=f'TESTKMS004-{tag}-{uuid.uuid4().hex[:6]}',
        name=f'KMS-004 自测节点（{tag}）',
        ip_address='127.0.0.1',
        port=9010,
        status='PENDING_INIT',
        # `sys_user_id` 是**唯一约束**列：给每个自测节点一个随机值而不是固定
        # 值，否则同一次运行里两个节点会撞唯一键（报的是驱动层的 IntegrityError，
        # 看着像被测代码坏了）。随机值取小片区间，够用且不与开发库里的真账号
        # 撞概率可忽略。
        sys_user_id=(uuid.uuid4().int % 2_000_000_000 + 1) if with_user else None,
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
        '★ FALCON：镜像列 falcon_public_key **停写**（KMS-015 —— 只写规范列；'
        '读路径已切到 falcon_sign_public_key 优先）',
        fresh.falcon_public_key == '' and fresh.falcon_sign_public_key == falcon,
        f'镜像列={fresh.falcon_public_key!r} 规范列长度={len(fresh.falcon_sign_public_key)}',
    ))
    # 停写的是**写**，不是清理：回收必须把镜像列也清掉（存量节点上可能还有旧值）。
    # 造一个"旧时代残留的镜像值"，回收 FALCON 后它必须一起被清。
    Node.objects.filter(pk=node.pk).update(falcon_public_key='LEGACY-MIRROR-VALUE')
    active_falcon = NodeLongTermKey.objects.filter(
        node=node, algorithm='FALCON', status=C.KEY_STATUS_ACTIVE).first()
    R.revoke_public_key(active_falcon, '自测：KMS-015 镜像列清理面')
    fresh = Node.objects.get(pk=node.pk)
    results.append(_report(
        '★ FALCON：回收把镜像列的**存量旧值**也清掉（停写 ≠ 不清理）',
        fresh.falcon_public_key == '' and fresh.falcon_sign_public_key == '',
        f'镜像列={fresh.falcon_public_key!r} 规范列={fresh.falcon_sign_public_key!r}',
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
        '不动其他算法列（KMS-015：FALCON 只写规范列，镜像列停写后为空）',
        bool(fresh.falcon_sign_public_key) and fresh.falcon_public_key == '',
        f'sign={len(fresh.falcon_sign_public_key)}B mirror={fresh.falcon_public_key!r}',
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


def test_require_key_version(node):
    """KMS-008：按**显式指定的一版**取密钥，四种拒绝各自可区分。

    ---- 这一组防的是什么 ----
    `require_usable_key` 问的是"这个算法现在能用哪一把"（服务端替调用方挑）；
    本函数问的是"**我指定的这一版**能不能用"。两者差别不是松紧，而是
    "版本由谁给出" —— 计划 §6.1 要求所有请求显式携带版本，不允许服务端
    自己挑"当前最新"。

    要在分发路径上做到这一点，就得先有一次**先于封装发生**的精确查询：
    分发原本读的是物化列（"当前生产公钥"），请求里带了版本也传不进封装，
    于是"用户选了 v1、实际用 v2 封的"，而每一处都成功。

    ⚠️ 本组刻意用一个**只登记了两版**的节点：`KEY_VERSION_MISMATCH`
    那条只有在"行存在、未撤、未过期、但不是生产版本"时才发得出来 ——
    少造一版（比如只登记 v1 就撤它），这条会变成 `KEY_REVOKED`，
    断言看起来照样过，测的却是另一条分支。
    """
    results = []
    try:
        # --- 夹具：同一 keyId 两版（v2 在产，v1 被取代）；另一 keyId 一把回收了的 ---
        # ⚠️ v2 必须走 `rotate_public_key` 而不是再调一次 `register_public_key` ——
        #    KMS-006 起登记口拒绝给已有 keyId 加版本（那会绕过回收终态、生产槽位
        #    与逐版递增三道校验），拿登记口去造夹具会直接撞上那条守卫。
        kid = 'KMS008-K1'
        v1 = R.register_public_key(node, algorithm='KYBER', public_key=_b64_key(1184),
                                   key_id=kid, key_version=1)
        v2 = R.rotate_public_key(node, algorithm='KYBER', public_key=_b64_key(1184),
                                 key_id=kid, key_version=2)
        revoked = R.register_public_key(node, algorithm='SM2', public_key=_hex_pub('ab'),
                                        key_id='KMS008-REVOKED')
        R.revoke_public_key(revoked, 'KMS-008 自测：造一把已回收的')

        results.append(_report(
            '夹具就位：KYBER 同 keyId 的 v1（RETIRED）/ v2（ACTIVE）+ 一把已回收的 SM2',
            NodeLongTermKey.objects.get(pk=v1.pk).status == C.KEY_STATUS_RETIRED
            and NodeLongTermKey.objects.get(pk=v2.pk).status == C.KEY_STATUS_ACTIVE,
            f'v1={NodeLongTermKey.objects.get(pk=v1.pk).status} '
            f'v2={NodeLongTermKey.objects.get(pk=v2.pk).status}',
        ))

        # --- A. 命中：指定的那一版被原样取回 ---------------------------------
        got = R.require_key_version(node, 'KYBER', kid, 2)
        results.append(_report(
            '★ 指定 v2 → 取回的就是 v2 那一行（不是"最新一版"，就是**这一版**）',
            got.pk == v2.pk and got.key_version == 2,
            f'pk={got.pk}（期望 {v2.pk}）version={got.key_version}',
        ))
        # ⚠️ 版本用字符串给也要认：前端表单里的 select 值就是字符串。
        got_str = R.require_key_version(node, 'KYBER', kid, '2')
        results.append(_report(
            '纯数字字符串的版本号（前端表单常态）同样命中同一行',
            got_str.pk == v2.pk,
            f'pk={got_str.pk}',
        ))

        # --- B. 不存在的版本：KEY_NOT_FOUND，且**不回退**到别的版本 ----------
        ok, detail = _expect_contract_error(
            C.ERR_KEY_NOT_FOUND, R.require_key_version, node, 'KYBER', kid, 9,
        )
        results.append(_report(
            '★ 指定一个不存在的版本 → KEY_NOT_FOUND（不回退到 v2）', ok, detail,
        ))
        ok, detail = _expect_contract_error(
            C.ERR_KEY_NOT_FOUND, R.require_key_version, node, 'KYBER', 'no-such-key-id', 1,
        )
        results.append(_report(
            '指定一个不存在的 keyId → KEY_NOT_FOUND（不回退到同算法的别的 keyId）', ok, detail,
        ))

        # --- C. 已回收：KEY_REVOKED（终态，重试永远不会成功）------------------
        ok, detail = _expect_contract_error(
            C.ERR_KEY_REVOKED, R.require_key_version, node, 'SM2', 'KMS008-REVOKED', 1,
        )
        results.append(_report('★ 指定一把已回收的 → KEY_REVOKED（不是笼统的"不存在"）', ok, detail))

        # --- D. 被取代的旧版本：KEY_VERSION_MISMATCH（判据②）------------------
        ok, detail = _expect_contract_error(
            C.ERR_KEY_VERSION_MISMATCH, R.require_key_version, node, 'KYBER', kid, 1,
        )
        results.append(_report(
            '★ 指定一把**已被取代**的旧版本 → KEY_VERSION_MISMATCH —— '
            '这正是判据②「旧版本不能被误当成当前生产版本」',
            ok, detail,
        ))
        # ⚠️ 反过来：解旧信封（for_new_work=False）时同一行**必须放行**。
        #    不加这一条的话，"一律拒绝 RETIRED"也能让上面那条断言变绿 ——
        #    而那会把"旧信封还能解"这条既有能力一起砍掉。
        try:
            unwrap_ok = R.require_key_version(
                node, 'KYBER', kid, 1, for_new_work=False).pk == v1.pk
        except C.ContractError as exc:  # noqa: BLE001
            unwrap_ok = False
            detail = f'被拒：{exc.code} {exc.message}'
        results.append(_report(
            '同一把 RETIRED 在 for_new_work=False（解旧信封）下放行 —— '
            '拒绝的是"开新信封"，不是"这一版不存在"',
            unwrap_ok,
        ))

        # --- E. 参数面：空 keyId 与坏版本号都给 INVALID_PARAMETER ------------
        for bad_kid in ('', '   ', None):
            ok, detail = _rejects(
                C.ERR_INVALID_PARAMETER, R.require_key_version, node, 'KYBER', bad_kid, 1,
                needle='keyId',
            )
            results.append(_report(f'keyId={bad_kid!r} 被拒（必须显式指名）', ok, detail))
        for bad_ver in (True, 0, -1, 1.9, 'abc', None, []):
            ok, detail = _rejects(
                C.ERR_INVALID_PARAMETER, R.require_key_version, node, 'KYBER', kid, bad_ver,
                needle='keyVersion',
            )
            results.append(_report(f'keyVersion={bad_ver!r} 被拒（不猜、不 int() 兜底）', ok, detail))

        # --- F. 算法白名单：Falcon 不是保护算法 ------------------------------
        ok, detail = _expect_contract_error(
            C.ERR_KEY_NOT_FOUND, R.require_key_version, node, 'FALCON', kid, 1,
        )
        results.append(_report(
            '拿 FALCON 去查同一 keyId → 查不到（算法进查询，不会串到别的算法的行）',
            ok, detail,
        ))

        # 以上全部被拒之后，两行都一动没动。
        still_v1 = NodeLongTermKey.objects.get(pk=v1.pk)
        still_v2 = NodeLongTermKey.objects.get(pk=v2.pk)
        results.append(_report(
            '全部被拒之后两行都没被改动（查询不该有副作用）',
            still_v1.status == C.KEY_STATUS_RETIRED and still_v2.status == C.KEY_STATUS_ACTIVE,
            f'v1={still_v1.status} v2={still_v2.status}',
        ))
    finally:
        # ⚠️ 本组没有额外建的节点要清理：`_main` 建的那个节点会被它自己删掉，
        #    长期密钥行靠外键 CASCADE 一并消失。保留 `finally` 是为了与
        #    其余各组同形，将来若要加对端节点，落点已经在了。
        pass
    return all(results)


def test_verify_node_distribution_signature(node):
    """KMS-010：服务端**验签** —— 验不过必须拒收（阶段 3 出口检查的后半句）。

    ---- 这一组防的是什么 ----
    KMS-009 把 SM4 的生成、封装、签名都搬到了发送节点，服务端只"核形状、
    算摘要、落库"；本组落地最后一步：**用发送方登记的 Falcon 公钥验签**，
    验不过一律拒（`SIGNATURE_INVALID`）。阶段 3 出口检查「Falcon 缺失时不能
    发送」在此之前只能靠"没带签名"表达，现在补上了"签了但验不过"。

    三条断言各自防一种"看起来已经验过了"的假象：

      * **改一个被签字段**（接收方版本 1→3）→ 必须拒，且**一条池行都不留**。
        不验签的实现会让它照常登记 —— 库里躺着一封"接收方以为是 v1、实际
        按 v3 声明"的信，而每一处都成功。
      * **用别的节点的私钥签、信封里声称是本节点发的** → 必须拒。这条钉住
        "签名绑住了发送者身份"：只检查"签名与公钥自洽"会放过它。
      * **正常路径必须真的通** → 回 `signature_verified=True` 且库内信封与
        请求逐字相同。只测拒绝面的话，"验签永远返回 False"也能全绿 ——
        而这会把所有正当分发全拒掉。

    ⚠️ 本组用**真 Falcon / 真 Kyber**，不是假材料：`FalconCrypto`（DLL）、
       `KyberCrypto`（DLL）、`wrap_with_public_key`、`node_canonical_payload`
       全是生产那条路径上的实现。假公钥在这里会**必然失败**（长度校验都过不去），
       而失败会被读成"验签实现了"。
    """
    from pqkds.crypto_utils import FalconCrypto, KyberCrypto
    from pqkds.distribution_service import create_node_distribution
    from pqkds.envelope_signature import ciphertext_digest, node_canonical_payload
    from pqkds.models import DistributionBatch
    from pqkds.sm4_crypto import SM4Crypto
    from pqkds.wrappers import wrap_with_public_key

    results = []
    receiver = _make_node('16-receiver')
    other = _make_node('16-other')
    try:
        # --- 夹具：接收方真 Kyber-768 公钥 + 本节点真 Falcon 公钥（登记表 hex 口径）---
        k_kyber = KyberCrypto(768)
        rec_pk, rec_sk = k_kyber.generate_keypair()
        rec_key = R.register_public_key(
            receiver, algorithm='KYBER', public_key=base64.b64encode(rec_pk).decode(),
            key_id='KMS010-REC', key_version=1,
        )

        f_sender = FalconCrypto(512)
        fpk_v1, fsk_v1 = f_sender.generate_keypair()
        # ⚠️ 登记表里的 Falcon 公钥是 **hex**（KMS-009 实测踩中）——这里按生产
        #    路径的口径登记，让 `_decode_registry_key_material` 的"按形状认编码"
        #    真的被走一遍（登记成 base64 会让验签恒失败且不报编码错）。
        falcon_v1 = R.register_public_key(
            node, algorithm='FALCON', public_key=fpk_v1.hex(),
            key_id='KMS010-SIGN', key_version=1,
        )
        # 另一个节点的 Falcon 私钥：用于"冒充发送方"的反例。
        _, fsk_other = FalconCrypto(512).generate_keypair()

        def make_request(*, signer_sk, falcon_key_id='KMS010-SIGN', falcon_key_version=1,
                         sender_node_id=None, tamper=None, signer_ref=None):
            """造一份**真签名**的分发请求。

            签名口径与生产完全一致：`wrap_with_public_key` 产出信封 →
            补齐被签字段 → `node_canonical_payload` 重建字节串 → DLL 签名。
            """
            payload_key = os.urandom(16)
            envelope, key_hash = wrap_with_public_key(
                payload_key, base64.b64encode(rec_pk).decode(), 'kyber_kem',
            )
            batch_id = timezone.now().strftime('dist-%Y%m%d%H%M%S-') + uuid.uuid4().hex[:8]
            expires_at = timezone.now() + timedelta(hours=2)
            envelope.update({
                'batch_id': batch_id,
                'sender_node_id': sender_node_id or node.node_id,
                'receiver_node_id': receiver.node_id,
                'recipient_key_id': rec_key.key_id,
                'recipient_key_version': 1,
                'key_hash': key_hash,
                # 摘要算的是**内层密文**（与 `_canonical_inner_json` 同一口径），
                # 与生产端 `envelope-signing.js` 的做法逐字节一致。
                #
                # ⚠️ 这里直接对**信封里已有的那几项**取子集再序列化（而不是另写
                #    一份字段清单）：做法与生产端 `canonicalJson(inner)` 一致 ——
                #    另写清单会在信封换形状时留下一条永远对不上的摘要，
                #    而现象只是"摘要不符"。
                'ciphertext_digest': ciphertext_digest(json.dumps(
                    {
                        'kem_ciphertext': envelope['kem_ciphertext'],
                        'encrypted_key': envelope['encrypted_key'],
                        'nonce': envelope['nonce'],
                        'tag': envelope['tag'],
                        'payload_algorithm': envelope['payload_algorithm'],
                        'wrapping_algorithm': envelope['wrapping_algorithm'],
                    },
                    ensure_ascii=False, sort_keys=True, separators=(',', ':'),
                )),
                'expires_at': expires_at.isoformat(),
            })
            signature = FalconCrypto(512).sign(node_canonical_payload(envelope), signer_sk)
            if tamper:
                # 篡改发生在**签名之后**：改的是"已经被签过的那份内容"，
                # 这才是伪造的样子。先改后签等于签了一份新内容，验得过。
                tamper(envelope)
            return {
                'envelope': envelope,
                'signature': signature,
                'batch_id': batch_id,
                'key_hash': key_hash,
                'args': dict(
                    protection_algorithm='KYBER',
                    recipient_key_id=rec_key.key_id,
                    recipient_key_version=1,
                    batch_id=batch_id,
                    expires_at=envelope['expires_at'],
                    envelope=envelope,
                    signature=base64.b64encode(signature).decode('ascii'),
                    falcon_key_id=signer_ref[0] if signer_ref else falcon_key_id,
                    falcon_key_version=signer_ref[1] if signer_ref else falcon_key_version,
                    key_hash=key_hash,
                ),
            }

        def pool_rows(batch_id):
            return PreDistributedKey.objects.filter(pool_id=batch_id).count()

        def call(req):
            return create_node_distribution(node, receiver, **req['args'])

        # --- A. 正常路径：验得过才登记，且如实回签名者版本 --------------------
        req_ok = make_request(signer_sk=fsk_v1)
        out_ok = call(req_ok)
        stored = json.loads(
            PreDistributedKey.objects.get(pool_id=req_ok['batch_id']).encrypted_key_data
        )
        results.append(_report(
            '★ 真签名 → 登记成功，且回 signature_verified=True（只有验过才可能回）',
            out_ok.get('signature_verified') is True
            and out_ok['signing_key'].pk == falcon_v1.pk
            and out_ok['signing_key'].key_version == 1,
            f"verified={out_ok.get('signature_verified')} signer={out_ok['signing_key'].key_id}"
            f" v{out_ok['signing_key'].key_version}",
        ))
        results.append(_report(
            '★ 库内信封就是被签的那一份：签名与全部被签字段逐字相同',
            stored.get('signature') == req_ok['args']['signature']
            and all(stored.get(k) == req_ok['envelope'].get(k)
                    for k in ('batch_id', 'sender_node_id', 'receiver_node_id',
                              'recipient_key_id', 'recipient_key_version',
                              'key_hash', 'ciphertext_digest', 'expires_at')),
            f"signature 长度={len(str(stored.get('signature')))}",
        ))
        # 落库的信封**真能解开**（用接收方私钥按生产口径解）—— 顺带证明这一组
        # 夹具不是"看起来像信封"的假数据。
        ss = k_kyber.decrypt(base64.b64decode(stored['kem_ciphertext']), rec_sk)
        from pqkds.sm4_crypto import PayloadCipher  # noqa: E402  局部导入：只有本组用
        kek = PayloadCipher.kek_from_shared_secret('sm4', ss)
        opened = SM4Crypto.decrypt(
            base64.b64decode(stored['encrypted_key']), kek,
            base64.b64decode(stored['nonce']) + base64.b64decode(stored['tag']),
        )
        results.append(_report(
            '库内信封能被接收方私钥解开（16 字节 SM4）—— 验签通过的那一封是真信封',
            isinstance(opened, bytes) and len(opened) == 16,
            f'解出 {len(opened) if opened else 0} 字节',
        ))

        # --- B. 摘要不自洽：报 ENVELOPE_TAMPERED 而不是 SIGNATURE_INVALID -------
        # 顺序判据：序列化漂移（我们改了规范）与伪造（安全事件）必须分开报。
        req_digest = make_request(
            signer_sk=fsk_v1,
            tamper=lambda env: env.update({'ciphertext_digest': 'f' * 64}),
        )
        ok, detail = _expect_contract_error(
            C.ERR_ENVELOPE_TAMPERED, call, req_digest,
        )
        results.append(_report(
            '★ 摘要被改 → ENVELOPE_TAMPERED（**先于**验签报出：序列化漂移不该伪装成伪造）',
            ok, detail,
        ))

        # --- C. 篡改**被签字段** → SIGNATURE_INVALID 且一条池行都不留 ----------
        req_tampered = make_request(
            signer_sk=fsk_v1,
            tamper=lambda env: env.update({'recipient_key_version': 3}),
        )
        ok, detail = _expect_contract_error(C.ERR_SIGNATURE_INVALID, call, req_tampered)
        results.append(_report(
            '★ 签名之后改一个被签字段（接收方版本 1→3）→ SIGNATURE_INVALID',
            ok, detail,
        ))
        results.append(_report(
            '★ 被拒的那一批**一条池行、一条批次行都没留下**（拒收不是"先落库后报错"）',
            pool_rows(req_tampered['batch_id']) == 0
            and DistributionBatch.objects.filter(batch_id=req_tampered['batch_id']).count() == 0,
            f"池行={pool_rows(req_tampered['batch_id'])} "
            f"批次行={DistributionBatch.objects.filter(batch_id=req_tampered['batch_id']).count()}",
        ))

        # --- D. 别的节点私钥签、声称是本节点发的 → 必须拒 ----------------------
        # 信封内容与"本节点身份"自洽（sender_node_id 写的是本节点），签名却不
        # 出自本节点那把私钥 —— 只检查"签名与某个公钥自洽"的实现会放过它。
        req_impostor = make_request(signer_sk=fsk_other)
        ok, detail = _expect_contract_error(C.ERR_SIGNATURE_INVALID, call, req_impostor)
        results.append(_report(
            '★ 用别的节点私钥签、信封声称是本节点发的 → SIGNATURE_INVALID（签名绑住发送者身份）',
            ok, detail,
        ))

        # --- E. 缺签名者版本：显式携带是契约（计划 §6.1）-----------------------
        req_missing = make_request(signer_sk=fsk_v1, falcon_key_id='', falcon_key_version=None)
        ok, detail = _rejects(C.ERR_INVALID_PARAMETER, call, req_missing, needle='FALCON')
        results.append(_report(
            '缺 falconKeyId / falconKeyVersion → INVALID_PARAMETER（不替调用方挑"当前生产版"）',
            ok, detail,
        ))

        # --- F. 轮换后：拿旧私钥签、声称新版本 → 验不过（版本真的进了查询）-----
        fpk_v2, fsk_v2 = FalconCrypto(512).generate_keypair()
        R.rotate_public_key(
            node, algorithm='FALCON', public_key=fpk_v2.hex(),
            key_id='KMS010-SIGN', key_version=2,
        )
        req_old_sign = make_request(signer_sk=fsk_v1, falcon_key_version=2)
        ok, detail = _expect_contract_error(C.ERR_SIGNATURE_INVALID, call, req_old_sign)
        results.append(_report(
            '★ v2 在产时：拿 v1 私钥签、声称 v2 → 验不过（版本真的进了验签查询，不是拿"最新一把"糊上）',
            ok, detail,
        ))
        # 用 v1 私钥签、**如实声称 v1** → 现在是 KEY_VERSION_MISMATCH（v1 已 RETIRED），
        # 而不是"验签失败"。这条把"版本转换"与"签名不对"分开 —— 两者处置不同。
        req_retired = make_request(signer_sk=fsk_v1, falcon_key_version=1)
        ok, detail = _expect_contract_error(C.ERR_KEY_VERSION_MISMATCH, call, req_retired)
        results.append(_report(
            '拿已被取代的 v1 发新信 → KEY_VERSION_MISMATCH（不是 SIGNATURE_INVALID：该换版本，不是怀疑伪造）',
            ok, detail,
        ))

        # --- G. 轮换后正常路径仍然通，且验的是 v2 公钥 --------------------------
        req_v2 = make_request(signer_sk=fsk_v2, falcon_key_version=2)
        out_v2 = call(req_v2)
        results.append(_report(
            '★ v2 私钥签 + 声称 v2 → 通过（换一把之后判据在两个版本上各成立一次）',
            out_v2.get('signature_verified') is True
            and out_v2['signing_key'].key_version == 2,
            f"verified={out_v2.get('signature_verified')} v={out_v2['signing_key'].key_version}",
        ))

        # --- H. 已回收的签名版本 → KEY_REVOKED（回收禁止新签名）----------------
        R.revoke_public_key(
            NodeLongTermKey.objects.get(pk=falcon_v1.pk),
            'KMS-010 自测：回收终态',
        )
        R.revoke_public_key(R.require_key_version(node, 'FALCON', 'KMS010-SIGN', 2),
                            'KMS-010 自测：撤掉在产的 v2')
        req_revoked = make_request(signer_sk=fsk_v2, falcon_key_version=2)
        ok, detail = _expect_contract_error(C.ERR_KEY_REVOKED, call, req_revoked)
        results.append(_report(
            '★ 已回收的签名版本 → KEY_REVOKED（同一个请求体在撤之前是通过的）',
            ok, detail,
        ))
        results.append(_report(
            '全部被拒之后：本组只留下成功的那两批（A 与 G），没有半行',
            pool_rows(req_ok['batch_id']) == 1
            and pool_rows(req_v2['batch_id']) == 1
            and all(pool_rows(r['batch_id']) == 0 for r in (
                req_digest, req_impostor, req_missing, req_old_sign,
                req_retired, req_revoked,
            )),
            f"A={pool_rows(req_ok['batch_id'])} G={pool_rows(req_v2['batch_id'])}",
        ))
    finally:
        other.delete()
        receiver.delete()
    return all(results)


def _make_pool_item(node, tag, status='READY', algorithm='kyber_kem',
                    long_term_key_id=None, long_term_key_version=None):
    """一条预分配池项。字段取**最小可用集** —— 本组只关心它的 status 与长期密钥引用。"""
    return PreDistributedKey.objects.create(
        pool_id=f'TESTKMS007-{tag}-{uuid.uuid4().hex[:8]}',
        key_index=0,
        node1=node,
        algorithm=algorithm,
        encrypted_key_data='{}',
        key_hash='0' * 64,
        status=status,
        expires_at=timezone.now() + timedelta(days=1),
        long_term_key_id=long_term_key_id,
        long_term_key_version=long_term_key_version,
    )


def _make_session(a, b, tag):
    """一条**活跃**会话（`established` 是失效服务会扫的三个状态之一）。"""
    return SessionKey.objects.create(
        session_id=f'TESTKMS007-{tag}-{uuid.uuid4().hex[:8]}',
        node1=a, node2=b,
        encrypted_session_key='{}',
        key_exchange_data='{}',
        status='established',
        expires_at=timezone.now() + timedelta(hours=1),
    )


def test_revoke_service_impact(node):
    """KMS-007：回收的三个影响面、重试语义，以及"撤的是哪一个版本"。

    ---- 为什么要造一个"半成品"状态 ----
    本组最要紧的一条是 D 段。三步顺序（撤密钥 → 池项 → 会话）决定了中途失败
    会留下"密钥已撤、影响面没做完"的状态，而函数**刻意不在已是 REVOKED 时
    早返回**。这条设计只有真的造出那个状态才验得出来：直调 `revoke_public_key`
    只做第一步，池项仍是 READY，再走一次完整回收，看它有没有把剩下的补上。
    不造这个状态的话，"重试幂等"与"重试把活干了"在返回值上长得一模一样。
    """
    results = []
    other = _make_node('10-peer')
    try:
        # --- A. 撤的是哪一个版本，必须由调用方说了算 -------------------------
        # 先登记一把真密钥，好让"被误撤"有一个可观测的后果。
        key = R.register_public_key(node, algorithm='KYBER', public_key=_b64_key(1184))

        # ⚠️ `True` 排在最前：Python 里 `isinstance(True, int)` 为真、`int(True)`
        #    得到 1，一个写错的 `keyVersion: true` 会静默变成"撤 v1"。这里先把这个
        #    危险本身钉住——不然下面那条拒绝看起来只是"严格一点更好"。
        results.append(_report(
            'int(True) == 1 —— 这正是 keyVersion: true 会静默撤掉 v1 的原因',
            int(True) == 1 and isinstance(True, int),
        ))

        for bad in (True, False, 0, -1, 1.9, 'abc', '', '   ', None, []):
            ok, detail = _rejects(
                C.ERR_INVALID_PARAMETER, revoke_long_term_key,
                node, 'KYBER', key.key_id, bad, needle='keyVersion',
            )
            results.append(_report(f'keyVersion={bad!r} 被拒（不猜、不 int() 兜底）', ok, detail))

        still = NodeLongTermKey.objects.get(pk=key.pk)
        results.append(_report(
            '★ 以上全部被拒之后，那一行**一动没动**（尤其没有被静默撤成 v1）',
            still.status != C.KEY_STATUS_REVOKED,
            f'status={still.status} revoked_at={still.revoked_at}',
        ))
        results.append(_report(
            '物化列也没被这些失败请求动过',
            Node.objects.get(pk=node.pk).kyber_public_key == still.public_key,
        ))

        # --- B. 指名的那一行不存在：报 KEY_NOT_FOUND，且不顺手清场 -----------
        missing_ok, missing_detail = _expect_contract_error(
            C.ERR_KEY_NOT_FOUND, revoke_long_term_key,
            node, 'KYBER', 'no-such-key-id', 1,
        )
        results.append(_report('撤一个不存在的 keyId → KEY_NOT_FOUND', missing_ok, missing_detail))
        results.append(_report(
            '报"不存在"之后，同节点**别的密钥**没被牵连（不做整节点清场）',
            NodeLongTermKey.objects.filter(
                node=node, algorithm='KYBER', status=C.KEY_STATUS_ACTIVE).count() == 1,
        ))

        # --- C. 正常路径：三个影响面一起发生 ---------------------------------
        item = _make_pool_item(node, 'c', long_term_key_id=key.key_id, long_term_key_version=1)
        session = _make_session(node, other, 'c')

        result = revoke_long_term_key(
            node, 'KYBER', key.key_id, key.key_version, reason='自测：正常回收',
        )
        revoked, impact = result['revoked'], result['impact']

        results.append(_report(
            '密钥本身转入 REVOKED 终态，并记下原因',
            revoked['status'] == C.KEY_STATUS_REVOKED
            and revoked['revokedReason'] == '自测：正常回收'
            and bool(revoked['revokedAt']),
            f"status={revoked['status']} reason={revoked['revokedReason']}",
        ))
        results.append(_report(
            '★ 回收同时清空了物化列（不清的话既有读路径会继续拿它当可用，且失败是静默的）',
            Node.objects.get(pk=node.pk).kyber_public_key in ('', None),
            f"读回 {Node.objects.get(pk=node.pk).kyber_public_key!r}",
        ))
        results.append(_report(
            'wasActive=True（撤的正是生产版本）/ alreadyRevoked=False（本次才撤的）',
            revoked['wasActive'] is True and revoked['alreadyRevoked'] is False,
            f"wasActive={revoked['wasActive']} alreadyRevoked={revoked['alreadyRevoked']}",
        ))
        item.refresh_from_db()
        results.append(_report(
            '★ 池项被连带失效（否则它会一直显示 READY，等某次会话取用后在节点上解封失败）',
            item.status == 'REVOKED', f'status={item.status}',
        ))
        session.refresh_from_db()
        results.append(_report(
            '★ 会话被连带撤销',
            session.status == 'revoked', f'status={session.status}',
        ))
        invalidation = SessionKeyInvalidation.objects.filter(session=session).first()
        results.append(_report(
            '失效记录写的是**已声明**的 manual_revocation，不是新造的第三个值',
            invalidation is not None and invalidation.reason == 'manual_revocation',
            f'reason={getattr(invalidation, "reason", None)}',
        ))
        results.append(_report(
            '影响面如实回报：poolItems=1、sessions=1、sessionsOk=True',
            impact['poolItems'] == 1 and impact['sessions'] == 1 and impact['sessionsOk'] is True,
            f"poolItems={impact['poolItems']} sessions={impact['sessions']} ok={impact['sessionsOk']}",
        ))

        # --- D. ★ 半成品状态：重试必须把没做完的补上 -------------------------
        # 直调 `revoke_public_key` **只做第一步**，池项留在 READY —— 这就是
        # "密钥已撤、影响面没处理完"在库里的样子。
        key2 = R.register_public_key(node, algorithm='KYBER', public_key=_b64_key(1184))
        item2 = _make_pool_item(node, 'd', long_term_key_id=key2.key_id, long_term_key_version=1)
        R.revoke_public_key(key2, '自测：只做第一步，人为造出半成品')
        key2.refresh_from_db()
        item2.refresh_from_db()
        results.append(_report(
            '半成品状态确实造出来了：密钥已撤，池项还是 READY',
            key2.status == C.KEY_STATUS_REVOKED and item2.status == 'READY',
            f'key={key2.status} item={item2.status}',
        ))

        retry = revoke_long_term_key(node, 'KYBER', key2.key_id, key2.key_version)
        item2.refresh_from_db()
        results.append(_report(
            '重试如实报告 alreadyRevoked=True（"早就撤了"与"这次撤的"可区分）',
            retry['revoked']['alreadyRevoked'] is True,
            f"alreadyRevoked={retry['revoked']['alreadyRevoked']}",
        ))
        results.append(_report(
            '★ 重试**没有**早返回：上一轮没做完的池项被补上了',
            retry['impact']['poolItems'] >= 1 and item2.status == 'REVOKED',
            f"poolItems={retry['impact']['poolItems']} item={item2.status}",
        ))

        # --- E. 撤一个**非生产**版本：不能误伤正在用的那一把 -----------------
        # 登记两把新的（后一把接管生产槽位），再把前一把撤掉 —— 它已是 RETIRED。
        stale = R.register_public_key(node, algorithm='KYBER', public_key=_b64_key(1184))
        prod = R.register_public_key(node, algorithm='KYBER', public_key=_b64_key(1184))
        stale_result = revoke_long_term_key(node, 'KYBER', stale.key_id, stale.key_version)
        results.append(_report(
            'wasActive=False —— 撤一把早就被取代的旧版本是清账，不是停服级事件',
            stale_result['revoked']['wasActive'] is False,
            f"wasActive={stale_result['revoked']['wasActive']}",
        ))
        results.append(_report(
            '★ 撤旧版本**没有**清空物化列：生产中的那一把仍可正常使用',
            Node.objects.get(pk=node.pk).kyber_public_key == prod.public_key,
        ))
        results.append(_report(
            '生产槽位仍属于在生产的那一把',
            NodeLongTermKey.objects.filter(
                node=node, algorithm='KYBER', status=C.KEY_STATUS_ACTIVE).first().pk == prod.pk,
        ))

        # --- F. ★ KMS-007 D3：失效必须精确到"哪一把密钥、哪个算法" ----------
        # 改前 `revoke_pool_items_for_key` **只按 node_id 匹配**：撤一个算法的
        # 一把密钥，会把该节点**全部** READY/RESERVED 池项一次清空（包括用其它
        # 仍然有效的算法封的），而日志逐字印着 key_id/version —— 读日志的人会
        # 以为它是精确失效的。这一节就是钉住那个缺陷。
        results.append(_report(
            '算法名 → 库里拼写的家族展开：认识的非空、不认识的为空元组',
            C.wrapping_algorithms_for('KYBER') == ('kyber_kem', 'KYBER')
            and C.wrapping_algorithms_for('falcon_lattice') == ('falcon_lattice', 'FALCON')
            and C.wrapping_algorithms_for('nonsense') == ()
            and C.wrapping_algorithms_for('') == (),
            f"KYBER={C.wrapping_algorithms_for('KYBER')} "
            f"认不出={C.wrapping_algorithms_for('nonsense')!r}",
        ))

        fkey = R.register_public_key(node, algorithm='KYBER', public_key=_b64_key(1184))
        # 三条历史行（**没有**长期密钥引用 —— 迁移 0017 之前创建的池项就是这样），
        # 算法各不相同。节点相同，算法是唯一的收窄条件，所以这一节能分辨
        # "按算法家族匹配"与"按节点全清"。
        hist_kyber = _make_pool_item(node, 'f-kyber')
        hist_falcon = _make_pool_item(node, 'f-falcon', algorithm='falcon_lattice')
        hist_sm2 = _make_pool_item(node, 'f-sm2', algorithm='gm_sm2')

        # F1. 认不出的算法名：**不退化**。宁可漏，也不能按节点全清 ——
        #     那正是上面那个缺陷的翻版，而且是静默的（日志里另有一条 error）。
        unknown_n = KeyPoolService.revoke_pool_items_for_key(
            node.node_id, fkey.key_id, version=1, algorithm='nonsense',
        )
        hist_kyber.refresh_from_db()
        results.append(_report(
            '★ 算法名认不出时不做退化匹配：历史行一条都没动',
            unknown_n == 0 and hist_kyber.status == 'READY',
            f'revoked={unknown_n} kyber历史行={hist_kyber.status}',
        ))

        # F2. 正常撤销：只牵连**同算法家族**的历史行。
        f_result = revoke_long_term_key(node, 'KYBER', fkey.key_id, fkey.key_version)
        for item in (hist_kyber, hist_falcon, hist_sm2):
            item.refresh_from_db()
        results.append(_report(
            '★ 同算法的历史行（无长期密钥引用）被退化匹配命中',
            hist_kyber.status == 'REVOKED', f'status={hist_kyber.status}',
        ))
        results.append(_report(
            '★ 另一算法的历史行**必须还活着** —— 改前按 node 全清，它们会一起被撤',
            hist_falcon.status == 'READY' and hist_sm2.status == 'READY',
            f'falcon={hist_falcon.status} sm2={hist_sm2.status}',
        ))
        results.append(_report(
            '影响面只报了真正改动的那一条',
            f_result['impact']['poolItems'] == 1,
            f"poolItems={f_result['impact']['poolItems']}",
        ))
    finally:
        # ⚠️ `_main` 只清理它自己建的那个节点。这里为了造会话多建了一个对端节点，
        #    必须自己删掉 —— 漏删不会让本组失败，只会让开发库里慢慢积起
        #    TESTKMS004-10-peer-* 这种谁也不知道哪来的行。
        other.delete()
    return all(results)


def test_pool_consume_semantics(node):
    """KMS-013：池项消费 —— 断口复现、状态机、终态、过期与引用失效的消费口。

    ---- 为什么这组不只测"消费成功" ----
    `consume_key` 在 KMS-013 之前**从未成功执行过**（裸名 NameError +
    `select_for_update` 无外层事务，roadmap §4 有复现记录），所以"它现在
    能跑"本身就要有断言；而"能跑"之后，真正要钉的是**它拒绝什么**：

      * 已消费的行取不到第二次（一次性）；
      * 过期的行取不出来 —— 页面（`effective_status`）与消费必须对"过期"
        给出**同一个**答案，不然页面说可用、消费说没有，两边都不报错；
      * 引用的长期密钥登记行被回收 → 消费口必须自己拒（`KEY_REVOKED`）——
        这是阶段 5 出口检查「密钥版本失效会阻止消费」在**消费口**的那一半；
        另一半（回收把池项连带标 REVOKED）由第 14 组覆盖。

    ⚠️ 本组刻意**不用** `_make_pool_item`：那个夹具只设 node1（node2 为空），
       而 `consume_key` 按**节点对**双向匹配，node2 为空的行永远不会被选中 ——
       用它做夹具的话所有消费都返回"没有可用"，看起来像消费坏了。
    """
    results = []
    other = _make_node('13-peer')
    tag = uuid.uuid4().hex[:8]

    def pair_item(name, **kw):
        return PreDistributedKey.objects.create(
            pool_id=f'TESTKMS013-{name}-{tag}',
            key_index=0,
            node1=node,
            node2=other,
            algorithm=kw.pop('algorithm', 'kyber_kem'),
            encrypted_key_data='{}',
            key_hash='0' * 64,
            status=kw.pop('status', 'READY'),
            expires_at=kw.pop('expires_at', timezone.now() + timedelta(days=1)),
            **kw,
        )

    try:
        # --- A. 断口复现 ---------------------------------------------------
        # 断口 1：常量是**类属性**，静态方法里的裸名解析不到（NameError）。
        # 这条断言本身不执行消费，但它把"名字从哪来"钉在类上。
        results.append(_report(
            '★ POOL_STATUS_READY_VALUES 挂在类上且含旧拼写（裸名曾经解析不到 —— 断口 1）',
            KeyPoolService.POOL_STATUS_READY_VALUES == (C.POOL_READY, 'unused'),
            f'{KeyPoolService.POOL_STATUS_READY_VALUES}',
        ))
        # 断口 2：事务边界。此时节点对没有任何池项 —— 修好前这里抛
        # TransactionManagementError / NameError，修好后走完事务并如实返回失败。
        empty = KeyPoolService.consume_key(node.node_id, other.node_id)
        results.append(_report(
            '★ 直调不再抛 NameError / TransactionManagementError，如实回 POOL_ITEM_UNAVAILABLE',
            empty.get('success') is False and empty.get('code') == C.ERR_POOL_ITEM_UNAVAILABLE,
            f"code={empty.get('code')} message={str(empty.get('message'))[:60]}",
        ))

        # --- B. 状态机表（单一出处：api_contract） --------------------------
        results.append(_report(
            '状态机：READY → CONSUMED 合法；READY → RESERVED **没有边**（保留值）',
            C.pool_transition_allowed(C.POOL_READY, C.POOL_CONSUMED)
            and not C.pool_transition_allowed(C.POOL_READY, C.POOL_RESERVED)
            and C.POOL_RESERVED in C.POOL_TRANSITIONS
            and C.POOL_TRANSITIONS[C.POOL_RESERVED]
            == frozenset({C.POOL_CONSUMED, C.POOL_REVOKED, C.POOL_EXPIRED}),
            f'READY→CONSUMED={C.pool_transition_allowed(C.POOL_READY, C.POOL_CONSUMED)} '
            f'READY→RESERVED={C.pool_transition_allowed(C.POOL_READY, C.POOL_RESERVED)}',
        ))
        results.append(_report(
            '旧拼写经归一后与规范值同判：unused≡READY；used/distributed≡CONSUMED（不可再消费）',
            C.pool_status_allows_new_work('unused') and C.pool_status_allows_new_work(C.POOL_READY)
            and not C.pool_status_allows_new_work('used')
            and not C.pool_status_allows_new_work('distributed')
            and C.normalize_pool_status('distributed') == C.POOL_CONSUMED,
            f"distributed→{C.normalize_pool_status('distributed')}",
        ))

        # --- C. 正常消费：旧拼写行也能取、一次性、消费会话落库 --------------
        legacy = pair_item('c-legacy', status='unused')  # 历史拼写，只在别名表里算"可用"
        session = _make_session(node, other, 'c')
        first = KeyPoolService.consume_key(node.node_id, other.node_id, session=session)
        legacy.refresh_from_db()
        results.append(_report(
            '★ 历史拼写（unused）的行也能被取到 —— 只认 READY 会让它永远取不出来',
            first.get('success') is True and first.get('pool_id') == legacy.pool_id,
            f"success={first.get('success')} pool_id={first.get('pool_id')}",
        ))
        results.append(_report(
            '★ 取用后行转**规范值** CONSUMED、记下 used_at 与消费会话（页面「消费情况」列的数据源）',
            legacy.status == C.POOL_CONSUMED
            and legacy.used_at is not None
            and legacy.used_by_session_id == session.pk,
            f'status={legacy.status} session={legacy.used_by_session_id}',
        ))
        second = KeyPoolService.consume_key(node.node_id, other.node_id, session=session)
        results.append(_report(
            '★ 同一行取不到第二次（一次性消费；此时节点对没有其它可用行）',
            second.get('success') is False
            and second.get('code') == C.ERR_POOL_ITEM_UNAVAILABLE,
            f"success={second.get('success')} code={second.get('code')}",
        ))

        # --- D. 过期行：消费口与页面必须同判 --------------------------------
        expired = pair_item('d-exp', status='READY')
        PreDistributedKey.objects.filter(pk=expired.pk).update(
            expires_at=timezone.now() - timedelta(minutes=1))
        expired.refresh_from_db()
        after_exp = KeyPoolService.consume_key(node.node_id, other.node_id)
        expired.refresh_from_db()
        results.append(_report(
            '★ 已过期的 READY 行取不出来，且标记未动（过期不是消费，不改状态）',
            after_exp.get('success') is False and expired.status == C.POOL_READY,
            f"success={after_exp.get('success')} 行状态={expired.status}",
        ))
        from pqkds.serializers import PreDistributedKeySerializer
        shown = PreDistributedKeySerializer(expired).data
        results.append(_report(
            '★ 页面口径同判：序列化器的 effective_status=EXPIRED（库内值仍是 READY）',
            shown.get('effective_status') == C.POOL_EXPIRED and shown.get('status') == C.POOL_READY,
            f"effective_status={shown.get('effective_status')} status={shown.get('status')}",
        ))

        # --- E. 引用的长期密钥被回收 → 识破即纠正、跳过继续取 ------------------
        key = R.register_public_key(node, algorithm='KYBER', public_key=_b64_key(1184))
        bound = pair_item('e-bound', status=C.POOL_READY,
                          long_term_key_id=key.key_id, long_term_key_version=key.key_version)
        # 只直调登记层回收（`revoke_public_key(row, reason)` 收的是**行**；做
        # 影响面编排的是 `revoke_long_term_key`），池项仍是 READY —— 这正是
        # "连带标记漏网"的行（历史数据、手工改库、标记引入之前的行）。消费口
        # 必须自己看出来，而不是把它取走、让调用方解封时才失败。
        R.revoke_public_key(key, '自测：KMS-013')

        # E1 —— 池子里只剩这一条死件：拒绝，且码是 KEY_REVOKED（处置是
        # "重新预分配"，不是"稍后再试"）。
        blocked = KeyPoolService.consume_key(node.node_id, other.node_id)
        bound.refresh_from_db()
        results.append(_report(
            '★ 只剩死件时消费被拒：码是 KEY_REVOKED（不是笼统的"没有可用"）',
            blocked.get('success') is False and blocked.get('code') == C.ERR_KEY_REVOKED,
            f"code={blocked.get('code')} message={str(blocked.get('message'))[:48]}",
        ))
        # E2 —— 识破即纠正：死件被就地标成 REVOKED（与回收路径**同一判据**的
        # 迟到应用）。不标的话它会永远躺在 READY 集合里，页面继续显示
        # "可被会话取用"，与消费的结论再次互相矛盾。
        results.append(_report(
            '★ 死件被就地标成 REVOKED（页面口径从此一致），skipped 如实回报',
            bound.status == C.POOL_REVOKED
            and any(s.get('pool_id') == bound.pool_id for s in blocked.get('skipped') or []),
            f"行状态={bound.status} skipped={blocked.get('skipped')}",
        ))
        # E3 —— 纠正之后不再毒化池子：第二次消费面对的是"没有 READY 行"，
        # 而不是又一次撞上同一条死件。这是"只拒绝不纠正"版本的回归判据 ——
        # 那个版本下这一条会永远返回 KEY_REVOKED。
        after = KeyPoolService.consume_key(node.node_id, other.node_id)
        results.append(_report(
            '★ 第二次消费不再撞上死件：池子空了就是"没有可用"',
            after.get('success') is False and after.get('code') == C.ERR_POOL_ITEM_UNAVAILABLE,
            f"code={after.get('code')}",
        ))
        # E4 —— 跳过继续取：死件（key_index=0）后面还有活件（index=1）时，
        # 消费必须拿到活的那条、并如实回报跳过了什么。这一条钉的是
        # "一条死件毒化整个节点对"的反面（消费按 key_index 取，死件排在前
        # 就会永远挡路）。
        key2 = R.register_public_key(node, algorithm='KYBER', public_key=_b64_key(1184))
        dead2 = pair_item('e-dead2', status=C.POOL_READY,
                          long_term_key_id=key.key_id, long_term_key_version=1)
        live = pair_item('e-live', status=C.POOL_READY,
                         long_term_key_id=key2.key_id, long_term_key_version=key2.key_version)
        PreDistributedKey.objects.filter(pk=dead2.pk).update(key_index=0)
        PreDistributedKey.objects.filter(pk=live.pk).update(key_index=1)
        picked = KeyPoolService.consume_key(node.node_id, other.node_id)
        dead2.refresh_from_db()
        live.refresh_from_db()
        results.append(_report(
            '★ 跳过死件取到活件：拿到的是活的那条，skipped 如实带出死件',
            picked.get('success') is True and picked.get('pool_id') == live.pool_id
            and dead2.status == C.POOL_REVOKED and live.status == C.POOL_CONSUMED
            and len(picked.get('skipped') or []) == 1,
            f"取到={picked.get('pool_id')} 死件={dead2.status} 活件={live.status} "
            f"skipped={picked.get('skipped')}",
        ))
        # 正对照：上面全部拒绝之后，引用活密钥的行仍然能正常消费 ——
        # 没有这一条，"闸门恒拒绝"也能让拒绝面全绿。
        key3 = R.register_public_key(node, algorithm='KYBER', public_key=_b64_key(1184))
        fresh = pair_item('e-fresh', status=C.POOL_READY,
                          long_term_key_id=key3.key_id, long_term_key_version=key3.key_version)
        ok_again = KeyPoolService.consume_key(node.node_id, other.node_id)
        fresh.refresh_from_db()
        results.append(_report(
            '★ 正对照：引用活密钥（新 keyId）的行照常消费成功（闸门不是恒拒绝）',
            ok_again.get('success') is True and ok_again.get('pool_id') == fresh.pool_id
            and fresh.status == C.POOL_CONSUMED
            and ok_again.get('status') == C.POOL_CONSUMED,
            f"success={ok_again.get('success')} pool_id={ok_again.get('pool_id')}",
        ))

        # --- F. skip_locked=False 的等锁路径（验收脚本走 HTTP，覆盖不了它）-----
        # 真开一个**持锁线程**：它把这一行 `SELECT ... FOR UPDATE` 锁住 1.2 秒
        # 再回滚。主线程此时调 skip_locked=False 的消费 —— InnoDB 会等锁，
        # 对方回滚后重新读到的是 READY（对方没提交任何东西）→ 照常消费成功。
        #
        # ⚠️ 两个细节缺一不可，否则这条断言在证明不了任何事的情况下也会绿：
        #    * 持锁线程必须先 `set_autocommit(False)` —— autocommit 下
        #      `SELECT ... FOR UPDATE` 是语句级锁，语句一结束就释放，主线程
        #      根本不会等；
        #    * 断言主线程**确实等了**（elapsed ≥ 0.3s）。不看耗时的版本里，
        #      就算锁压根没生效、断言也照样通过。
        # 真并发的"恰好一个成功"由验收脚本用 N 个独立进程钉（同一进程的线程
        # 测不出 InnoDB 对**不同连接**的隔离，那只由它们的连接数保证）。
        wait_item = pair_item('f-wait', status=C.POOL_READY)
        import threading
        import time as _time
        state = {}

        def _hold_row_lock():
            from django.db import connection as conn
            try:
                conn.set_autocommit(False)
                with conn.cursor() as cur:
                    cur.execute(
                        'SELECT id FROM dvadmin_pqkds_pre_distributed_keys WHERE id=%s FOR UPDATE',
                        [wait_item.pk],
                    )
                    state['held'] = True
                    _time.sleep(1.2)
                conn.rollback()
            except Exception as exc:  # noqa: BLE001
                state['error'] = repr(exc)
            finally:
                conn.close()

        holder = threading.Thread(target=_hold_row_lock, daemon=True)
        holder.start()
        wait_start = _time.perf_counter()
        while not state.get('held') and not state.get('error') and holder.is_alive():
            _time.sleep(0.02)
        waited = KeyPoolService.consume_key(node.node_id, other.node_id, skip_locked=False)
        elapsed = _time.perf_counter() - wait_start
        holder.join(timeout=5)
        results.append(_report(
            'skip_locked=False 的等锁路径：真等到锁释放后消费成功（且确实等待过）',
            waited.get('success') is True and waited.get('pool_id') == wait_item.pool_id
            and elapsed >= 0.3,
            f"success={waited.get('success')} elapsed={elapsed:.2f}s "
            f"error={state.get('error')}",
        ))
    finally:
        # ⚠️ `_main` 只清理它自己建的节点。对端节点由本组自己交代清楚 ——
        #    池行与我会话都挂在这个对端（或被测节点）上，随 CASCADE 一并清掉；
        #    漏删不会让本组失败，只会让开发库里慢慢积起没人认得出来的表名行。
        other.delete()
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
        ("回收的影响面：三个连带失效、重试补做、版本区分", test_revoke_service_impact),
        ("按显式版本取密钥：四种拒绝各自可区分（KMS-008）", test_require_key_version),
        ("服务端验签：验不过必拒、验过才登记（KMS-010）", test_verify_node_distribution_signature),
        ("池项消费：断口复现、状态机、终态、过期与引用失效（KMS-013）", test_pool_consume_semantics),
    ]

    failed = []
    created = []
    try:
        for index, (name, fn) in enumerate(tests, start=1):
            # KMS-010 的验签组要落 `DistributionBatch`（user_id 非空，取
            # `Node.sys_user_id`），所以它的两个夹具节点必须带账号映射；
            # 其余组不需要（复用同一个 `_make_node` 也行，但那样每个节点都占
            # 一个 sys_user 值，与"这个组用不上它"的事实不符）。
            node = _make_node(
                f'{index:02d}',
                with_user=(fn is test_verify_node_distribution_signature),
            )
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
