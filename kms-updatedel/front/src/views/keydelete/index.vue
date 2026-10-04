<template>
  <div class="app-container key-revoke">
    <el-card shadow="never" class="key-revoke__card">
      <template #header>
        <div class="key-revoke__header">
          <h2>密钥回收</h2>
          <div class="key-revoke__header-side">
            <el-tag v-if="node.nodeId" type="info" size="small">{{ node.nodeId }}</el-tag>
            <el-button size="small" :loading="loading" @click="load">刷新</el-button>
          </div>
        </div>
      </template>

      <!-- 账号没关联节点：管理员账号，或数据异常。与「密钥更新」同一判据。 -->
      <el-alert
        v-if="!loading && !mapped"
        type="warning"
        :closable="false"
        show-icon
        title="当前账号未关联任何节点"
        description="回收是节点对自己长期密钥的动作。请用节点账号登录。"
      />

      <template v-else>
        <p class="key-revoke__lead">
          本页回收的是<strong>本节点</strong>在平台上登记的长期密钥，每次回收
          <strong>必须同时指定 keyId 与版本</strong> —— 不存在"回收这把密钥的最新版"这种隐式操作。
          列表里的状态与可用性都来自服务端下发，页面不另做判断。
        </p>

        <el-alert
          class="key-revoke__notice"
          type="warning"
          :closable="false"
          show-icon
          title="回收是终态"
          description="回收后该版本不能更新，也不能用于新分发、新签名、新预分配、新会话。回收还会处置受影响的对象（未消费的池项、依赖它的会话），每次回收的实际影响面在下方结果里如实列出。"
        />

        <!-- 后端一次最多回 200 行且没有分页参数。到顶时必须说出来：
             不说的话页面看起来"就这些"，而少掉的那些是更早的版本，可能还有在产行。 -->
        <el-alert
          v-if="possiblyTruncated"
          class="key-revoke__notice"
          type="info"
          :closable="false"
          show-icon
          :title="`只显示了最近 ${SERVER_ROW_LIMIT} 条`"
          description="本节点登记过的密钥行数达到接口上限，更早的版本没有列出来。需要完整历史请直接查服务端 dvadmin_pqkds_node_long_term_keys 表。"
        />

        <el-row :gutter="10" class="key-revoke__toolbar">
          <el-button
            type="danger"
            plain
            icon="Delete"
            :disabled="!selected.length || revoking"
            :loading="revoking"
            @click="openRevoke()"
          >回收所选密钥</el-button>
          <span class="key-revoke__toolbar-note">
            只有仍可用于新工作（allowsNewWork）的行能勾选；已被取代、已回收的行只作展示
          </span>
        </el-row>

        <el-form inline class="key-revoke__filter" @submit.prevent>
          <el-form-item label="算法">
            <el-select v-model="algoFilter" clearable placeholder="全部" class="key-revoke__filter-select">
              <el-option v-for="a in algorithmOptions" :key="a" :label="a" :value="a" />
            </el-select>
          </el-form-item>
          <el-form-item label="状态">
            <el-select v-model="statusFilter" clearable placeholder="全部" class="key-revoke__filter-select">
              <el-option v-for="o in statusOptions" :key="o.value" :label="o.label" :value="o.value" />
            </el-select>
          </el-form-item>
          <el-form-item label="keyId">
            <el-input v-model="keyword" clearable placeholder="包含匹配" style="width: 200px" />
          </el-form-item>
          <el-form-item>
            <el-button @click="resetFilters">重置</el-button>
          </el-form-item>
        </el-form>

        <el-table v-loading="loading" :data="filtered" size="small" border @selection-change="handleSelectionChange">
          <el-table-column type="selection" width="46" align="center" :selectable="canRevoke" />
          <el-table-column label="算法" width="92" prop="algorithm" />
          <el-table-column label="keyId" min-width="200" show-overflow-tooltip>
            <template #default="{ row }">
              <span class="mono">{{ row.keyId || '（未记录）' }}</span>
            </template>
          </el-table-column>
          <el-table-column label="版本" width="70">
            <template #default="{ row }">v{{ row.keyVersion }}</template>
          </el-table-column>
          <el-table-column label="状态" width="116">
            <template #default="{ row }">
              <el-tag :type="statusTagType(row.status)" size="small">{{ row.statusLabel }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="可用性" width="132">
            <template #default="{ row }">{{ usableText(row) }}</template>
          </el-table-column>
          <el-table-column label="生效时间" width="150">
            <template #default="{ row }">{{ formatTime(row.effectiveAt || row.createdAt) }}</template>
          </el-table-column>
          <el-table-column label="回收时间" width="150">
            <template #default="{ row }">{{ formatTime(row.revokedAt) }}</template>
          </el-table-column>
          <el-table-column label="回收原因" min-width="140" show-overflow-tooltip>
            <template #default="{ row }">{{ row.revokedReason || '—' }}</template>
          </el-table-column>
          <el-table-column label="操作" width="80" fixed="right">
            <template #default="{ row }">
              <el-button
                v-if="canRevoke(row)"
                link
                type="danger"
                size="small"
                :disabled="revoking"
                @click="openRevoke(row)"
              >回收</el-button>
              <span v-else class="is-muted">—</span>
            </template>
          </el-table-column>
        </el-table>
        <p v-if="!loading && !filtered.length" class="key-revoke__empty">
          {{ rows.length ? '没有符合筛选条件的密钥。' : '这个节点还没有登记过任何长期密钥。' }}
        </p>

        <!-- 最近一次回收的结果。**不随刷新清掉** —— 影响面（失效了多少池项、多少会话）
             必须在页面上留得住：弹一条消息就消失的话，"密钥已回收、会话还活着"
             这条结论会跟着一起消失，而它正是用户接下来要不要处置的依据。 -->
        <div v-if="lastRevoke" class="key-revoke__result">
          <div class="key-revoke__result-head">
            <span class="key-revoke__result-title">最近一次回收</span>
            <span class="key-revoke__result-note">{{ formatTime(lastRevoke.at) }} · 原因：{{ lastRevoke.reason }}</span>
          </div>
          <div
            v-for="r in lastRevoke.results"
            :key="`${r.algorithm}/${r.keyId}/v${r.keyVersion}`"
            class="key-revoke__result-row"
          >
            <el-icon v-if="r.ok" class="is-ok"><CircleCheck /></el-icon>
            <el-icon v-else class="is-bad"><CircleClose /></el-icon>
            <span class="mono key-revoke__result-key">{{ r.algorithm }} {{ r.keyId }} v{{ r.keyVersion }}</span>
            <template v-if="r.ok">
              <span class="key-revoke__result-detail">
                已回收<template v-if="impactOf(r.data)">；失效池项 <strong>{{ impactOf(r.data).poolItems }}</strong> 条、会话 <strong>{{ impactOf(r.data).sessions }}</strong> 个</template><template v-else>；<span class="is-bad">服务端未回报影响面</span>（不能当作 0 —— 请查服务端日志确认池项与会话状态）</template>
              </span>
              <el-tag v-if="chainOf(r.data)" size="small" :type="chainOf(r.data).type">
                {{ chainOf(r.data).label }}
              </el-tag>
            </template>
            <span v-else class="key-revoke__result-detail is-bad">{{ describeError(r.error) }}</span>
          </div>
        </div>
      </template>
    </el-card>
  </div>
</template>

<script setup name="KeyDelete">
/**
 * 密钥回收（菜单 7000，节点端 `/keydelete/index`）。
 *
 * 改造前，这一页打在 updatedel 旧 `keymanage` 模型上（`listKeymanage` /
 * `DELETE /lifecycle/keymanage/{keyId}`）：点「回收」删的是那条链的旧行，
 * 节点真正在用的长期密钥（`NodeLongTermKey`）原样不动 —— 页面显示成功，
 * 密钥没变。与 KMS-006 之前更新页的问题同源，这次修的是回收这一半。
 *
 * 现在：
 * - 列表读 `GET /node-self/keys/`（本节点全部长期密钥行，**刻意不过滤状态**，
 *   所以被取代/已回收的历史版本也在表里，只是不可勾选）；
 * - 回收调 `POST /node-self/keys/revoke/`，**keyId 与 keyVersion 一起提交** ——
 *   服务端不接受"取最新一把"的隐式行为（KMS-006 定下的纪律）。提交的两个值
 *   就是列表行上的原值，不在前端做任何"补算"。
 *
 * 为什么只有 `allowsNewWork` 的行可回收
 * ------------------------------------
 * 已被取代（RETIRED）的版本仍需要解开按它分发出去的旧信封，回收它会让那些
 * 信封再也解不开；已回收的行是终态，重复提交没有意义。这两类行仍然
 * **显示**（状态文案来自服务端 `statusLabel`），但不可勾选。
 *
 * 为什么状态与可用性不写在前端
 * --------------------------
 * 铁律：`statusLabel` / `allowsNewWork` / `allowsUnwrap` 一律用服务端下发的。
 * 前端另写一份中文状态表或可用性判断，两份必然漂移，而漂移的表现是
 * "界面写着当前版本、实际已被取代"——用户据此做的判断全是错的，且不会有任何
 * 一处报错。这里唯一的本地判断是 `status → 标签颜色`，它不影响任何语义。
 */
import { computed, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { CircleCheck, CircleClose } from '@element-plus/icons-vue'
import {
  getSelfNode,
  listSelfNodeKeys,
  revokeSelfNodePublicKey,
  NODE_SELF_ERR
} from '@/api/pqkds/node-self'

/**
 * 后端 `_long_term_keys_payload(node, limit=200)` 的条数上限，**与后端同改**。
 * 只用来在到顶时提醒"可能被截断"，不参与分页 —— 接口本身没有分页参数，
 * 前端私自分页只会让人以为数据全在。
 */
const SERVER_ROW_LIMIT = 200

/**
 * 状态 → 标签颜色。**只有颜色**是前端的：文案一律用服务端下发的 `statusLabel`
 * （`api_contract.KEY_STATUS_CHOICES`）。与「密钥历史」页同一张表，避免两页配色分叉。
 */
const STATUS_TAG_TYPE = { ACTIVE: 'success', PENDING: 'warning', REVOKED: 'danger' }

const loading = ref(true)
const mapped = ref(false)
const node = ref({})
const rows = ref([])
const selected = ref([])

const revoking = ref(false)
/** 最近一次回收的结果，含影响面。不放进 `load()` 会清空的那些状态里（见模板注释）。 */
const lastRevoke = ref(null)

const algoFilter = ref('')
const statusFilter = ref('')
const keyword = ref('')

async function load() {
  loading.value = true
  try {
    const data = await getSelfNode()
    mapped.value = Boolean(data?.mapped)
    node.value = data?.node || {}
    if (!mapped.value) {
      rows.value = []
      return
    }
    try {
      const payload = await listSelfNodeKeys()
      rows.value = payload?.keys || []
    } catch (error) {
      // 读不到与"没有密钥"是两回事：后者会诱导用户去重新生成，
      // 而密钥本来好好的。所以列空表 + 明确报错，不静默。
      rows.value = []
      ElMessage.error(`读取平台登记记录失败：${error.message}`)
    }
  } catch (error) {
    ElMessage.error(`读取节点信息失败：${error.message}`)
  } finally {
    loading.value = false
  }
}

const possiblyTruncated = computed(() => rows.value.length >= SERVER_ROW_LIMIT)

/** 算法选项从已载入的数据派生 —— 写死一份清单会在服务端新增算法时静默漏掉。 */
const algorithmOptions = computed(() => [...new Set(rows.value.map((r) => r.algorithm).filter(Boolean))].sort())

/** 状态选项同样从数据派生，label 直接用服务端下发的 statusLabel。 */
const statusOptions = computed(() => {
  const seen = new Map()
  for (const row of rows.value) {
    if (row.status) seen.set(row.status, row.statusLabel || row.status)
  }
  return [...seen].map(([value, label]) => ({ value, label }))
})

const filtered = computed(() =>
  rows.value.filter((row) => {
    if (algoFilter.value && row.algorithm !== algoFilter.value) return false
    if (statusFilter.value && row.status !== statusFilter.value) return false
    if (keyword.value) {
      const wanted = keyword.value.trim().toLowerCase()
      if (wanted && !String(row.keyId || '').toLowerCase().includes(wanted)) return false
    }
    return true
  })
)

function resetFilters() {
  algoFilter.value = ''
  statusFilter.value = ''
  keyword.value = ''
}

function handleSelectionChange(selection) {
  selected.value = selection
}

/** 可回收判据 = 服务端下发的 `allowsNewWork`，前端不做第二份可用性判断。 */
function canRevoke(row) {
  return row?.allowsNewWork === true
}

function statusTagType(status) {
  return STATUS_TAG_TYPE[status] || 'info'
}

/** 「这把还能干什么」由服务端下发的两个布尔量拼出，前端不另写状态表。 */
function usableText(row) {
  if (row.allowsNewWork) return '可用于新会话'
  if (row.allowsUnwrap) return '仅可解开旧信封'
  return '不可用'
}

/**
 * 影响面计数。服务端没回报 `impact` 时返回 null，**不收敛成 0** ——
 * "没有影响"与"没人告诉你有没有影响"是两条不同的结论，
 * 把后者显示成前者正好是本页要防的静默错误。
 */
function impactOf(data) {
  const impact = data?.impact
  if (!impact) return null
  const toText = (v) => (Number.isFinite(Number(v)) ? Number(v) : '—')
  return { poolItems: toText(impact.poolItems), sessions: toText(impact.sessions) }
}

/**
 * 存证结论，**三态**。只在响应里真的带了这个字段时才给结论：该端点的最终响应
 * 形状由并发的后端线定稿（见 doc/kms-007-lane-frontend.md 的未验证清单），
 * 这里不做"没带字段 = 存证失败"的推断 —— 那会把一次成功回收播报成审计缺口。
 *
 * ⚠️ 为什么不能只看 `chainHash` 是否为空串
 * ----------------------------------------
 * `chainHash` 空串有**两种**含义，而它们要做的处置完全相反：
 *
 *   * `alreadyRevoked: false` —— 本次才把密钥转入终态，却没拿到链上哈希：
 *     真的是一次审计缺口，必须显示。
 *   * `alreadyRevoked: true` —— 本次是**重试**（上一次回收后池项/会话没处理完，
 *     服务端刻意不早返回，见 key_revocation_service 的说明）。这种状态下服务端
 *     **故意不重复上链**：同一次回收在链上留多条 KEY_REVOKED，"回收了几次"
 *     就没有可信答案了。所以空串在这里是**正确行为**，不是失败。
 *
 * 把它一律读成"存证未成功"，就会在一条设计内的恢复路径上（重试是正常路径，
 * 不是异常路径）报出一个不存在的审计缺口 —— 这类假警报比不报警更糟：
 * 它会让人去追一个根本没丢的记录，而真正的缺口被这种噪音淹没。
 * 判别所需的信息就在响应里（`revoked.alreadyRevoked`），不需要服务端再加字段。
 */
function chainOf(data) {
  if (!data || !Object.prototype.hasOwnProperty.call(data, 'chainHash')) return null
  if (data.revoked && data.revoked.alreadyRevoked === true) {
    return { label: '无需重复存证（上次回收已上链）', type: 'info' }
  }
  return Boolean(data.chainHash)
    ? { label: '存证已上链', type: 'success' }
    : { label: '存证未成功', type: 'warning' }
}

/** 汇总一次批量回收的影响面；有任何一把没回报就退回"见下方结果"，不拼一个偏小的数。 */
function impactSummary(okResults) {
  let pool = 0
  let sessions = 0
  for (const r of okResults) {
    const impact = impactOf(r.data)
    if (!impact || typeof impact.poolItems !== 'number' || typeof impact.sessions !== 'number') {
      return '影响面见页面下方结果'
    }
    pool += impact.poolItems
    sessions += impact.sessions
  }
  return `失效池项 ${pool} 条、会话 ${sessions} 个`
}

/**
 * 打开回收确认。row 缺省表示回收当前勾选的行。
 *
 * 回收原因由用户填写（预填一个默认值，改不改都行）：它会写进 `revokedReason`
 * 并出现在版本历史页上，是事后唯一能回答"为什么回收"的字段。
 */
async function openRevoke(row) {
  if (revoking.value) return
  const targets = (row ? [row] : selected.value).filter(canRevoke)
  if (!targets.length) {
    ElMessage.warning('请先勾选仍可用于新工作的密钥')
    return
  }
  const list = targets.map((t) => `${t.algorithm} ${t.keyId} v${t.keyVersion}`).join('、')
  let reason
  try {
    const { value } = await ElMessageBox.prompt(
      `将回收 ${targets.length} 把密钥：${list}。回收是终态，且会失效相关池项与会话。`,
      '密钥回收',
      {
        confirmButtonText: '确认回收',
        cancelButtonText: '取消',
        type: 'warning',
        inputValue: '节点侧主动回收',
        inputPlaceholder: '回收原因（会写入 revokedReason）',
        inputValidator: (v) => (String(v || '').trim() ? true : '回收原因不能为空')
      }
    )
    reason = String(value).trim()
  } catch {
    return // 用户取消
  }
  await doRevoke(targets, reason)
}

async function doRevoke(targets, reason) {
  revoking.value = true
  try {
    const results = []
    for (const t of targets) {
      try {
        // 算法名一并带上：服务端按 (节点, 算法, keyId, 版本) 定位那一行，
        // 且**刻意**不替调用方推断算法（keyId 跨算法不保证唯一）。这一行
        // 本来就渲染着算法名，原样回传即可。
        const data = await revokeSelfNodePublicKey(t.algorithm, t.keyId, t.keyVersion, reason)
        results.push({
          algorithm: t.algorithm,
          keyId: t.keyId,
          keyVersion: t.keyVersion,
          ok: true,
          data: data || {}
        })
      } catch (error) {
        // 逐把收集失败，不中断整批：已成功的那些必须如实报出来，
        // 否则用户会重试一遍已经回收成功的密钥。
        results.push({
          algorithm: t.algorithm,
          keyId: t.keyId,
          keyVersion: t.keyVersion,
          ok: false,
          error
        })
      }
    }
    lastRevoke.value = { at: new Date().toISOString(), reason, results }

    const okResults = results.filter((r) => r.ok)
    const failed = results.filter((r) => !r.ok)
    if (failed.length) {
      ElMessage.error(`回收完成：成功 ${okResults.length} 把、失败 ${failed.length} 把 —— 失败原因见页面下方结果`)
    } else {
      ElMessage.success(`已回收 ${okResults.length} 把；${impactSummary(okResults)}`)
    }

    await load()
  } finally {
    revoking.value = false
  }
}

/**
 * 把失败翻译成"下一步该做什么"。分支**按错误码**，不按文案：
 * `error.errorCode` 来自冻结契约（`api_contract.ERR_*`，经 `@/api/pqkds/http`
 * 附在错误对象上），文案改了也不会让分支走错。只映射本页真正会分支处理的几个码。
 */
function describeError(error) {
  const message = error?.message || String(error)
  switch (error?.errorCode) {
    case NODE_SELF_ERR.KEY_REVOKED:
      return `${message}。该版本已是「已回收」终态，重复回收不会产生新的影响；请刷新后核对列表`
    case NODE_SELF_ERR.KEY_NOT_FOUND:
      return `${message}。本节点没有这一行登记记录 —— 列表可能已过期，请刷新后重选`
    case NODE_SELF_ERR.KEY_VERSION_MISMATCH:
      return `${message}。提交的是列表里看到的 keyId + 版本；出现这一码说明页面上的行与服务端已不一致，请刷新后重选`
    case NODE_SELF_ERR.INVALID_PARAMETER:
      return `${message}。请刷新后重试；若反复出现，把页面上的 keyId 与版本一并提供给运维`
    default:
      return message
  }
}

function formatTime(value) {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return String(value)
  const pad = (n) => String(n).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`
}

onMounted(load)
</script>

<style scoped>
.key-revoke__card { max-width: 1320px; margin: 24px auto; }
.key-revoke__header { display: flex; align-items: center; justify-content: space-between; }
.key-revoke__header h2 { margin: 0; font-size: 18px; }
.key-revoke__header-side { display: flex; align-items: center; gap: 8px; }
.key-revoke__lead { margin: 0 0 16px; color: var(--kms-text-secondary, #606266); line-height: 1.7; }
.key-revoke__notice { margin-bottom: 12px; }
.key-revoke__toolbar { display: flex; align-items: center; gap: 12px; margin-bottom: 8px; }
.key-revoke__toolbar-note { font-size: 12px; color: var(--kms-text-secondary, #909399); }
.key-revoke__filter { margin-bottom: 4px; }
.key-revoke__filter-select { width: 160px; }
.key-revoke__empty { margin: 12px 0 0; color: var(--kms-text-secondary, #909399); font-size: 13px; }
.key-revoke__result {
  margin-top: 20px; padding: 12px 14px; border-radius: 6px;
  border: 1px solid var(--el-border-color, #dcdfe6);
}
.key-revoke__result-head { display: flex; align-items: baseline; gap: 12px; margin-bottom: 8px; flex-wrap: wrap; }
.key-revoke__result-title { font-weight: 600; }
.key-revoke__result-note { font-size: 12px; color: var(--kms-text-secondary, #909399); }
.key-revoke__result-row {
  display: flex; align-items: baseline; gap: 8px; padding: 4px 0;
  font-size: 13px; line-height: 1.7; flex-wrap: wrap;
}
.key-revoke__result-key { flex: 0 0 auto; }
.key-revoke__result-detail { flex: 1 1 320px; word-break: break-all; }
.mono { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
.is-ok { color: var(--el-color-success, #67c23a); }
.is-bad { color: var(--el-color-danger, #f56c6c); }
.is-muted { color: var(--kms-text-secondary, #909399); }
</style>
