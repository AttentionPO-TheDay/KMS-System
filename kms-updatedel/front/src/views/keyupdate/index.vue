<template>
  <div class="app-container key-update">
    <el-card shadow="never" class="key-update__card">
      <template #header>
        <div class="key-update__header">
          <h2>密钥更新</h2>
          <div class="key-update__header-side">
            <el-tag v-if="node.nodeId" type="info" size="small">{{ node.nodeId }}</el-tag>
            <el-button size="small" :loading="loading" @click="load">刷新</el-button>
          </div>
        </div>
      </template>

      <!-- 账号没关联节点：管理员账号，或数据异常。与「密钥生成」同一判据。 -->
      <el-alert
        v-if="!loading && !mapped"
        type="warning"
        :closable="false"
        show-icon
        title="当前账号未关联任何节点"
        description="密钥更新是节点的动作。请用节点账号登录，或在「节点管理」里创建节点后再由节点自行登录。"
      />

      <template v-else>
        <p class="key-update__lead">
          更新 = 给<strong>同一把</strong>密钥换一个新版本：<span class="mono">keyId</span> 不变、版本号 +1。
          新私钥<strong>先在本机生成并封存</strong>、当场自检，通过之后才把公钥上报；
          本机这一步失败时平台上的生产版本<strong>一点都不会动</strong>。
        </p>

        <el-alert
          v-if="deviceWarning"
          class="key-update__device"
          type="warning"
          :closable="false"
          show-icon
          :title="deviceWarning.title"
        >
          <template #default>
            <p>{{ deviceWarning.detail }}</p>
          </template>
        </el-alert>

        <el-alert v-if="node.keygenPolicy?.enabled === false" type="warning" :closable="false" show-icon
          title="改进型双份额生成尚未启用：请由运维完成独立密码学验证、重建镜像并显式启用策略；不会降级为普通生成。" />
        <div class="key-update__grid">
          <div
            v-for="c in cards"
            :key="c.algorithm"
            class="key-update__algo"
            :class="{ 'is-active': c.active, 'is-warn': c.reconcile && !c.reconcile.ok && c.reconcile.state !== RECONCILE.LOCAL_ONLY }"
          >
            <div class="key-update__algo-head">
              <span class="key-update__algo-name">{{ c.label }}</span>
              <el-tag v-if="c.active" :type="c.active.allowsNewWork ? 'success' : 'info'" size="small">
                {{ c.active.statusLabel }}
              </el-tag>
              <!-- 没有在产行、但历史上登记过：如实说"最后一版是什么状态"，
                   不能一律显示"未登记" —— 已回收的密钥在库里明明白白躺着。 -->
              <el-tag v-else-if="c.latest" type="warning" size="small" effect="plain">
                {{ c.latest.statusLabel }}
              </el-tag>
              <el-tag v-else type="info" size="small" effect="plain">未登记</el-tag>
            </div>
            <p class="key-update__algo-role">{{ c.role }}</p>
            <p class="key-update__algo-role">{{ coreDetail(c.algorithm, c.active ? variantOf(c.active) : undefined) }}</p>
            <p v-if="c.active" class="key-update__algo-role">当前登记来源：{{ formatGenerationName(c.algorithm, c.active.generation) }}</p>

            <dl class="key-update__facts">
              <div class="key-update__fact">
                <dt>生产版本</dt>
                <dd v-if="c.active" class="mono">
                  {{ c.active.keyId }} · v{{ c.active.keyVersion }}
                  <span class="key-update__fact-note">{{ usableText(c.active) }}</span>
                </dd>
                <dd v-else class="is-muted">—</dd>
              </div>
              <div class="key-update__fact">
                <dt>本机材料</dt>
                <dd :class="c.localKey ? 'is-ok' : 'is-muted'">{{ c.localText }}</dd>
              </div>
              <div v-if="c.stagedKey" class="key-update__fact">
                <dt>下一版</dt>
                <dd class="is-ok">
                  已在本机封存 v{{ nextVersionOf(c) }}
                  <span class="key-update__fact-note">上次更新没走完留下的；本次直接用它，不重新生成</span>
                </dd>
              </div>
              <div v-if="c.active" class="key-update__fact">
                <dt>生效时间</dt>
                <dd>{{ formatTime(c.active.effectiveAt || c.active.createdAt) }}</dd>
              </div>
            </dl>

            <!-- 对账结论：与「密钥生成」同一套口径，但这里的后果不同 ——
                 生成页那边点错了只是多一把密钥，这里点错了是**换掉生产版本**。 -->
            <el-alert
              v-if="c.reconcile && c.reconcile.state === RECONCILE.LOCAL_MISSING"
              class="key-update__reconcile"
              type="error"
              :closable="false"
              show-icon
              title="平台记着这把公钥，本机却没有对应私钥"
              description="本机不是生成这把密钥的设备（或站点数据被清过），因此没有材料可以更新。按它分发的信封在本机解不开，换新版本也补不回来。请改回原设备，或在「节点首次初始化」里用本机重新生成一套。"
            />
            <el-alert
              v-else-if="c.reconcile && c.reconcile.state === RECONCILE.MISMATCH"
              class="key-update__reconcile"
              type="error"
              :closable="false"
              show-icon
              title="同一 keyId 下，本机公钥与平台记录不一致"
              description="正常路径不会出现。在这里更新会以本机这把为准，把平台上的生产版本换成一把来源不明的公钥 —— 先查清本机密钥库是否被导入或被改写过。"
            />
            <el-alert
              v-else-if="c.reconcile && c.reconcile.state === RECONCILE.SERVER_EMPTY_PK"
              class="key-update__reconcile"
              type="info"
              :closable="false"
              show-icon
              title="平台记录的公钥无法换算成可比对的形式"
              description="可能是历史行（编码与当前口径不同）。无法确认本机这把就是平台在产那把，因此这里不提供更新 —— 登录服务器查该行原文。"
            />
            <div v-else-if="c.reconcile && c.reconcile.state === RECONCILE.LOCAL_ONLY" class="key-update__pending">
              本机有材料、平台没有在产行 —— 这属于<strong>登记</strong>，请到「密钥生成」页完成。
            </div>
            <div v-else-if="c.reconcile && c.reconcile.state === RECONCILE.MATCH" class="key-update__match">
              <el-icon><CircleCheck /></el-icon>
              <span>本机这把公钥与平台在产版本逐字节相同，可以放心更新</span>
            </div>
            <div v-else-if="!c.active && c.latest" class="key-update__pending">
              该算法的最后一版是「{{ c.latest.statusLabel }}」。<strong>更新救不回来</strong> ——
              已回收是终态，要恢复服务请在「密钥生成」里生成一把新的（新 keyId）。
            </div>

            <div v-if="selfTestOf(c)" class="key-update__selftest" :class="selfTestOf(c).ok ? 'is-ok' : 'is-bad'">
              {{ selfTestOf(c).ok ? '自检通过' : '自检未过' }}：{{ selfTestOf(c).detail }}
            </div>

            <div class="key-update__algo-actions">
              <el-button
                type="primary"
                size="small"
                :loading="updating === c.algorithm"
                :disabled="!c.canRotate || (Boolean(updating) && updating !== c.algorithm)"
                @click="handleRotate(c)"
              >
                {{ updating === c.algorithm ? '更新中…' : (c.active ? `更新到 v${nextVersionOf(c)}` : '无可更新版本') }}
              </el-button>
              <span v-if="c.algorithm === 'KYBER' && c.active" class="key-update__variant-note">
                参数继承当前生产版本：round-3 KEM · {{ variantOf(c.active) }}
              </span>
              <el-button
                v-if="selfTestKeyRef(c)"
                size="small"
                :loading="testing === selfTestKeyRef(c)"
                :disabled="Boolean(testing)"
                @click="runSelfTest(c.algorithm, selfTestKeyRef(c))"
              >
                自检
              </el-button>
            </div>
          </div>
        </div>

        <!-- 最近一次更新的结果。**不随刷新清掉** —— 存证失败这件事必须在页面上留得住，
             否则用户刷新一下就只看到"版本 +1 了"，那条审计缺口就此消失。 -->
        <div v-if="lastRotate" class="key-update__result">
          <div class="key-update__result-head">
            <el-icon v-if="lastRotate.chainHash"><CircleCheck /></el-icon>
            <span class="key-update__result-title">
              {{ lastRotate.label }} 已更新：v{{ lastRotate.fromVersion }} → v{{ lastRotate.toVersion }}
            </span>
            <el-tag size="small" :type="lastRotate.chainHash ? 'success' : 'warning'">
              {{ lastRotate.chainHash ? '已上链' : '存证未成功' }}
            </el-tag>
          </div>
          <dl class="key-update__facts">
            <div class="key-update__fact">
              <dt>keyId</dt>
              <dd class="mono">
                {{ lastRotate.keyId }}
                <span class="key-update__fact-note">与更新前是同一把 —— 更新的语义就是它不变</span>
              </dd>
            </div>
            <div class="key-update__fact">
              <dt>本机材料</dt>
              <dd class="mono" :class="lastRotate.selfTestOk ? 'is-ok' : 'is-bad'">
                {{ lastRotate.keyRef }}
                <span class="key-update__fact-note">
                  {{ lastRotate.selfTestOk ? '自检通过' : '自检未过：' + lastRotate.selfTestDetail }}
                </span>
              </dd>
            </div>
            <div class="key-update__fact">
              <dt>存证</dt>
              <dd :class="lastRotate.chainHash ? 'is-ok' : 'is-bad'">
                <span v-if="lastRotate.chainHash" class="mono">{{ lastRotate.chainHash }}</span>
                <span v-else>
                  已更新，但存证未成功
                  <span class="key-update__fact-note">
                    本次更新<strong>已经生效</strong>；少的是链上那条 KEY_UPDATED，属审计缺口，不是更新失败
                  </span>
                </span>
              </dd>
            </div>
          </dl>
        </div>

        <p class="key-update__note">
          更新<strong>保留 keyId</strong>：旧版本降为「已被取代」后不再用于新会话，但仍能解开按它分发出去的旧信封 ——
          这是"同一个节点换了把锁、旧信还读得出来"所需要的。要整把作废（不再解封任何旧信封）请走回收流程，
          回收是终态，之后本页也更新不了它。
        </p>

        <h3 class="key-update__section-title">
          本节点密钥版本对照
          <span class="key-update__section-note">
            只列 {{ node.nodeId }} 的密钥 —— 同一浏览器上其它节点的材料不会出现在这里
          </span>
        </h3>
        <el-table :data="rows" size="small" border class="key-update__table">
          <el-table-column label="生成方案" min-width="240">
            <template #default="{ row }">{{ formatGenerationName(row.algorithm, (row.server || row.local)?.generation) }}<small v-if="!row.server && row.local?.generation">（本机声明 · 待服务端校验）</small></template>
          </el-table-column>
          <el-table-column label="keyId" min-width="200">
            <template #default="{ row }">
              <span class="mono">{{ row.keyId || '（平台铸造）' }}</span>
            </template>
          </el-table-column>
          <el-table-column label="版本" width="70">
            <template #default="{ row }">v{{ row.version }}</template>
          </el-table-column>
          <el-table-column label="平台" width="140">
            <template #default="{ row }">
              <el-tag v-if="row.server" :type="row.server.allowsNewWork ? 'success' : 'info'" size="small">
                {{ row.server.statusLabel }}
              </el-tag>
              <el-tag v-else type="warning" size="small" effect="plain">未登记</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="本机" width="90">
            <template #default="{ row }">
              <span :class="row.local ? 'is-ok' : 'is-muted'">{{ row.local ? '有私钥' : '无私钥' }}</span>
            </template>
          </el-table-column>
          <el-table-column label="对账" min-width="150">
            <template #default="{ row }">
              <span :class="row.reconcile.ok ? 'is-ok' : 'is-bad'">{{ row.reconcile.text }}</span>
            </template>
          </el-table-column>
          <el-table-column label="公钥字节" width="88">
            <template #default="{ row }">{{ row.publicKeyBytes || '—' }}</template>
          </el-table-column>
          <el-table-column label="生效时间" min-width="150">
            <template #default="{ row }">{{ formatTime(row.server && (row.server.effectiveAt || row.server.createdAt)) }}</template>
          </el-table-column>
          <el-table-column label="更新时间" min-width="150">
            <template #default="{ row }">{{ formatTime(row.server && row.server.updatedAt) }}</template>
          </el-table-column>
          <el-table-column label="操作" width="76" fixed="right">
            <template #default="{ row }">
              <el-button
                v-if="row.local"
                link
                type="primary"
                size="small"
                :disabled="Boolean(testing)"
                @click="runSelfTest(row.algorithm, row.local.keyRef)"
              >
                自检
              </el-button>
            </template>
          </el-table-column>
        </el-table>
        <p v-if="!loading && !rows.length" class="key-update__empty">
          这个节点还没有任何长期密钥。先到「密钥生成」页生成第一把。
        </p>
      </template>
    </el-card>
  </div>
</template>

<script setup>
/**
 * 密钥更新（菜单 5000，节点端 `/keyupdate/index`）。
 *
 * 这个页面在做什么
 * ----------------
 * 计划 §7 阶段 2：「更新时先在本地生成并保存新版本，再登记公钥，最后切换生产版本。
 * 任一步失败不得把服务端状态标成 ACTIVE。」以及 §6.1：「更新保留 key_id，
 * 递增 key_version」「所有请求显式携带版本；不允许依赖'当前最新版本'的隐式行为」。
 *
 * 所以本页的动作顺序是**固定**的，不能调换：
 *
 *   1. 选中一把当前生产密钥（`c.active`），确认本机有对应私钥（对账为「一致」）；
 *   2. **先在本机生成并封存**新版本（`cryptoProvider.generate`，keyId 沿用、
 *      版本 = 生产版本 + 1），私钥落加密 IndexedDB；
 *   3. 当场 `selfTest` —— 本机都往返不通就不该上行，上行只会把生产版本换掉；
 *   4. 带上 `rotate: true` 把新公钥上报，服务端在一个事务里降级旧版、启用新版；
 *   5. 用响应里的 keyId / keyVersion / chainHash 显示结果，再刷新对账。
 *
 * 为什么整页重写
 * --------------
 * 改造前这里是**用户腿 + 部分刷新**：`useKeyringStore` 里取 uA → 调
 * `/lifecycle/keymanage` 让 KGC 重算部分密钥 → 本机用 `composeUpdatedPrivateKey`
 * 合成新的 d_A → 下载密钥文件。那条路上"密钥"是**用户**的，私钥材料还要靠浏览器
 * 下载一个文件来保存；与 §5.2「节点本地保存 SM2/SSCL/Kyber/Falcon 私钥」不是一回事。
 * 更实际的问题是：那个页面上的「密钥更新」按钮操作的是 `keymanage` 表里的记录，
 * 与节点真正在用、真正要换的那把长期密钥（`NodeLongTermKey`）**根本不是同一行** ——
 * 点完显示"更新成功"，而节点手上的密钥没变，分发照旧用旧版本。
 *
 * 数据来源
 * --------
 * - 平台侧：`GET /node-self/keys/`（本节点的全部长期密钥行，含历史版本）
 * - 本机侧：`cryptoProvider.inspectNodeKeys(nodeId)`（加密 IndexedDB，**按 nodeId 过滤**）
 * 两边对账的口径（配对三元组、公钥比较、五种结论的文案）收在
 * `@/utils/crypto/node-key-compare`，本页只负责渲染。
 *
 * 为什么按钮由**对账结论**而不是权限决定
 * -------------------------------------
 * 「本地私钥存在性」是这一页唯一真正的门禁：对账不是「一致」时更新**必错**——
 * 平台有、本机没有，说明生成这把密钥的是另一台设备，更新过去只会把生产版本
 * 换成一把本机新造的密钥，而已分发的旧信封一把都解不开；公钥对不上则更糟。
 * 权限是另一回事：与生成页同理，`node_self_views` 现在**没有**校验 `CAP_GENERATE`，
 * 前端单方面加门禁会造出「生成页能更新、更新页不能」的自相矛盾。
 */
import { computed, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { CircleCheck } from '@element-plus/icons-vue'
import {
  getSelfNode,
  listSelfNodeKeys,
  NODE_SELF_ERR
} from '@/api/pqkds/node-self'
import {
  RECONCILE,
  activeServerKey,
  compareNodeKeys,
  findLocalKey,
  reconcileRow
} from '@/utils/crypto/node-key-compare.js'
import { KYBER_PK_LENGTHS, cryptoProvider } from '@/utils/crypto/browser-provider.js'
import { deviceFingerprint, hasDeviceKey } from '@/utils/crypto/device-credential.js'
import { IS_DEMO } from '@/utils/entry-mode'
import { generateAndRegisterNodeKey } from '@/utils/node-initialization'
import { formatGenerationName, coreDetail, GENERATION_SCHEMES } from '@/utils/crypto/generation-scheme.js'

const loading = ref(true)
const mapped = ref(false)
const node = ref({})

/** 平台登记的行（`GET /node-self/keys/` 原样） */
const serverKeys = ref([])
/** 本机密钥库里属于**这个节点**的材料 */
const localKeys = ref([])
const hasDeviceCredential = ref(false)
const deviceFingerprintValue = ref('')

/** 正在更新的算法名（同时只允许一个 —— 生成是重计算，且两次更新会互相踩版本号） */
const updating = ref('')
/** 正在自检的 keyRef */
const testing = ref('')
/** keyRef → {ok, detail}，自检结论。不持久化：自检是"此刻这把能不能用" */
const selfTestResults = ref({})

/**
 * 最近一次更新的结果。**刻意不放进 `load()` 会清空的那些状态里** ——
 * 它记的是"这次更新的存证成没成"，一次次刷新之后它仍然是对的事实。
 */
const lastRotate = ref(null)

const ALGO_META = [
  {
    algorithm: 'KYBER',
    label: formatGenerationName('KYBER', GENERATION_SCHEMES.KYBER),
    role: '密钥封装（KEM）：与其它节点协商共享秘密。更新后变体与生产版本保持一致。'
  },
  {
    algorithm: 'SSCL',
    label: 'SSCL',
    role: '国密无证书：封装 SM4 会话密钥。'
  },
  {
    algorithm: 'SM2',
    label: 'SM2',
    role: '国密：封装 SM4 会话密钥。'
  },
  {
    algorithm: 'FALCON',
    label: formatGenerationName('FALCON', GENERATION_SCHEMES.FALCON),
    role: '对分发消息签名与验签。更新它只影响此后的签名，已发出的签名仍按旧版本公钥验证。'
  }
]

// ---------------------------------------------------------------------------
// 载入
// ---------------------------------------------------------------------------
async function load() {
  loading.value = true
  try {
    const data = await getSelfNode()
    mapped.value = Boolean(data?.mapped)
    node.value = data?.node || {}
    if (!mapped.value) {
      serverKeys.value = []
      localKeys.value = []
      return
    }

    // 平台侧与本机侧**各取一次**，哪边失败就说哪边。
    // 合成一次 try 的话，"平台读不到"会表现成"本机密钥全没了" —— 那会诱导
    // 用户去重新生成（而私钥本来好好的，重生成反而会把生产版本换掉）。
    const [platform, local] = await Promise.allSettled([
      listSelfNodeKeys(),
      cryptoProvider.inspectNodeKeys(node.value.nodeId)
    ])

    if (platform.status === 'fulfilled') {
      serverKeys.value = platform.value?.keys || []
    } else {
      serverKeys.value = []
      ElMessage.error(`读取平台登记记录失败：${platform.reason?.message || platform.reason}`)
    }

    if (local.status === 'fulfilled') {
      localKeys.value = local.value?.keys || []
    } else {
      // 密钥库不可用（隐私模式 / 浏览器禁用 IndexedDB）。此处**不能**当成
      // "本机没有" —— 那会让人以为私钥丢了。列空表 + 明确报错。
      // 对本页尤其关键：对账不成立时更新按钮就是禁用的，密钥库读不到会让
      // **整页都更新不了**，必须说清是"读不到"而不是"没有"。
      localKeys.value = []
      ElMessage.error(`读取本机密钥库失败：${local.reason?.message || local.reason}`)
    }

    if (IS_DEMO) return // Demo never creates or consumes standalone device credentials.
    try {
      hasDeviceCredential.value = await hasDeviceKey(node.value.nodeId)
      deviceFingerprintValue.value = await deviceFingerprint(node.value.nodeId)
    } catch {
      hasDeviceCredential.value = false
      deviceFingerprintValue.value = ''
    }
  } catch (error) {
    ElMessage.error(`读取节点信息失败：${error.message}`)
  } finally {
    loading.value = false
  }
}

// ---------------------------------------------------------------------------
// 卡片：按算法对「平台在产的那一版」做对账
// ---------------------------------------------------------------------------
const cards = computed(() =>
  ALGO_META.map((meta) => {
    const active = activeServerKey(serverKeys.value, meta.algorithm)
    // `_long_term_keys_payload` 按 `algorithm, -id` 排，所以同算法的第一行就是
    // 最新的一行 —— 没有在产版本时用它如实显示"最后一版是什么状态"。
    const latest = serverKeys.value.find((r) => r.algorithm === meta.algorithm) || null
    const local = active
      ? findLocalKey(localKeys.value, {
          algorithm: meta.algorithm,
          keyId: active.keyId,
          version: active.keyVersion
        })
      : null
    // 上一次更新可能"本地封存成功、上报失败"。那一版在新一次更新时**直接复用**：
    // 若上一轮其实已经落库（只是响应丢了），复用能让公钥摘要对上、服务端判为幂等
    // 重试；重新生成则摘要不同，会被判成"同 keyId 同版本两把公钥"的真冲突 ——
    // 于是本机多出一把永远用不上的私钥、生产版本指向的 keyRef 在本机查不到，
    // 两个失败都不报错。
    const stagedKey = active
      ? findLocalKey(localKeys.value, {
          algorithm: meta.algorithm,
          keyId: active.keyId,
          version: Number(active.keyVersion) + 1
        })
      : null
    const mine = localKeys.value.filter((k) => k.algorithm === meta.algorithm)
    // 平台还没有这一算法的在产行时，比对的是"这一算法本机有没有材料"，
    // 而不是某一对具体的行 —— 那种情况下结论只能是 LOCAL_ONLY。
    const reconcile = active
      ? reconcileRow(active, local)
      : (mine.length ? reconcileRow(null, mine[mine.length - 1]) : null)

    return {
      ...meta,
      active,
      latest,
      localKey: local,
      stagedKey,
      reconcile,
      // 只有"平台在产的那一把 = 本机这把"才允许更新。其余四种结论各有各的
      // 下一步（见模板里的提示），**都不是"再点一次"**。
      canRotate: Boolean(active) && reconcile?.state === RECONCILE.MATCH,
      localText: local
        ? `有（${local.keyRef}）`
        : (mine.length
            ? `有 ${mine.length} 把，但都不是平台在产的那一版`
            : '无')
    }
  })
)

/** 「这把还能干什么」由服务端下发的两个布尔量拼出，前端不另写状态表。 */
function usableText(row) {
  if (row.allowsNewWork) return '可用于新会话'
  if (row.allowsUnwrap) return '仅可解开旧信封'
  return '不可用'
}

function nextVersionOf(card) {
  return card.active ? Number(card.active.keyVersion) + 1 : null
}

/**
 * Kyber 变体：**从当前生产那一版的公钥反推**，不从页面默认值来。
 *
 * 公钥长度是自描述的（800/1184/1568 → 512/768/1024），与
 * `node_service.store_node_public_key` 推断变体、`wrappers.pk_len_map` 取参数
 * 是同一口径。`securityLevel` 只作兜底（历史行可能没有字节数），再不行才是 768。
 *
 * ⚠️ 变体换了**不会报任何错**：本地生成成功、登记成功、自检也过（自检是自己
 *    封、自己解，两边用的是同一套参数）。看得见的后果只有两个，都不在本次
 *    请求里：节点的抗量子档位被静默改掉（比如 1024 掉成 768），以及服务端记的
 *    `kyber_security_level` 与分发侧按档位选的参数分叉 —— 分叉的表现是
 *    "密文解不开"，而那要等到下一次真实分发才暴露。
 */
function variantOf(row) {
  const byBytes = KYBER_PK_LENGTHS[Number(row?.publicKeyBytes)]
  if (byBytes) return byBytes
  const byLevel = Number(row?.securityLevel)
  if (byLevel === 512 || byLevel === 768 || byLevel === 1024) return byLevel
  return 768
}

// ---------------------------------------------------------------------------
// 表格：平台行 ∪ 本机独有行（对账口径见 node-key-compare）
// ---------------------------------------------------------------------------
const rows = computed(() =>
  compareNodeKeys({ serverKeys: serverKeys.value, localKeys: localKeys.value })
)

// ---------------------------------------------------------------------------
// 设备一致性提示
// ---------------------------------------------------------------------------
const deviceWarning = computed(() => {
  if (IS_DEMO) return null
  const bound = String(node.value.keyDeviceId || '').trim()
  // 服务端还没绑定设备 → 这台就是"第一台"，上报会把本机绑上去。
  if (!bound) return null
  if (!hasDeviceCredential.value) {
    return {
      title: '本机没有该节点的设备凭据',
      detail: '该节点的密钥是在另一台设备上生成的，上报公钥会被平台按「设备不一致」拒绝。请改回原设备，或在「节点首次初始化」里用本机重新生成一套。'
    }
  }
  // 私钥在，但公钥读不出来（记录损坏）。这与"换设备"不同：能做的只有重新激活。
  if (!deviceFingerprintValue.value) {
    return {
      title: '本机的设备凭据读不出公钥',
      detail: '该节点的设备私钥在，但对应的公钥记录损坏。上报公钥会被平台按「设备不一致」拒绝，需要重新激活该节点。'
    }
  }
  if (deviceFingerprintValue.value !== bound) {
    return {
      title: '本机设备与平台绑定的不是同一台',
      detail: '本机持有一个设备凭据，但与平台记录的不是同一台设备。上报公钥同样会被拒绝，请确认是否用过另一个浏览器配置或另一台机器。'
    }
  }
  return null
})

// ---------------------------------------------------------------------------
// 更新
// ---------------------------------------------------------------------------
function selfTestOf(card) {
  const ref = selfTestKeyRef(card)
  return ref ? selfTestResults.value[ref] : null
}

/** 自检对象：优先平台在产那一版对应的本机材料；没有则用本机最新的一把。 */
function selfTestKeyRef(card) {
  if (card.localKey) return card.localKey.keyRef
  if (card.stagedKey) return card.stagedKey.keyRef
  const mine = localKeys.value.filter((k) => k.algorithm === card.algorithm)
  return mine.length ? mine[mine.length - 1].keyRef : ''
}

/**
 * 把当前生产版本更新到下一版。
 *
 * 顺序不可调换：**先本地封存、再自检、最后才上报**。
 * 反过来（先上报再生成）如果本地这一步失败，平台上生产版本已经换成了一个
 * 本机没有私钥的 keyRef —— 那正是 `KEY_VERSION_MISMATCH` 想防的那类状态，
 * 而且此时**没有任何接口能把它改回去**（版本只增不减）。
 *
 * ⚠️ `keyId` 沿用生产版本那一把、`version` 是它 +1，两个都必须原样转发
 *    `generate()` / 本机已封存记录的返回值。服务端不替调用方算版本：算出来的
 *    那一版与本地封存的可能不是同一个，于是本机多出一把永远用不上的私钥，
 *    而生产版本指向的 keyRef 在本机查不到 —— 两个失败都不报错。
 */
async function handleRotate(card) {
  if (updating.value || !card.active) return
  const active = card.active
  const nextVersion = Number(active.keyVersion) + 1
  updating.value = card.algorithm
  lastRotate.value = null
  try {
    // Shared workflow re-reads production identity, recovers sealed next version,
    // self-tests and renews ONLY expired registration authorization (never KeyGen).
    const { material, result, check, reused } = await generateAndRegisterNodeKey({
      algorithm: card.algorithm, nodeId: node.value.nodeId,
      keyId: active.keyId, version: nextVersion, rotate: true,
      variant: card.algorithm === 'KYBER' ? variantOf(active) : undefined,
      confirmUnusedIssuance: async record => {
        await ElMessageBox.confirm(record.message, '确认恢复未完成签发', { type: 'warning', confirmButtonText: '弃用未使用签发并重试', cancelButtonText: '取消，不换钥' })
        return true
      }
    })
    selfTestResults.value = { ...selfTestResults.value, [material.keyRef]: check }

    lastRotate.value = {
      algorithm: card.algorithm,
      label: formatGenerationName(card.algorithm, material.generation),
      keyId: result?.keyId || material.keyId,
      fromVersion: Number(active.keyVersion),
      toVersion: Number(result?.keyVersion || material.version),
      keyStatus: result?.keyStatus || '',
      chainHash: result?.chainHash || '',
      keyRef: material.keyRef,
      selfTestOk: check.ok,
      selfTestDetail: check.detail,
      reused: Boolean(reused)
    }

    await load()

    // 「已更新」与「已上链」分开说。存证是旁路增强（`record_chain_event` 失败
    // 只返回空串），合成一句"更新成功"会把审计缺口盖掉 —— 之后谁也说不清
    // 这一次更新到底有没有留痕。
    const head = `${card.label} 已更新：v${lastRotate.value.fromVersion} → v${lastRotate.value.toVersion}`
    if (lastRotate.value.chainHash) {
      ElMessage.success(`${head}；存证已上链`)
    } else {
      ElMessage.warning(`${head}；但存证未成功（更新本身已生效，链上少一条 KEY_UPDATED）`)
    }
  } catch (error) {
    ElMessage.error(`${card.label} 更新失败：${describeError(error, card)}`)
    // ⚠️ 失败之后**必须**刷新对账，这不是为了界面好看。
    //
    // `stagedKey` 是从 `load()` 写下的 `localKeys` 推导的（第 466 行），只有 `load()`
    // 会更新它。而"响应丢失"是一条**真实**路径：POST 已经被服务端提交（在产版本
    // 已切、物化列已换），提交与响应之间还夹着一次链上存证调用，链上服务一慢，
    // 浏览器看到的就是超时/错误。
    //
    // 不刷新的话 `stagedKey` 仍是 null，用户再点一次「更新」会**再生成一把 v+1**，
    // 而 `sealSecret` 对同一个 keyRef 是无条件 `put`（`node-key-store.js:146`
    // 自己写明这是"静默覆盖"）—— 本机那把与服务端在产公钥配对的私钥就此被销毁。
    // 后果不可恢复：版本只增不减，新公钥与服务端已存的那把不同，重试被
    // KEY_VERSION_MISMATCH 拒，对账从此恒为 MISMATCH，这一把再也更新不了。
    //
    // 刷新后 `stagedKey` 会命中刚封存的那一版，重试复用同一把公钥 ——
    // 服务端走幂等分支返回已有行，整条恢复路径才成立（后端 `retry_same_version`
    // 那一支正是为它准备的）。
    try {
      await load()
    } catch {
      // 刷新失败不该把上面那条真正的错误盖掉；本地密钥来自 IndexedDB，
      // 即便平台读不到，`stagedKey` 一般也已经能对上。
    }
  } finally {
    updating.value = ''
  }
}

/** 自检：用本地这份材料真跑一轮往返。失败**不抛错**（`selfTest` 把失败当结论返回）。 */
async function runSelfTest(algorithm, keyRef) {
  if (!keyRef || testing.value) return
  testing.value = keyRef
  try {
    const result = await cryptoProvider.selfTest(algorithm, keyRef)
    selfTestResults.value = { ...selfTestResults.value, [keyRef]: result }
  } finally {
    testing.value = ''
  }
}

/**
 * 把失败翻译成"下一步该做什么"。
 *
 * 分支**按错误码**，不按文案：`error.errorCode` 来自冻结契约
 * （`api_contract.ERR_*`，经 `@/api/pqkds/http` 附在错误对象上），
 * 文案改了也不会让分支走错。
 *
 * `KEY_VERSION_MISMATCH` 一个码对应三种触发（同 keyId 两把公钥 / 版本回退或跨越 /
 * 更新的不是生产那把），**下一步各不相同**，所以把服务端那句具体说明留在前面，
 * 只补一句"这一码的通用规则"，不替它猜是哪一种。
 */
function describeError(error, card) {
  const message = error?.message || String(error)
  switch (error?.errorCode) {
    case NODE_SELF_ERR.KEYGEN_POLICY_DISABLED:
      return '双份额生成尚未启用：需完成独立密码学验证并由运维显式启用；不会降级为普通生成'
    case NODE_SELF_ERR.KEYGEN_CONTEXT_MISMATCH:
      return `${message}。身份或设备上下文已变化；请返回原身份恢复，不会自动换钥`
    case NODE_SELF_ERR.KEYGEN_GENERATION_REQUIRED:
      return `${message}。请明确恢复历史材料，不能补造双份额来源`
    case NODE_SELF_ERR.KEY_REVOKED:
      return `${message}。回收是终态，更新救不回来 —— 请到「密钥生成」为 ${card.label} 生成一把新的（新 keyId）`
    case NODE_SELF_ERR.KEY_NOT_FOUND:
      return `${message}。本机这把在平台上没有登记记录，请先到「密钥生成」完成登记，再回来更新`
    case NODE_SELF_ERR.KEY_VERSION_MISMATCH:
      return `${message}。版本只允许"等于最新（重试）"或"逐版 +1"；若提示的是生产版本属于别的 keyId，请点「刷新」后基于生产版本重做`
    case NODE_SELF_ERR.DEVICE_MISMATCH:
      return `${message}。本机不是该节点绑定的设备：请改回原设备，或在「节点首次初始化」里用本机重新生成一套`
    case NODE_SELF_ERR.INVALID_PARAMETER:
      return `${message}。请刷新页面后重试；若反复出现，把本地 keyRef 与平台记录的 keyId 一并提供给运维`
    case NODE_SELF_ERR.ALGORITHM_NOT_ALLOWED:
      return `${message}。平台只接受 SM2 / SSCL / KYBER / FALCON 四个规范名`
    default:
      return message
  }
}

function formatTime(value) {
  if (!value) return '—'
  // 后端下发 ISO（`_iso`）。按本机时间展示，不换算时区 —— 与其它节点侧页面一致。
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  const pad = (n) => String(n).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`
}

onMounted(load)
</script>

<style scoped>
.key-update__card { max-width: 1180px; margin: 24px auto; }
.key-update__header { display: flex; align-items: center; justify-content: space-between; }
.key-update__header h2 { margin: 0; font-size: 18px; }
.key-update__header-side { display: flex; align-items: center; gap: 8px; }
.key-update__lead { margin: 0 0 16px; color: var(--kms-text-secondary, #606266); line-height: 1.7; }
.key-update__device { margin-bottom: 16px; }
.key-update__device p { margin: 6px 0 0; line-height: 1.7; }
.key-update__grid {
  display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
  gap: 12px; margin-bottom: 20px;
}
.key-update__algo {
  border: 1px solid var(--el-border-color, #dcdfe6); border-radius: 6px;
  padding: 12px 14px; display: flex; flex-direction: column; gap: 8px;
}
.key-update__algo.is-active { border-color: var(--el-color-success, #67c23a); }
.key-update__algo.is-warn { border-color: var(--el-color-danger, #f56c6c); }
.key-update__algo-head { display: flex; align-items: center; justify-content: space-between; }
.key-update__algo-name { font-weight: 600; }
.key-update__algo-role { margin: 0; font-size: 12px; color: var(--kms-text-secondary, #909399); line-height: 1.6; }
.key-update__facts { margin: 0; }
.key-update__fact { display: flex; gap: 8px; font-size: 12px; line-height: 1.9; }
.key-update__fact dt { color: var(--kms-text-secondary, #909399); flex: 0 0 60px; }
.key-update__fact dd { margin: 0; word-break: break-all; }
.key-update__fact-note { color: var(--kms-text-secondary, #909399); margin-left: 6px; }
.key-update__reconcile { margin: 4px 0; }
.key-update__pending { font-size: 12px; color: var(--el-color-warning, #e6a23c); line-height: 1.6; }
.key-update__match { display: flex; align-items: center; gap: 6px; font-size: 12px; color: var(--el-color-success, #67c23a); }
.key-update__selftest { font-size: 12px; line-height: 1.6; word-break: break-all; }
.key-update__algo-actions { display: flex; align-items: center; gap: 8px; margin-top: auto; flex-wrap: wrap; }
.key-update__variant-note { font-size: 12px; color: var(--kms-text-secondary, #909399); }
.key-update__result {
  border: 1px solid var(--el-color-success, #67c23a); border-radius: 6px;
  padding: 12px 14px; margin-bottom: 20px;
}
.key-update__result-head { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; flex-wrap: wrap; }
.key-update__result-title { font-weight: 600; }
.key-update__note {
  margin: 0 0 24px; padding: 10px 14px; border-radius: 6px;
  background: var(--el-fill-color-light, #f5f7fa);
  font-size: 13px; color: var(--kms-text-secondary, #606266); line-height: 1.8;
}
.key-update__section-title { margin: 0 0 12px; font-size: 15px; }
.key-update__section-note { margin-left: 8px; font-size: 12px; font-weight: 400; color: var(--kms-text-secondary, #909399); }
.key-update__table { margin-bottom: 12px; }
.key-update__empty { margin: 0; color: var(--kms-text-secondary, #909399); font-size: 13px; }
.mono { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
.is-ok { color: var(--el-color-success, #67c23a); }
.is-bad { color: var(--el-color-danger, #f56c6c); }
.is-muted { color: var(--kms-text-secondary, #909399); }
</style>
