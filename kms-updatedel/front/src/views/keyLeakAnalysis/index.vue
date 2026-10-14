<template>
  <div class="app-container">
    <el-card shadow="never">
      <template #header>
        <div class="la-header">
          <h2>泄漏关联分析</h2>
          <div class="la-query">
            <!-- KMS-014：两类密钥的关联面**在不同表**里（用户密钥 = kms.keymanage、
                 节点长期密钥 = falcon_kds.NodeLongTermKey），keyId 空间也不同
                 （数字 vs 形如 KRb-XX-KYBER-1a2b3c4d 的字符串）。后端因此分成
                 两个入口；这里显式选，避免"输入框填错表 → 查到空、看起来像没泄漏"。
                 KMS-008 之后的节点到节点分发**完全不用用户密钥**，处置节点密钥
                 泄漏要选第二项。 -->
            <el-radio-group v-model="space" size="small">
              <el-radio-button value="user">用户密钥</el-radio-button>
              <el-radio-button value="node">节点长期密钥</el-radio-button>
            </el-radio-group>
            <el-input
              v-model="keyId"
              :placeholder="space === 'user' ? '输入疑遭泄漏的用户密钥ID（数字）' : '输入节点长期密钥 keyId'"
              clearable
              style="width: 240px"
              @keyup.enter="load"
            />
            <el-input
              v-if="space === 'node'"
              v-model="version"
              placeholder="版本（留空=全部版本）"
              clearable
              style="width: 170px"
              @keyup.enter="load"
            />
            <el-button type="primary" icon="Search" :loading="loading" @click="load">分析</el-button>
          </div>
        </div>
      </template>

      <el-alert v-if="analysisError" :title="analysisError" type="error" :closable="false" show-icon />
      <el-empty v-else-if="!loaded && !loading" description="输入密钥ID后点击分析" :image-size="64" />
      <template v-if="loaded">
        <el-alert v-if="truncated" title="关联记录较多，每类展示最近 200 条" type="info" :closable="false" />
        <el-descriptions v-if="base" :column="3" border size="small" class="la-base">
          <!-- ⚠️ baseInfo 是后端直接序列化的 Keymanage，字段为 **snake_case**
               （key_id / key_name / encryt_name / user_name）。只读 camelCase
               会得到一排空值 —— 页面看着没报错，但什么都没显示。 -->
          <el-descriptions-item label="密钥ID">{{ pick(base, 'keyId', 'key_id') }}</el-descriptions-item>
          <el-descriptions-item label="名称">{{ pick(base, 'keyName', 'key_name') || '-' }}</el-descriptions-item>
          <el-descriptions-item label="算法">{{ pick(base, 'encrytName', 'encryt_name') || '-' }}</el-descriptions-item>
          <el-descriptions-item label="版本">v{{ pick(base, 'version') }}</el-descriptions-item>
          <el-descriptions-item label="状态">
            <el-tag :type="['3','REVOKED','EXPIRED'].includes(String(pick(base, 'status'))) ? 'danger' : 'info'" size="small">
              {{ statusText(pick(base, 'status')) }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="所属用户">{{ pick(base, 'userName', 'user_name') || '-' }}</el-descriptions-item>
        </el-descriptions>

        <h3 class="la-title">关联节点</h3>
        <el-table :data="nodes" size="small" border empty-text="没有节点收到过用该密钥保护的分发">
          <el-table-column label="节点ID" prop="node_id" min-width="150" />
          <el-table-column label="名称" prop="name" min-width="120" />
          <el-table-column label="权限等级" prop="permission_level" width="100" />
          <el-table-column label="所属域" prop="domain_id" width="130" />
        </el-table>

        <h3 class="la-title">可用预分配池项</h3>
        <el-table :data="poolItems" size="small" border
                  empty-text="暂无可用池项">
          <el-table-column label="池批次" prop="pool_id" min-width="200" />
          <el-table-column label="条数" prop="item_count" width="90" />
          <el-table-column label="状态" prop="status" width="110" />
        </el-table>

        <h3 class="la-title">分发记录</h3>
        <el-table :data="footprints" size="small" border empty-text="没有分发记录">
          <el-table-column v-for="col in footprintCols" :key="col"
                           :label="col" :prop="col" min-width="140" show-overflow-tooltip />
        </el-table>

        <h3 class="la-title">{{ space === 'node' ? '关联会话' : '操作记录' }}</h3>
        <el-table :data="trails" size="small" border empty-text="没有操作记录">
          <el-table-column v-for="col in trailCols" :key="col"
                           :label="col" :prop="col" min-width="140" show-overflow-tooltip />
        </el-table>

        <el-alert
          v-if="!loading && !footprints.length && !trails.length && !nodes.length && !poolItems.length"
          class="la-empty"
          type="success"
          :closable="false"
          show-icon
          title="未发现关联痕迹"
        />
      </template>
    </el-card>
  </div>
</template>

<script setup>
import { onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { getKeymanageAnalysis, getNodeKeyAnalysis } from '@/api/lifecycle/lifecycle'
import { getOwnNodeKeyAnalysis } from '@/api/pqkds/key-diagnostics'
import useUserStore from '@/store/modules/user'

const route = useRoute()
const keyId = ref('')
/** KMS-014：'user' = 用户密钥（kms.keymanage）；'node' = 节点长期密钥。 */
const userStore = useUserStore()
const space = ref(userStore.principalType === 'NODE' ? 'node' : 'user')
const version = ref('')
const loading = ref(false)
const loaded = ref(false)
const analysisError = ref('')
const truncated = ref(false)
let analysisRequest = 0
watch([keyId, space, version], () => { analysisRequest++; loaded.value = false; analysisError.value = ''; loading.value = false }, { flush: 'sync' })
const statusText = value => ({ '0': '有效', '1': '未生效', '2': '已到期', '3': '已回收', ACTIVE: '有效', RETIRED: '历史版本', REVOKED: '已回收', EXPIRED: '已到期', PENDING: '待激活' }[String(value)] || value || '-')
const base = ref(null)
const footprints = ref([])
const trails = ref([])
const nodes = ref([])
const poolItems = ref([])

// 列名从数据自身推导：后端返回的是 Map 列表，字段名由查询决定，
// 前端写死列会在后端调整字段时静默变成空表。
const footprintCols = ref([])
const trailCols = ref([])

/** 兼容 snake_case 与 camelCase：后端不同接口的命名并不统一 */
const pick = (obj, ...keys) => {
  for (const k of keys) {
    const v = obj?.[k]
    if (v !== undefined && v !== null && v !== '') return v
  }
  return ''
}

const norm = (r) => {
  const o = {}
  Object.entries(r || {}).forEach(([k, v]) => {
    o[k] = (v === null || v === undefined) ? '' : String(v)
  })
  return o
}

async function load() {
  const id = String(keyId.value || '').trim()
  if (!id || loading.value) return
  if (version.value && (!/^\d+$/.test(version.value) || Number(version.value) < 1 || Number(version.value) > 2147483647)) { analysisError.value = '版本须为正整数'; return }
  if (space.value === 'user' && !/^\d+$/.test(id)) { analysisError.value = '请选择节点长期密钥'; return }
  const requestId = ++analysisRequest
  loaded.value = false
  analysisError.value = ''
  loading.value = true
  base.value = null
  footprints.value = []
  trails.value = []
  nodes.value = []
  poolItems.value = []
  footprintCols.value = []
  trailCols.value = []
  try {
    // 两条入口的响应形状一致（同一 DTO）；分流只决定走哪个标识空间，
    // 见 KMS-014 在 `LifecycleService.getNodeKeyLeakAnalysis` 的说明。
    const res = space.value === 'node'
      ? await (userStore.principalType === 'ADMIN' ? getNodeKeyAnalysis : getOwnNodeKeyAnalysis)(id, version.value ? Number(version.value) : undefined)
      : await getKeymanageAnalysis(id)
    if (requestId !== analysisRequest) return
    if (res?.code && res.code !== 200) {
      analysisError.value = res.msg || '分析失败'
      return
    }
    const d = res?.data || res || {}
    base.value = d.baseInfo || null
    footprints.value = (d.distributeFootprints || []).map(norm)
    trails.value = (d.operationTrails || []).map(norm)
    nodes.value = (d.affectedNodes || []).map(norm)
    poolItems.value = (d.affectedPoolItems || []).map(norm)
    footprintCols.value = footprints.value.length ? Object.keys(footprints.value[0]) : []
    trailCols.value = trails.value.length ? Object.keys(trails.value[0]) : []
    truncated.value = Boolean(d.truncated)
    loaded.value = true
  } catch (error) {
    if (requestId === analysisRequest) analysisError.value = `分析失败：${error.message || '请稍后重试'}`
  } finally {
    if (requestId === analysisRequest) loading.value = false
  }
}

onMounted(() => {
  const q = route.query.keyId
  if (q) {
    keyId.value = String(q)
    if (!/^\d+$/.test(String(q))) space.value = 'node'
  }
})
</script>

<style scoped>
.la-header { display: flex; align-items: center; justify-content: space-between; }
.la-header h2 { margin: 0; font-size: 18px; }
.la-query { display: flex; gap: 8px; }
@media (max-width: 1100px) { .la-header { align-items: flex-start; flex-direction: column; gap: 12px; } .la-query { flex-wrap: wrap; width: 100%; } .la-query .el-input { flex: 1 1 180px; } }
.la-base { margin-bottom: 20px; }
.la-title { margin: 20px 0 10px; font-size: 14px; font-weight: 600; }
.la-empty { margin-top: 16px; }
</style>
