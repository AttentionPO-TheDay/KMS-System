<template>
  <div class="app-container">
    <el-card shadow="never">
      <template #header>
        <div class="panel-head">
          <span>域管理</span>
          <el-button size="small" :loading="loading" :disabled="saving !== null" @click="load">刷新</el-button>
        </div>
      </template>


      <el-form class="create-domain" @submit.prevent="addDomain" label-position="top">
        <el-form-item label="域标识（唯一）"><el-input v-model="newDomain.domain_id" maxlength="64" placeholder="例如 domain-3" :disabled="creating" /></el-form-item>
        <el-form-item label="域名称"><el-input v-model="newDomain.name" maxlength="100" placeholder="例如研发域" :disabled="creating" /></el-form-item>
        <el-form-item label="说明（选填）"><el-input v-model="newDomain.description" maxlength="500" :disabled="creating" /></el-form-item>
        <el-button type="primary" native-type="submit" :loading="creating" :disabled="loading || saving !== null || !newDomain.domain_id.trim() || !newDomain.name.trim()">新增域</el-button>
      </el-form>
      <el-alert v-if="error" type="error" :title="error" :closable="false" show-icon />
      <el-alert
        v-else-if="!loading && !domains.length"
        type="info"
        :closable="false"
        show-icon
        title="尚未创建域"
      />

      <template v-else>
        <div class="section-title">域分布</div>
        <el-table :data="domains" border>
          <el-table-column label="域标识" prop="domainId" min-width="180">
            <template #default="{ row }">
              <span class="mono">{{ row.domainId }}</span>
            </template>
          </el-table-column>
          <el-table-column label="域名称" prop="name" min-width="140" />
          <el-table-column label="说明" prop="description" min-width="180" show-overflow-tooltip />
          <el-table-column label="节点数" width="100" align="center" prop="count" />
          <el-table-column label="状态分布" min-width="280">
            <template #default="{ row }">
              <el-tag v-for="s in row.statuses" :key="s.status" size="small" class="status-tag"
                      :type="statusTagType(s.status)">
                {{ s.status }} × {{ s.count }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="权限等级" min-width="200">
            <template #default="{ row }">
              <el-tag v-for="l in row.levels" :key="l.level" size="small" effect="plain" class="status-tag">
                {{ l.level }} × {{ l.count }}
              </el-tag>
            </template>
          </el-table-column>
        </el-table>

        <div class="section-title">节点明细与域归属 <span class="domain-note">共 {{ nodes.length }} 个节点</span></div>
        <el-table v-loading="loading" :data="nodeRows" border>
          <el-table-column label="节点 ID" prop="node_id" min-width="150" show-overflow-tooltip />
          <el-table-column label="名称" prop="name" min-width="140" show-overflow-tooltip />
          <el-table-column label="所属域" min-width="150">
            <template #default="{ row }">
              <span class="mono">{{ row.domain_id || '-' }}</span>
            </template>
          </el-table-column>
          <el-table-column label="节点类型" prop="node_type" width="120" />
          <el-table-column label="权限等级" width="110" align="center">
            <template #default="{ row }">
              <el-tag size="small" effect="plain">{{ row.permission_level || '-' }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="状态" width="130" align="center">
            <template #default="{ row }">
              <el-tag size="small" :type="statusTagType(row.status)">{{ row.status || '未初始化' }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="调整所属域" min-width="300">
            <template #default="{ row }">
              <div class="domain-editor">
                <el-select v-model="drafts[row.id]" filterable
                           :disabled="saving !== null || creating" :aria-label="`${row.node_id} 的新所属域`" placeholder="选择已创建的域">
                  <el-option v-for="domain in registeredDomains" :key="domain.domain_id" :label="domain.domain_id" :value="domain.domain_id" />
                </el-select>
                <el-button :loading="saving === row.id"
                           :disabled="saving !== null || !drafts[row.id]?.trim() || drafts[row.id]?.trim() === row.domain_id"
                           @click="save(row)">保存</el-button>
              </div>
            </template>
          </el-table-column>
        </el-table>

      </template>
    </el-card>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { listAllNodes, updateNode } from '@/api/nodes/nodes'
import { listDomains, createDomain } from '@/api/nodes/domains'

const loading = ref(false)
const nodes = ref([])
const drafts = ref({})
const saving = ref(null)
const error = ref('')
const registeredDomains = ref([])
const creating = ref(false)
const newDomain = ref({ domain_id: '', name: '', description: '' })

/** 历史空域明确显示为未指定，不凭空推断到 domain-1。 */
const FALLBACK_DOMAIN = '未指定域'

const nodeRows = computed(() => nodes.value)

const domains = computed(() => {
  const byDomain = new Map()
  registeredDomains.value.forEach(domain => byDomain.set(domain.domain_id, {
    domainId: domain.domain_id, name: domain.name, description: domain.description,
    count: 0, statuses: new Map(), levels: new Map()
  }))
  nodes.value.forEach((n) => {
    const id = String(n.domain_id || '').trim() || FALLBACK_DOMAIN
    if (!byDomain.has(id)) {
      byDomain.set(id, { domainId: id, count: 0, statuses: new Map(), levels: new Map() })
    }
    const entry = byDomain.get(id)
    entry.count += 1

    const status = String(n.status || '').trim() || '未初始化'
    entry.statuses.set(status, (entry.statuses.get(status) || 0) + 1)

    const level = String(n.permission_level || '').trim() || '未设'
    entry.levels.set(level, (entry.levels.get(level) || 0) + 1)
  })

  return [...byDomain.values()]
    .map((entry) => ({
      domainId: entry.domainId,
      name: entry.name || '未登记',
      description: entry.description || '',
      count: entry.count,
      statuses: [...entry.statuses].map(([status, count]) => ({ status, count })),
      levels: [...entry.levels].map(([level, count]) => ({ level, count }))
    }))
    .sort((a, b) => b.count - a.count || a.domainId.localeCompare(b.domainId))
})

function statusTagType(status) {
  const s = String(status || '').toLowerCase()
  if (s === 'active') return 'success'
  if (s === 'disabled' || s === 'inactive') return 'danger'
  if (!s) return 'info'
  return 'warning'
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const [nodeData, domainData] = await Promise.all([listAllNodes(), listDomains()])
    if (!Array.isArray(domainData)) throw new Error('域列表响应格式不正确')
    nodes.value = nodeData
    registeredDomains.value = domainData
    drafts.value = Object.fromEntries(nodes.value.map(row => [row.id, row.domain_id || '']))
  } catch (err) {
    error.value = err?.message || '域数据获取失败，请刷新后重试'
    nodes.value = []
    registeredDomains.value = []
  } finally {
    loading.value = false
  }
}

async function addDomain() {
  if (creating.value || loading.value || saving.value !== null) return
  creating.value = true
  try {
    await createDomain(Object.fromEntries(Object.entries(newDomain.value).map(([key, value]) => [key, value.trim()])))
    newDomain.value = { domain_id: '', name: '', description: '' }
    ElMessage.success('域已创建，可为节点调整归属')
    await load()
  } catch (err) { ElMessage.error(err?.message || '新增域失败，请重试') }
  finally { creating.value = false }
}

async function save(row) {
  if (saving.value !== null) return
  const domain = String(drafts.value[row.id] || '').trim()
  if (!domain || domain.length > 64) { ElMessage.warning('域标识须为 1 至 64 个字符'); return }
  if (domain === row.domain_id) return
  saving.value = row.id
  try {
    await updateNode(row.id, { domain_id: domain })
    ElMessage.success('所属域已更新，历史分发记录不变')
    await load()
  } catch (err) { ElMessage.error(err?.message || '保存失败，节点归属未更新') }
  finally { saving.value = null }
}

onMounted(load)
</script>

<style scoped>
.domain-note { color: var(--kms-text-secondary); font-size: 13px; line-height: 1.7; }
.domain-editor { display: flex; gap: 8px; }
.domain-editor .el-select { flex: 1; min-width: 0; }
.create-domain { display: flex; gap: 12px; align-items: flex-end; flex-wrap: wrap; margin: 20px 0; }
.create-domain .el-form-item { flex: 1 1 180px; margin-bottom: 0; }
@media (max-width: 600px) { .create-domain .el-form-item { flex-basis: 100%; } }
.panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.mono {
  font-family: 'JetBrains Mono', Consolas, monospace;
  font-size: 13px;
}
.section-title {
  margin: 20px 0 10px;
  font-size: 14px;
  font-weight: 600;
  color: var(--kms-text-primary);
}
.section-title:first-of-type { margin-top: 0; }
.status-tag { margin: 2px 6px 2px 0; }
</style>
