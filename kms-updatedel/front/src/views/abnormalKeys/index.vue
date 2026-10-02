<template>
  <div class="app-container">
    <el-card shadow="never">
      <template #header>
        <div class="panel-head">
          <span>异常密钥</span>
          <el-button size="small" :loading="loading" @click="load">刷 新</el-button>
        </div>
      </template>

      <!--
        §9.5 异常密钥管理。

        与「一致性检查」（keyHealth）的分工，别再合并：
          本页   —— **列表**视角：一批密钥里哪些有问题、分布如何，逐条下去查
          keyHealth —— **单钥**视角：输入一个 key_id，把这个键在数据库/版本标记/
                        操作轨迹/链上状态之间的不一致逐项摊开，给规则与建议

        这里刻意**不自己判定异常**。异常判据只应有一处 —— 后端的
        `/keymanage/health/{keyId}`。前端若再写一套阈值，两套必然漂移，
        而漂移的表现是"列表说异常、点进去说正常"。

        所以本页的做法是：**候选筛选 + 逐条复核**。
        「回收」状态是唯一在前端就敢断定的异常（REVOKED 是终态，无需再判定）；
        其余筛选条件只是**指向可疑对象**，结论一律以健康检查为准。
      -->

      <el-form :inline="true" class="filter-bar">
        <el-form-item label="候选范围">
          <el-select v-model="filter.scope" style="width: 190px">
            <el-option label="已回收（REVOKED）" value="revoked" />
            <el-option label="全部非正常状态" value="abnormal" />
            <el-option label="全部密钥（人工复核）" value="all" />
          </el-select>
        </el-form-item>
        <el-form-item label="算法">
          <el-select v-model="filter.encrytType" clearable placeholder="全部" style="width: 160px">
            <el-option v-for="t in algorithmOptions" :key="t" :label="t" :value="t" />
          </el-select>
        </el-form-item>
        <el-form-item label="关键字">
          <el-input v-model="filter.keyword" clearable placeholder="密钥ID / 名称 / 用户" style="width: 220px" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" icon="Search" @click="load">查询</el-button>
          <el-button icon="Refresh" @click="reset">重置</el-button>
        </el-form-item>
      </el-form>

      <el-alert
        v-if="filter.scope !== 'revoked'"
        type="info"
        :closable="false"
        show-icon
        class="mb16"
        title="除「已回收」外，这里的筛选只是指向可疑对象，不等同于判定为异常"
        description="点「复核」会调该密钥的健康检查接口给出结论。异常判据只维护在后端一处。"
      />

      <el-table v-loading="loading" :data="rows" border empty-text="没有符合条件的密钥">
        <el-table-column label="密钥ID" prop="keyId" width="90" align="center" />
        <el-table-column label="密钥名称" prop="keyName" min-width="150" show-overflow-tooltip />
        <el-table-column label="用户名" prop="userName" width="120" show-overflow-tooltip />
        <el-table-column label="算法" prop="encrytName" min-width="130" show-overflow-tooltip />
        <el-table-column label="版本" width="80" align="center">
          <template #default="{ row }">
            <span v-if="row.version != null">v{{ row.version }}</span>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="110" align="center">
          <template #default="{ row }">
            <el-tag size="small" :type="statusTagType(row.status)">{{ row.status || '-' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="链上状态" width="120" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.chainStatus" size="small" effect="plain"
                    :type="row.chainStatus === 'CONFIRMED' ? 'success' : 'warning'">
              {{ row.chainStatus }}
            </el-tag>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column label="更新时间" width="170">
          <template #default="{ row }">{{ formatTime(row.updTime) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="180" align="center" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="openReview(row)">复核</el-button>
            <el-button link type="primary" size="small" @click="goHealth(row)">一致性检查</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 复核抽屉：把该密钥的健康检查结果摊开，不在这里做二次判定 -->
    <el-drawer v-model="review.open" :title="`复核 · 密钥 ${review.keyId}`" size="620px">
      <div v-loading="review.loading">
        <template v-if="review.result">
          <div class="review-summary">
            <el-tag :type="healthTagType(review.result.health)" size="large">
              {{ healthText(review.result.health) }}
            </el-tag>
            <span class="review-meta">
              {{ review.result.keyName || '-' }} · 版本 v{{ review.result.version }} ·
              状态 {{ review.result.status }}
            </span>
          </div>

          <el-table :data="review.result.findings || []" size="small" border
                    empty-text="全部检查通过，未发现一致性问题或异常">
            <el-table-column label="级别" width="80">
              <template #default="{ row }">
                <el-tag :type="row.severity === 'ERROR' ? 'danger' : 'warning'" size="small">
                  {{ row.severity === 'ERROR' ? '严重' : '警告' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="规则" prop="rule" width="150" />
            <el-table-column label="说明" prop="message" min-width="220" />
            <el-table-column label="建议" prop="advice" min-width="220" />
          </el-table>

          <el-collapse v-if="review.result.observations?.length" class="review-obs">
            <el-collapse-item :title="`判定依据（${review.result.observations.length} 条）—— 供人工核对`">
              <ul>
                <li v-for="(o, i) in review.result.observations" :key="i">{{ o }}</li>
              </ul>
            </el-collapse-item>
          </el-collapse>
        </template>
      </div>
    </el-drawer>
  </div>
</template>

<script setup>
/**
 * §11.1 密钥更新与回收监管 → 异常密钥。
 *
 * 列表数据与「更新状态」同源（`/lifecycle/keymanage/list`），差别只在
 * **默认筛选与用途**：那一页看轮换进度，这一页挑需要处置的键。
 * 复用同一接口而不是新造一个，避免两页对"异常"各持一套定义。
 */
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useRouter } from 'vue-router'
import { getKeyHealth, listKeymanage } from '@/api/lifecycle/lifecycle'

const router = useRouter()
const loading = ref(false)
const all = ref([])

const filter = reactive({ scope: 'revoked', encrytType: '', keyword: '' })

const review = reactive({ open: false, loading: false, keyId: '', result: null })

/** 非正常状态：ACTIVE 之外的都值得看一眼；具体含义由后端状态机决定 */
const ABNORMAL_STATUSES = new Set(['REVOKED', 'EXPIRED', 'DISABLED', 'INVALID', 'COMPROMISED'])

function isAbnormal(status) {
  const s = String(status || '').toUpperCase()
  if (!s) return false
  return ABNORMAL_STATUSES.has(s)
}

const algorithmOptions = computed(() => {
  const seen = new Set()
  all.value.forEach((r) => r.encrytType && seen.add(r.encrytType))
  return [...seen]
})

const rows = computed(() => {
  const kw = filter.keyword.trim().toLowerCase()
  return all.value.filter((r) => {
    if (filter.encrytType && r.encrytType !== filter.encrytType) return false

    if (filter.scope === 'revoked') {
      if (String(r.status || '').toUpperCase() !== 'REVOKED') return false
    } else if (filter.scope === 'abnormal') {
      if (!isAbnormal(r.status)) return false
    }

    if (!kw) return true
    return [r.keyId, r.keyName, r.userName]
      .filter((v) => v !== null && v !== undefined)
      .some((v) => String(v).toLowerCase().includes(kw))
  })
})

function statusTagType(status) {
  const s = String(status || '').toUpperCase()
  if (s === 'ACTIVE') return 'success'
  if (s === 'REVOKED' || s === 'COMPROMISED') return 'danger'
  if (!s) return 'info'
  return 'warning'
}

function healthTagType(health) {
  if (health === 'OK') return 'success'
  if (health === 'REVOKED') return 'info'
  return 'warning'
}

function healthText(health) {
  if (health === 'OK') return '一致'
  if (health === 'REVOKED') return '已回收'
  if (health === 'SUSPICIOUS') return '存疑'
  return health || '-'
}

function formatTime(value) {
  if (!value) return '-'
  const d = new Date(String(value).replace(' ', 'T'))
  return Number.isNaN(d.getTime()) ? String(value) : d.toLocaleString('zh-CN', { hour12: false })
}

async function load() {
  loading.value = true
  try {
    const res = await listKeymanage({ pageNum: 1, pageSize: 500 })
    all.value = Array.isArray(res?.rows) ? res.rows : Array.isArray(res) ? res : []
  } catch (error) {
    ElMessage.error(error?.message || '加载密钥列表失败')
    all.value = []
  } finally {
    loading.value = false
  }
}

function reset() {
  filter.scope = 'revoked'
  filter.encrytType = ''
  filter.keyword = ''
}

async function openReview(row) {
  review.open = true
  review.keyId = row.keyId
  review.result = null
  review.loading = true
  try {
    review.result = await getKeyHealth(row.keyId)
  } catch (error) {
    ElMessage.error(error?.message || '健康检查失败')
  } finally {
    review.loading = false
  }
}

/** 去「一致性检查」页看完整诊断（带 keyId 进入，该页支持带参查询） */
function goHealth(row) {
  router.push({ path: '/health', query: { keyId: row.keyId } })
}

onMounted(load)
</script>

<style scoped>
.panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.filter-bar { margin-bottom: 8px; }
.mb16 { margin-bottom: 16px; }
.review-summary {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
}
.review-meta {
  color: var(--kms-text-secondary);
  font-size: 13px;
}
.review-obs { margin-top: 12px; }
.review-obs ul {
  margin: 0;
  padding-left: 18px;
  color: var(--kms-text-secondary);
  font-size: 13px;
  line-height: 1.8;
}
</style>
