<template>
  <div class="app-container version-history">
    <el-card shadow="never" class="version-history__card">
      <template #header>
        <div class="version-history__header">
          <h2>版本历史</h2>
          <div class="version-history__header-side">
            <el-tag v-if="node.nodeId" type="info" size="small">{{ node.nodeId }}</el-tag>
            <el-button size="small" :loading="loading" @click="load">刷新</el-button>
          </div>
        </div>
      </template>

      <!-- 账号没关联节点：管理员账号，或数据异常。与「密钥更新」「密钥回收」同一判据。 -->
      <el-alert
        v-if="!loading && !mapped"
        type="warning"
        :closable="false"
        show-icon
        title="当前账号未关联任何节点"
        description="版本历史是节点自己长期密钥的记录。请用节点账号登录。"
      />

      <template v-else>
        <p class="version-history__lead">
          本节点<strong>每一把</strong>长期密钥的全部版本，按 keyId 分组、最新在前。
          更新与回收都不会让旧版本消失：被取代的版本仍要能解开按它分发出去的旧信封，
          已回收的版本是终态 —— 两者都留在这里可查，状态与可用性均来自服务端下发。
        </p>

        <!-- 后端一次最多回 200 行且没有分页参数，到顶必须说出来：
             被截掉的正是更早的版本，而"看不见"会被当成"不存在"。 -->
        <el-alert
          v-if="possiblyTruncated"
          class="version-history__notice"
          type="info"
          :closable="false"
          show-icon
          :title="`只显示了最近 ${SERVER_ROW_LIMIT} 条`"
          description="本节点登记过的密钥行数达到接口上限，更早的版本没有列出来。需要完整历史请直接查服务端 dvadmin_pqkds_node_long_term_keys 表。"
        />

        <el-form inline class="version-history__filter" @submit.prevent>
          <el-form-item label="keyId">
            <el-input v-model="keyword" clearable placeholder="包含匹配" style="width: 220px" />
          </el-form-item>
          <el-form-item label="算法">
            <el-select v-model="algoFilter" clearable placeholder="全部" class="version-history__filter-select">
              <el-option v-for="a in algorithmOptions" :key="a" :label="a" :value="a" />
            </el-select>
          </el-form-item>
          <el-form-item>
            <el-button @click="resetFilters">重置</el-button>
          </el-form-item>
          <el-form-item v-if="rows.length">
            <span class="version-history__summary">共 {{ groups.length }} 把密钥 · {{ filteredRows.length }} 个版本</span>
          </el-form-item>
        </el-form>

        <p v-if="!loading && !groups.length" class="version-history__empty">
          {{ rows.length ? '没有符合筛选条件的密钥。' : '这个节点还没有登记过任何长期密钥。' }}
        </p>

        <section v-for="g in groups" :key="g.key" class="version-history__group">
          <div class="version-history__group-head">
            <span class="mono version-history__group-keyid">{{ g.keyId || '（未记录 keyId）' }}</span>
            <el-tag size="small" effect="plain">{{ g.algorithm }}</el-tag>
            <!-- 最新一版的状态：它回答"这把密钥现在是什么处境"。
                 文案来自服务端 `statusLabel`，前端只决定颜色。 -->
            <el-tag :type="statusTagType(g.latest.status)" size="small">{{ g.latest.statusLabel }}</el-tag>
            <span class="version-history__group-note">{{ g.rows.length }} 个版本 · 最新在前</span>
          </div>
          <el-table :data="g.rows" size="small" border>
            <el-table-column label="版本" width="80">
              <template #default="{ row }">v{{ row.keyVersion }}</template>
            </el-table-column>
            <el-table-column label="状态" width="130">
              <template #default="{ row }">
                <el-tag :type="statusTagType(row.status)" size="small">{{ row.statusLabel }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="可用性" width="140">
              <template #default="{ row }">{{ usableText(row) }}</template>
            </el-table-column>
            <el-table-column label="生效时间" width="150">
              <template #default="{ row }">{{ formatTime(row.effectiveAt || row.createdAt) }}</template>
            </el-table-column>
            <el-table-column label="回收时间" width="150">
              <template #default="{ row }">{{ formatTime(row.revokedAt) }}</template>
            </el-table-column>
            <el-table-column label="回收原因" min-width="160" show-overflow-tooltip>
              <template #default="{ row }">{{ row.revokedReason || '—' }}</template>
            </el-table-column>
          </el-table>
        </section>
      </template>
    </el-card>
  </div>
</template>

<script setup>
/**
 * 版本历史（菜单 9411，节点端 `/keyVersionHistory/index`）。
 *
 * 改造前，这一页打在 updatedel 旧 `keymanage` 模型上：要求用户先输一个 keyId，
 * 再调 `GET /lifecycle/keymanage/{keyId}/versions` 读 `keymanage_version_history`。
 * 那条链与节点真正在用的长期密钥（`NodeLongTermKey`）不是一回事 ——
 * 查得到"历史"，但查的不是这把密钥的历史。
 *
 * 现在：一次读回本节点全部长期密钥行（`GET /node-self/keys/`），在前端按
 * **algorithm + keyId** 分组。接口本身**没有分页参数**（刻意如此，见 node-self.js），
 * 所以不做服务端分页，只在到 200 条上限时如实提醒可能被截断。
 *
 * 为什么分组键带 algorithm，不只按 keyId
 * ------------------------------------
 * 密钥的身份是 `nodeId / 算法 / keyId / 版本` 四元组（本地 keyRef 同此）。
 * keyId 是节点本地铸的，理论上不同算法可能铸出同一串 —— 只按 keyId 分组会把
 * 两个算法各自的版本历史**静默合并**到一组里，看起来是一条连续版本链，
 * 而实际上 v1/v2 根本不是先后关系。多带一列 algorithm 就杜绝了这种合并。
 *
 * 为什么组内不重新排序
 * ------------------
 * 服务端按 `algorithm, -id` 下发，同一组的相对顺序就是"最新在前"。
 * 本地再按 keyVersion 排序会在**跨 keyId 重铸**（版本从 1 重新开始）的行上
 * 得到与事实相反的顺序，而排序结果不会报错。
 */
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { getSelfNode, listSelfNodeKeys } from '@/api/pqkds/node-self'

/** 后端 `_long_term_keys_payload(node, limit=200)` 的条数上限，**与后端同改**。 */
const SERVER_ROW_LIMIT = 200

/** 状态 → 标签颜色。**只有颜色**是前端的，文案一律用服务端 `statusLabel`。 */
const STATUS_TAG_TYPE = { ACTIVE: 'success', PENDING: 'warning', REVOKED: 'danger' }

const route = useRoute()
const loading = ref(true)
const mapped = ref(false)
const node = ref({})
const rows = ref([])

// 从密钥列表带 ?keyId= 跳进来时预填筛选词。仍然只是**本地筛选**，
// 不因此改成按 keyId 请求服务端 —— 接口不读 query，传了也不会生效。
const keyword = ref(String(route.query.keyId || ''))
const algoFilter = ref('')

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

const algorithmOptions = computed(() => [...new Set(rows.value.map((r) => r.algorithm).filter(Boolean))].sort())

const filteredRows = computed(() =>
  rows.value.filter((row) => {
    if (algoFilter.value && row.algorithm !== algoFilter.value) return false
    if (keyword.value) {
      const wanted = keyword.value.trim().toLowerCase()
      if (wanted && !String(row.keyId || '').toLowerCase().includes(wanted)) return false
    }
    return true
  })
)

/**
 * 分组。用 Map 而不是"相邻分组"：同 keyId 的行**不一定连续** ——
 * 服务端按 `-id` 排，A 的两版与 B 的一版会交错出现（A@10, B@8, A@5），
 * 相邻分组会把 A 拆成两组，看起来像两把不同的密钥。
 *
 * `\u0000` 作分隔符：keyId 是十六进制串，不含 NUL，不会与 algorithm 拼串歧义
 * （用 `-` 之类的分隔符则 `A/B-1` 与 `A/B-2` 有理论上的碰撞面）。
 */
const groups = computed(() => {
  const byKey = new Map()
  for (const row of filteredRows.value) {
    const key = `${row.algorithm}\u0000${row.keyId || ''}`
    if (!byKey.has(key)) {
      byKey.set(key, { key, algorithm: row.algorithm, keyId: row.keyId, rows: [] })
    }
    byKey.get(key).rows.push(row)
  }
  // 组内保持服务端顺序（最新在前，见文件头注释）；组间按算法、keyId 稳定输出。
  return [...byKey.values()].map((g) => ({ ...g, latest: g.rows[0] }))
})

function resetFilters() {
  keyword.value = ''
  algoFilter.value = ''
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
.version-history__card { max-width: 1320px; margin: 24px auto; }
.version-history__header { display: flex; align-items: center; justify-content: space-between; }
.version-history__header h2 { margin: 0; font-size: 18px; }
.version-history__header-side { display: flex; align-items: center; gap: 8px; }
.version-history__lead { margin: 0 0 12px; color: var(--kms-text-secondary, #606266); line-height: 1.7; }
.version-history__notice { margin-bottom: 12px; }
.version-history__filter { margin-bottom: 4px; }
.version-history__filter-select { width: 160px; }
.version-history__summary { font-size: 12px; color: var(--kms-text-secondary, #909399); }
.version-history__empty { margin: 12px 0 0; color: var(--kms-text-secondary, #909399); font-size: 13px; }
.version-history__group { margin-top: 20px; }
.version-history__group-head {
  display: flex; align-items: center; gap: 8px; margin-bottom: 8px; flex-wrap: wrap;
}
.version-history__group-keyid { font-weight: 600; word-break: break-all; }
.version-history__group-note { font-size: 12px; color: var(--kms-text-secondary, #909399); }
.mono { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
</style>
