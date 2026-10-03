/**
 * KMS-015 验收：**历史数据迁移与旧路径封存**（计划 §7 阶段 7 的全部判据）。
 *
 * 判据为什么是这几个动作，而不是"接口返回 200"
 * ------------------------------------------
 *
 *   * **"旧错误算法不能进入新业务"** ≠ "白名单里没有它"。第 2/3 节把三条
 *     入口逐个试过：预分配生成、补货、消费者取用 —— 每一条都断言**可辨识的
 *     拒绝**，并且**紧接着断言历史行仍然可读**（列表里在、状态如实）。
 *     只钉"拒绝"会让"把历史行也一起删掉"这种过度清理同样全绿 —— 而
 *     计划明确要求"历史数据仍可审计"。
 *   * **"私钥清理有数量、哈希与回滚记录"** ≠ "跑了条命令"。第 5 节按
 *     计划 §15 的**三步顺序**实测：dry-run（只有哈希、无写入）→ 备份
 *     （0600、含值与逐列 sha256）→ 核验一致后清空；还断言"不带 --backup
 *     的 --clear 必须被拒"（没有回滚记录的清空等于销毁）。
 *   * **"服务端不再产生私钥"** ≠ "把生成按钮下掉"。第 6 节把
 *     `auto_fix_all_nodes`（启动钩子，原先会在长度异常时**重新生成并写回
 *     节点私钥**）作为被测对象：造一个"格式异常"的行，跑一遍，断言**行没被
 *     改动** —— 生成路径还在代码里，这条断言就是它的看门狗。
 *   * **"镜像列停写"** ≠ "注释里写了"。第 4 节登记一把新 Falcon 公钥后
 *     直接读库：规范列有值、镜像列**必须为空**（停写生效）；就绪判定
 *     仍为 true（读路径已切到规范列优先）；回收后**两列都被清**
 *     （停写的是写，不是清理 —— 存量旧值必须能被清掉）。
 *
 * ⚠️ 会建真节点、写真数据；**会真的执行私钥清理**（不可逆，这正是本阶段
 *    要交付的动作；库内当时已只剩极少量存量值，备份落在
 *    `kms-ops/dvadmin-logs/`，即容器内 `/var/log`）。
 * ⚠️ 服务端代码打进镜像：改了后端不重建，第 1 节的探针先失败 —— 刻意如此。
 */
import { execFileSync, spawnSync } from 'node:child_process'
import { existsSync, readFileSync, statSync, writeFileSync, mkdirSync } from 'node:fs'
import {
  PQKDS,
  api,
  isOk,
  title,
  makeReporter,
  adminLogin,
  newNodeSession,
  cryptoProvider
} from './lib/node-session.mjs'
import { sqlScalar, dockerBin } from '../../../tools/lib/mysql.mjs'

const { check, info, finish } = makeReporter()

const KYBER = 'KYBER'
const VARIANT = 768
const DOMAIN = 'kms015'

const NODE_TABLE = 'falcon_kds.dvadmin_pqkds_nodes'
const POOL_TABLE = 'falcon_kds.dvadmin_pqkds_pre_distributed_keys'
const LTK_TABLE = 'falcon_kds.dvadmin_pqkds_node_long_term_keys'

const orm = (program) => execFileSync(
  dockerBin, ['exec', '-i', '-w', '/backend', 'dvadmin3-django', 'python', '-'],
  { input: program, encoding: 'utf8', env: { ...process.env, MSYS_NO_PATHCONV: '1' } }
)
const ormHeader = `
import os, sys
sys.path.insert(0, '/backend')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'application.settings')
import django
django.setup()
`
const manage = (args) => {
  // ⚠️ 用 spawnSync 而不是 execFileSync：管理命令"拒绝执行"时把原因写在
  //    **stderr** 上，而 execFileSync 抛错时两股流都不好取全（stdout 字段
  //    在新版 Node 上才有）。这里要断言的正是"拒绝的那句话"。
  const r = spawnSync(dockerBin,
    ['exec', '-w', '/backend', 'dvadmin3-django', 'python', 'manage.py', ...args],
    { encoding: 'utf8', env: { ...process.env, MSYS_NO_PATHCONV: '1' } })
  return { out: r.stdout || '', err: r.stderr || '' }
}

// ---------------------------------------------------------------------------
// 1. ★ 部署探针：封存码与拒绝面都在跑着的进程里
// ---------------------------------------------------------------------------
title('1. ★ 部署探针：旧会话动作已封存（410）；falcon_lattice 的生成口已拒')
info('KMS-015 的三个可观察标记：① /session-keys/ 的旧动作返回**明确封存码**；')
info('② /key-pool/generate/ 拒 falcon_lattice；③ /key-pool/replenish/ 同拒。')

const adminToken = await adminLogin()

const sealProbe = await api(PQKDS, '/session-keys/initiate/', {
  method: 'POST',
  token: adminToken,
  body: { node1_id: 'x', node2_id: 'y' }
})
check('★ ① 旧会话动作（initiate）返回明确封存码 410 + 指路新链路（不是 404 静默消失）',
  sealProbe.body?.code === 410
  && String(sealProbe.body?.msg || '').includes('/node-self/distributions'),
  `code=${sealProbe.body?.code} msg=${String(sealProbe.body?.msg || '').slice(0, 80)}`)

const genFalconProbe = await api(PQKDS, '/key-pool/generate/', {
  method: 'POST',
  token: adminToken,
  body: { node1_id: 'probe-a', node2_id: 'probe-b', algorithm: 'falcon_lattice', count: 1 }
})
check('★ ② /key-pool/generate/ 拒 falcon_lattice（ALGORITHM_NOT_ALLOWED 写进文案）',
  !isOk(genFalconProbe.body)
  && String(genFalconProbe.body?.msg || '').includes('ALGORITHM_NOT_ALLOWED'),
  `msg=${String(genFalconProbe.body?.msg || '').slice(0, 120)}`)

const replenishFalconProbe = await api(PQKDS, '/key-pool/replenish/', {
  method: 'POST',
  token: adminToken,
  body: { node1_id: 'probe-a', node2_id: 'probe-b', algorithm: 'falcon_lattice', target_size: 10 }
})
check('★ ③ /key-pool/replenish/ 同拒（补货也是新业务）',
  !isOk(replenishFalconProbe.body)
  && String(replenishFalconProbe.body?.msg || '').includes('ALGORITHM_NOT_ALLOWED'),
  `msg=${String(replenishFalconProbe.body?.msg || '').slice(0, 120)}`)

// ---------------------------------------------------------------------------
// 2. 夹具：A/B 两个真节点；falcon_lattice 历史池行（ORM 造，模拟迁移前数据）
// ---------------------------------------------------------------------------
title('2. 夹具：A/B 两节点 + 一条 falcon_lattice 历史池行（模拟遗留数据）')

const nodeA = await newNodeSession(adminToken, { prefix: 'K15A', name: 'KMS-015 节点A', domainId: DOMAIN })
const nodeB = await newNodeSession(adminToken, { prefix: 'K15B', name: 'KMS-015 节点B', domainId: DOMAIN })
check('两个节点已建好并激活', Boolean(nodeA.token && nodeB.token),
  `${nodeA.nodeId} / ${nodeB.nodeId}`)

const register = (session, algorithm, material, extra = {}) =>
  api(PQKDS, '/node-self/keys/', {
    method: 'POST',
    token: session.token,
    body: {
      algorithm,
      publicKey: material.publicKey,
      securityLevel: extra.securityLevel,
      deviceId: session.fingerprint,
      keyId: material.keyId,
      keyVersion: material.version
    }
  })

info('生成密钥并登记（Falcon 本机生成要十几秒）…')
const keys = { A: {}, B: {} }
for (const [label, session] of [['A', nodeA], ['B', nodeB]]) {
  for (const [algorithm, options, extra] of [
    ['SM2', {}, {}],
    ['SSCL', {}, {}],
    [KYBER, { variant: VARIANT }, { securityLevel: String(VARIANT) }],
    ['FALCON', {}, {}]
  ]) {
    const material = await cryptoProvider.generate(algorithm, { nodeId: session.nodeId, ...options })
    const up = await register(session, algorithm, material, extra)
    if (!isOk(up.body)) {
      check(`${label} 的 ${algorithm} 登记成功`, false, `code=${up.body?.code} msg=${up.body?.msg}`)
    }
    keys[label][algorithm] = material
  }
}
for (const session of [nodeA, nodeB]) {
  const init = await api(PQKDS, '/node-self/init/', { method: 'POST', token: session.token })
  if (!isOk(init.body)) {
    check(`${session.nodeId} 初始化收尾成功`, false, `msg=${init.body?.msg}`)
  }
}

const legacyFixture = orm(ormHeader + `
from pqkds.models import Node, PreDistributedKey
from django.utils import timezone
from datetime import timedelta
a = Node.objects.get(node_id='${nodeA.nodeId}')
b = Node.objects.get(node_id='${nodeB.nodeId}')
# ⚠️ update_or_create（而不是 create）：pool_id+key_index 有唯一约束，
#    上一次中断的运行可能留下同名行（它引用的是**上一轮**的节点，
#    已被清理不存在了）—— 直接 create 会撞唯一键，看起来像"夹具写坏"。
row, _ = PreDistributedKey.objects.update_or_create(
    pool_id='TESTKMS015-legacy-falcon', key_index=0,
    defaults=dict(node1=a, node2=b,
                  algorithm='falcon_lattice', wrapping_algorithm='falcon_lattice',
                  encrypted_key_data='{"legacy": true}', key_hash='a' * 64,
                  status='READY', expires_at=timezone.now() + timedelta(days=7)))
print('LEGACY_POOL_OK pk=%s' % row.pk)
`)
check('夹具：一条 falcon_lattice 历史池行（READY，模拟迁移前遗留数据）',
  legacyFixture.includes('LEGACY_POOL_OK'), legacyFixture.trim().split('\n')[-1])

// ---------------------------------------------------------------------------
// 3. ★ 历史错误算法：可读，但三条入口全部拒
// ---------------------------------------------------------------------------
title('3. ★ falcon_lattice：入新业务被拒（三条口子），历史行仍可读可审计')

const listLegacy = await api(PQKDS, '/key-pool/?pool_id=TESTKMS015-legacy-falcon&page=1&limit=5', { token: adminToken })
const legacyRow = (listLegacy.body?.data || [])[0] || {}
check('★ 历史行**可读**：列表里有它，算法与状态如实下发（不是被藏起来）',
  legacyRow.pool_id === 'TESTKMS015-legacy-falcon'
  && legacyRow.algorithm === 'falcon_lattice'
  && legacyRow.effective_status === 'READY',
  `algorithm=${legacyRow.algorithm} effective=${legacyRow.effective_status}`)

const consumeLegacy = await api(PQKDS, '/key-pool/consume/', {
  method: 'POST',
  token: adminToken,
  body: { node1_id: nodeA.nodeId, node2_id: nodeB.nodeId }
})
check('★ 消费口拒：ALGORITHM_NOT_ALLOWED（历史错误算法不进新业务）',
  !isOk(consumeLegacy.body)
  && String(consumeLegacy.body?.msg || '').includes('ALGORITHM_NOT_ALLOWED'),
  `msg=${String(consumeLegacy.body?.msg || '').slice(0, 130)}`)
check('★ 被拒之后行**原状**（不代标、不消费 —— 它是历史证据，不是死件）',
  sqlScalar(`SELECT status FROM ${POOL_TABLE} WHERE pool_id='TESTKMS015-legacy-falcon';`) === 'READY',
  `status=${sqlScalar(`SELECT status FROM ${POOL_TABLE} WHERE pool_id='TESTKMS015-legacy-falcon';`)}`)

// 正对照：**没有**任何行的节点对上，消费口报的是 POOL_ITEM_UNAVAILABLE ——
// 证明 ALGORITHM_NOT_ALLOWED 不是"任何消费都返回它"。
//（不用 nodeA↔nodeB 反向：那条 falcon 行就在这对节点上，两个方向都会撞到它，
//  拿它做正对照会把"分不出两种失败"当成通过。）
const consumeEmptyPair = await api(PQKDS, '/key-pool/consume/', {
  method: 'POST',
  token: adminToken,
  body: { node1_id: 'KMS015-NO-SUCH-A', node2_id: 'KMS015-NO-SUCH-B' }
})
check('★ 正对照：空节点对报 POOL_ITEM_UNAVAILABLE（算法码不是恒返回）',
  !isOk(consumeEmptyPair.body)
  && String(consumeEmptyPair.body?.msg || '').includes('POOL_ITEM_UNAVAILABLE'),
  `msg=${String(consumeEmptyPair.body?.msg || '').slice(0, 110)}`)

// 历史长期密钥（LEGACY 状态）可读且明确"不可用于新工作"
const legacyLtk = orm(ormHeader + `
from pqkds.models import Node, NodeLongTermKey
import uuid
b = Node.objects.get(node_id='${nodeB.nodeId}')
row = NodeLongTermKey.objects.create(
    node=b, algorithm='KYBER', key_id='legacy-falcon-era-%s' % uuid.uuid4().hex[:6],
    key_version=1, status='LEGACY', legacy=True, legacy_source='KMS-015 验收夹具（历史遗留）',
    public_key='00', public_key_hash='b' * 64)
print('LEGACY_LTK_OK %s' % row.key_id)
`)
const legacyKeyId = (legacyLtk.match(/LEGACY_LTK_OK (\S+)/) || [])[1] || ''
check('夹具：一条 LEGACY 状态的长期密钥行（模拟历史遗留）', Boolean(legacyKeyId), legacyKeyId)

const keysB = await api(PQKDS, '/node-self/keys/', { token: nodeB.token })
// ⚠️ 形状是 `{nodeId, keys: [...]}`（不是 `{items}` —— 那是 envelopes 那边的）。
//    字段名写错时断言会以"找不到行"失败，看起来像"历史行没落库"。
const legacyKeyRow = (keysB.body?.data?.keys || []).find((k) => k.keyId === legacyKeyId)
check('★ 历史长期密钥**可读**：在节点的密钥列表里，带 legacy 来源说明',
  Boolean(legacyKeyRow) && legacyKeyRow?.legacy === true,
  `keyId=${legacyKeyId} legacy=${legacyKeyRow?.legacy} legacySource=${String(legacyKeyRow?.legacySource || '').slice(0, 30)}`)
check('★ 历史长期密钥明确"不用于新工作"（allowsNewWork=false —— 页面据此置灰）',
  legacyKeyRow?.allowsNewWork === false && legacyKeyRow?.status === 'LEGACY',
  `status=${legacyKeyRow?.status} allowsNewWork=${legacyKeyRow?.allowsNewWork}`)

const nodeBId = sqlScalar(`SELECT id FROM ${NODE_TABLE} WHERE node_id='${nodeB.nodeId}';`) || ''
const nodeAId = sqlScalar(`SELECT id FROM ${NODE_TABLE} WHERE node_id='${nodeA.nodeId}';`) || ''
const userB = sqlScalar(`SELECT IFNULL(sys_user_id,'') FROM ${NODE_TABLE} WHERE node_id='${nodeB.nodeId}';`) || ''
// ⚠️ 授权方向：调用方是 **B**（旧接口的发起者），所以要把 **A 的节点**授权给
//    **B 的用户**（`authorized_node_ids(caller.userId)` 查的是"这个用户能发给谁"）。
//    反过来授会把下面两条断言都挡在"你没有通信权限"上 —— 第一次跑就是这么挂的。
const grant = await api(PQKDS, '/admin/node-authorizations/', {
  method: 'POST',
  token: adminToken,
  body: { userId: Number(userB), nodeId: Number(nodeAId), remark: 'KMS-015 验收：B 需要能向 A 分发' }
})
check('夹具：B 的用户对 A 的节点已授权（旧接口的授权检查先于算法检查）', isOk(grant.body),
  `code=${grant.body?.code} msg=${String(grant.body?.msg || '').slice(0, 60)}`)
const distLegacyApi = (algorithm) => api(PQKDS, '/key-pool/distribute-to-user/', {
  method: 'POST',
  token: nodeB.token,
  body: {
    source_key_id: 1, node_ids: [Number(nodeAId)], count: 1,
    node_wrapping_algorithm: algorithm
  }
})

const legacyAlgo = await distLegacyApi('falcon_lattice')
check('★ 旧用户腿接口**拒 falcon_lattice**（"不支持"写在文案里）+ 响应头仍带 Deprecation',
  !isOk(legacyAlgo.body)
  && String(legacyAlgo.body?.message || legacyAlgo.body?.msg || '').includes('节点封装算法不支持')
  && legacyAlgo.headers?.deprecation === 'true',
  `HTTP=${legacyAlgo.status} msg=${String(legacyAlgo.body?.message || '').slice(0, 80)} `
  + `Deprecation=${legacyAlgo.headers?.deprecation}`)
info('（这条断言接替了已删除的 tools/verify-distribute-algorithm.mjs —— 那个脚本断言的')
info('  "falcon_lattice 被接受"在 KMS-008 之后就不成立了；删除时按封存口径反转。）')

// 正对照：同一接口的合法算法**越过算法检查**（失败换成别的理由，不是"不支持"）。
// ⚠️ 授权检查在前、算法检查在后（见 _parse 的顺序）—— 这两步能到检查本身
//    就说明授权面是通的（上面 B→A 的授权就是为它准备的）。
const legacyKyber = await distLegacyApi('kyber_kem')
check('★ 正对照：同接口给 kyber_kem **越过算法检查**（失败换成别的理由，不是"不支持"）',
  !String(legacyKyber.body?.message || legacyKyber.body?.msg || '').includes('节点封装算法不支持'),
  `HTTP=${legacyKyber.status} msg=${String(legacyKyber.body?.message || legacyKyber.body?.msg || '').slice(0, 80)}`)

// ---------------------------------------------------------------------------
// 4. ★ 镜像列停写：登记只写规范列；回收仍然两列都清
// ---------------------------------------------------------------------------
title('4. ★ Node.falcon_public_key 停写：新登记只写规范列，读路径走规范列优先')

const falconA = keys.A.FALCON
const mirrorState = sqlScalar(
  `SELECT CONCAT_WS('|', LENGTH(IFNULL(falcon_sign_public_key,'')), LENGTH(IFNULL(falcon_public_key,''))) `
  + `FROM ${NODE_TABLE} WHERE node_id='${nodeA.nodeId}';`) || ''
check('★ 登记后：规范列有值、镜像列**为空**（停写生效，不再双写）',
  /^\d+\|0$/.test(mirrorState) && mirrorState.split('|')[0] !== '0',
  `规范列长度|镜像列长度 = ${mirrorState}`)

const nodeSelfA = await api(PQKDS, '/node-self/', { token: nodeA.token })
check('★ 就绪判定仍为 true（读路径已切到 falcon_sign_public_key 优先）',
  nodeSelfA.body?.data?.node?.keys?.falcon === true,
  `keys.falcon=${nodeSelfA.body?.data?.node?.keys?.falcon}`)

const revokeFalcon = await api(PQKDS, '/node-self/keys/revoke/', {
  method: 'POST',
  token: nodeA.token,
  body: { algorithm: 'FALCON', keyId: falconA.keyId, keyVersion: falconA.version, reason: 'KMS-015 验收：停写后的清理面' }
})
check('回收这把 FALCON 成功', isOk(revokeFalcon.body), `code=${revokeFalcon.body?.code}`)
const mirrorAfterRevoke = sqlScalar(
  `SELECT CONCAT_WS('|', LENGTH(IFNULL(falcon_sign_public_key,'')), LENGTH(IFNULL(falcon_public_key,''))) `
  + `FROM ${NODE_TABLE} WHERE node_id='${nodeA.nodeId}';`) || ''
check('★ 回收后**两列都被清**：停写的是写，清理仍然覆盖镜像列（存量旧值必须能被清掉）',
  mirrorAfterRevoke === '0|0', `规范列|镜像列 = ${mirrorAfterRevoke}`)

// ---------------------------------------------------------------------------
// 5. ★ 私钥清理：三步顺序 + 拒绝无备份的清空（计划 §15 第 7 步）
// ---------------------------------------------------------------------------
title('5. ★ 私钥清理：dry-run（只哈希）→ 备份（0600）→ 核验一致 → 清空')
info('⚠️ 这一步**真的清空**（本阶段的交付动作，不可逆）。为了让三步流程**每次运行**')
info('    都可复现，先用 ORM 给夹具节点塞一个明显的假值（KMS015-FAKE-…），再对它走完')
info('    全流程；真假值一视同仁 —— 命令按列、不挑内容。备份落在容器 /var/log，')
info('    即宿主 kms-ops/dvadmin-logs/ —— 那正是回滚记录所在。')

// 假夹具值（肉眼可辨、非任何真实材料）；随后由清理流程清掉。
orm(ormHeader + `
from pqkds.models import Node
n = Node.objects.get(node_id='${nodeA.nodeId}')
n.falcon_sign_private_key = 'KMS015-FAKE-PRIVATE-MATERIAL-FOR-CLEARING-TEST'
n.save(update_fields=['falcon_sign_private_key'])
print('FAKE_PRIV_OK')
`)

const dry = manage(['clear_node_private_keys'])
check('★★ dry-run 报告数量与逐列哈希（不写库）',
  /扫描完成/.test(dry.out) && /sha256=/.test(dry.out)
  && dry.out.includes(nodeA.nodeId),
  dry.out.split('\n').filter((l) => l.includes('扫描完成') || l.includes('sha256')).slice(0, 2).join(' | ').slice(0, 170))

const noBackup = manage(['clear_node_private_keys', '--clear'])
check('★ 不带 --backup 的 --clear **被拒**（没有回滚记录的清空等于销毁）',
  /拒绝执行 --clear/.test(noBackup.err + noBackup.out),
  (noBackup.err || noBackup.out).split('\n').filter(Boolean).slice(0, 2).join(' | ').slice(0, 140))

const stamp = new Date().toISOString().replace(/[-:T.]/g, '').slice(0, 14)
const backupName = `kms015-private-backup-${stamp}.json`
const backupPath = `/var/log/${backupName}`
const backup = manage(['clear_node_private_keys', '--backup', backupPath])
check('备份写出成功（含值与逐列 sha256，输出带宿主对应路径）',
  /已备份/.test(backup.out) && /0600/.test(backup.out),
  backup.out.split('\n').filter((l) => l.includes('已备份') || l.includes('宿主')).join(' | ').slice(0, 170))

// 宿主侧核对备份文件（/var/log 挂载到 kms-ops/dvadmin-logs）
const hostBackup = `../../kms-ops/dvadmin-logs/${backupName}`
check('★ 备份文件落在宿主可审计位置（kms-ops/dvadmin-logs/，含 rows 与 exportedAt）',
  existsSync(hostBackup) && (() => {
    const parsed = JSON.parse(readFileSync(hostBackup, 'utf8'))
    return Array.isArray(parsed.rows) && Boolean(parsed.exportedAt)
  })(),
  existsSync(hostBackup)
    ? `${hostBackup}（${statSync(hostBackup).size}B）`
    : `找不到 ${hostBackup}`)

const cleared = manage(['clear_node_private_keys', '--backup', backupPath, '--clear'])
check('★ 核验一致后清空成功（输出带条数与回滚记录位置）',
  /已清空/.test(cleared.out) && /回滚记录/.test(cleared.out),
  cleared.out.split('\n').filter((l) => l.includes('已清空') || l.includes('回滚记录')).join(' | ').slice(0, 170))

const privRemaining = sqlScalar(
  `SELECT COUNT(*) FROM ${NODE_TABLE} WHERE COALESCE(kyber_private_key,'')<>'' `
  + `OR COALESCE(gm_private_key,'')<>'' OR COALESCE(sscl_private_key,'')<>'' `
  + `OR COALESCE(falcon_private_key,'')<>'' OR COALESCE(falcon_sign_private_key,'')<>'' `
  + `OR COALESCE(falcon_lattice_params,'')<>'';`) || '?'
check('★★ 清空后库内服务端私钥材料为 0 行（六列全覆盖；含其他存量节点）',
  privRemaining === '0', `剩余 ${privRemaining} 行`)

// ---------------------------------------------------------------------------
// 6. ★ auto_fix 不再生成：格式异常只报告，不写回
// ---------------------------------------------------------------------------
title('6. ★ auto_fix_all_nodes 只报告不生成：格式异常的节点**一行都不动**')
info('原实现在长度异常时会在服务端重新生成密钥对并写回 kyber_private_key ——')
info('那是 §4.4 禁止的"服务端产生私钥"，还会把节点公钥换成它本地没有私钥的新钥匙。')

const fabricate = orm(ormHeader + `
from pqkds.models import Node
import base64
n = Node.objects.get(node_id='${nodeA.nodeId}')
n.kyber_public_key = base64.b64encode(b'PK-BAD-LENGTH').decode()
n.kyber_private_key = base64.b64encode(b'SK-BAD').decode()
n.save(update_fields=['kyber_public_key', 'kyber_private_key'])
print('FABRICATED_OK')
`)
check('夹具：造一个 Kyber 密钥格式异常的节点（清空之后手动塞入坏材料）',
  fabricate.includes('FABRICATED_OK'), fabricate.trim().split('\n')[-1])

const autoFixRun = orm(ormHeader + `
from pqkds.apps import PqkdsConfig
import logging, sys
# ⚠️ basicConfig 在本项目的 Django LOGGING 配置下**不生效**（root logger 已被
#    配置过，basicConfig 直接 no-op）。要拿到消息，得给这个 logger 自己挂一个
#    写 stdout 的 handler —— 不挂的话断言读到空串，看起来像"函数没跑"。
logger = logging.getLogger('pqkds.apps')
handler = logging.StreamHandler(sys.stdout)
handler.setLevel(logging.INFO)
logger.addHandler(handler)
logger.setLevel(logging.INFO)
# 不能写 PqkdsConfig() —— AppConfig 的构造要 (app_name, app_module)。
# 这个体检函数不使用 self，直接以未绑定方式调用即可（放在这里刻意的：
# 让断言的是**函数本身**，而不是"启动钩子碰巧跑过"）。
PqkdsConfig.auto_fix_all_nodes(None)
`)
// ⚠️ 断言比的是 **ORM 写进去的原文**读回来的样子：上游脚本用 base64 塞值，
//    读库读回的是**原文**（'PK-BAD-LENGTH'）—— 拿 base64 去比会一直失败
//   （第一次跑就是这么撞的），而失败信息看起来像"材料被换了"。
check('auto_fix 跑完并**点名**异常节点（只报告）',
  autoFixRun.includes(nodeA.nodeId) || autoFixRun.includes('格式异常'),
  autoFixRun.split('\n').filter((l) => l.includes('异常') || l.includes('只报告')).slice(0, 2).join(' | ').slice(0, 170))

// ⚠️ 断言比的是**原文**：ORM 写进去的是 Python 字符串（'PK-BAD-LENGTH'），
//    读库读回来也是原文 —— 拿 base64（'UEstQkFELUxFTkdUSA=='）去比会一直
//    失败（第一次跑就是这么撞的），而失败信息看起来像"材料被换了"。
const afterFix = sqlScalar(
  `SELECT CONCAT_WS('|', kyber_public_key, kyber_private_key) FROM ${NODE_TABLE} WHERE node_id='${nodeA.nodeId}';`) || ''
// ⚠️ 断言按**夹具写进去的样子**比：上面的夹具程序自己做了
//    `base64.b64encode(b'PK-BAD-LENGTH')`，所以库里躺的是它的 base64
//    （`UEstQkFELUxFTkdUSA==`）。拿原文去比会一直失败 —— 第一次跑就是这么撞的，
//    而失败信息看起来像"材料被换了"。
const afterFixB64Pk = Buffer.from('PK-BAD-LENGTH').toString('base64')
const afterFixB64Sk = Buffer.from('SK-BAD').toString('base64')
check('★★ 坏材料**一行没动**（服务端不再生成/修复私钥 —— 生成路径的看门狗）',
  afterFix.includes(afterFixB64Pk) && afterFix.includes(afterFixB64Sk),
  `读回 ${afterFix.slice(0, 40)}…（期望含 ${afterFixB64Pk.slice(0, 16)}…）`)

// 恢复 A 的密钥列（清掉坏夹具材料，保持库干净；公钥的登记行仍在）
orm(ormHeader + `
from pqkds.models import Node
n = Node.objects.get(node_id='${nodeA.nodeId}')
n.kyber_public_key = ''
n.kyber_private_key = ''
n.save(update_fields=['kyber_public_key', 'kyber_private_key'])
print('CLEANED_FIXTURE')
`)

// ---------------------------------------------------------------------------
// 7. legacy 清单（数量 + 分布）：落盘一份可审计清单
// ---------------------------------------------------------------------------
title('7. legacy 清单：历史遗留行的数量与分布（落盘 kms-ops/backups/）')

const inventorySql = `SELECT legacy, status, algorithm, COUNT(*) FROM ${LTK_TABLE} GROUP BY legacy, status, algorithm ORDER BY legacy, status, algorithm;`
// 整表导出（不用 sqlScalar —— 它只取首行）
const inventoryLines = execFileSync(dockerBin, [
  'exec', 'kms_mysql', 'mysql', '-uroot', '-proot123456', '--default-character-set=utf8mb4', '-N',
  '-e', inventorySql
], { encoding: 'utf8', env: { ...process.env, MSYS_NO_PATHCONV: '1' } })
  .split('\n').filter((l) => l.trim() && !/insecure|Warning/i.test(l))
const legacyCount = inventoryLines
  .filter((l) => l.startsWith('1\t'))
  .reduce((sum, l) => sum + Number(l.split('\t')[3] || 0), 0)
check('legacy 清单可导出（按 legacy × status × algorithm 分组）',
  inventoryLines.length > 0 && legacyCount >= 60,
  `分组 ${inventoryLines.length} 行，legacy=1 共 ${legacyCount} 条`)

const inventoryPath = `../../kms-ops/backups/legacy-inventory-${stamp}.json`
mkdirSync('../../kms-ops/backups', { recursive: true })
writeFileSync(inventoryPath, JSON.stringify({
  exportedAt: new Date().toISOString(),
  note: 'KMS-015 legacy 清单：NodeLongTermKey 按 legacy×status×algorithm 的分布。legacy=1 表示迁移 0016 回填的历史行。',
  groups: inventoryLines.map((l) => {
    const [legacy, status, algorithm, count] = l.split('\t')
    return { legacy: Number(legacy) === 1, status, algorithm, count: Number(count) }
  })
}, null, 2), 'utf8')
check('★ 清单已落盘（kms-ops/backups/，gitignored —— 可审计但不进提交）',
  existsSync(inventoryPath), inventoryPath)
info(`legacy 分布摘录：${inventoryLines.filter((l) => l.startsWith('1\t')).slice(0, 4).join(' / ')}`)

// ---------------------------------------------------------------------------
// 8. 清理：自建自清
// ---------------------------------------------------------------------------
title('8. 清理：删掉本脚本建的两个节点及其一切关联行')
const cleanupProgram = ormHeader + `
from pqkds.models import Node, UserKeyEnvelope, DistributionBatch
nodes = list(Node.objects.filter(domain_id='${DOMAIN}'))
ids = [n.pk for n in nodes]
user_ids = [n.sys_user_id for n in nodes if n.sys_user_id]
envelopes, _ = UserKeyEnvelope.objects.filter(user_id__in=user_ids).delete()
batches, _ = DistributionBatch.objects.filter(user_id__in=user_ids).delete()
deleted, _ = Node.objects.filter(pk__in=ids).delete()
left = Node.objects.filter(domain_id='${DOMAIN}').count()
print('nodes=%d envelopes=%d batches=%d cascaded=%d left=%d'
      % (len(ids), envelopes, batches, deleted, left))
`
let cleanupOut = ''
let cleanupErr = ''
try {
  cleanupOut = orm(cleanupProgram).trim()
} catch (error) {
  cleanupErr = String(error?.stderr || error?.message || error)
}
info(cleanupOut || cleanupErr)
check('清理完成：域内不再有本脚本建的节点',
  Boolean(cleanupOut) && cleanupOut.endsWith('left=0'), cleanupOut || cleanupErr)

info(`本次真建的节点：${nodeA.nodeId} / ${nodeB.nodeId}（已在上面删掉）`)
info('证据都在上面：旧动作封存码（410 + 指路）、falcon_lattice 三条入口全拒 + 历史行可读 +')
info('正对照、LEGACY 长期密钥可读且 allowsNewWork=false、镜像列停写（登记不写/回收仍清/读路径优先）、')
info('私钥清理三步（dry-run → 0600 备份 → 核验清空）+ 无备份被拒 + 六列归零、')
info('auto_fix 不再生成（坏材料一行没动）、legacy 清单落盘。')
finish()
