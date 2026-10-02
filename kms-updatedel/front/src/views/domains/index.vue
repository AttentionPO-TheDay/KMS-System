<template>
  <div class="app-container">
    <el-card shadow="never">
      <template #header>
        <div class="panel-head">
          <span>域管理</span>
          <el-button size="small" :loading="loading" @click="load">刷 新</el-button>
        </div>
      </template>

      <!--
        §9.10 跨域管理。

        ⚠️ 域在这里是**标记**，不是一套独立的部署。
        第一阶段不部署多套 KMS（见 three-subsystem-refactor-plan-v2.md §14
        「不拆成三套独立物理部署，仍坚持逻辑三个子系统、物理一套系统」）。
        域的取值就是 Node.domain_id 这个字段，本页做的是**归集与展示**，
        明确不引入域表、域的增删改或任何域级策略 —— 那些都会让人误以为
        域是独立安装，与上述决策相悖。

        数据全部来自既有的 `GET /pqkds-api/nodes/`（NodeSerializer 含 domain_id），
        因此本页不需要任何后端改动。
      -->

      <el-alert
        v-if="!loading && !domains.length"
        type="info"
        :closable="false"
        show-icon
        title="还没有任何节点"
        description="域信息来自节点的 domain_id 字段，请先在「节点管理 → 节点列表」里创建节点并指定所属域。"
      />

      <template v-else>
        <div class="section-title">域分布</div>
        <el-table :data="domains" border>
          <el-table-column label="域标识" prop="domainId" min-width="180">
            <template #default="{ row }">
              <span class="mono">{{ row.domainId }}</span>
            </template>
          </el-table-column>
          <el-table-column label="节点数" width="100" align="center" prop="count" />
          <el-table-column label="状态分布" min-width="280">
            <template #default="{ row }">
              <el-tag v-for="s in row.statuses" :key="s.status" size="small" class="status-tag"
                      :type="s.status === 'ACTIVE' ? 'success' : s.status === 'DISABLED' ? 'danger' : 'warning'">
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

        <div class="section-title">节点明细</div>
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
        </el-table>
      </template>
    </el-card>
  </div>
</template>

<script setup>
/**
 * §11.1 节点管理 → 域管理。
 *
 * 读 `GET /pqkds-api/nodes/`（NodeSerializer 暴露 domain_id，见 serializers.py
 * 里"漏在 fields 外面的字段会被 DRF 静默丢弃"那段注释）。前端按 domain_id
 * 归集即可，**不需要新接口** —— 这也是本页能比原计划少改一处后端的原因。
 */
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { listNodes } from '@/api/nodes/nodes'

const loading = ref(false)
const nodes = ref([])

/** 未指定域时的落点。与 Node.domain_id 的默认值保持一致（models.py:161） */
const FALLBACK_DOMAIN = 'domain-1'

const nodeRows = computed(() => nodes.value)

const domains = computed(() => {
  const byDomain = new Map()
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
  try {
    nodes.value = await listNodes()
  } catch (error) {
    ElMessage.error(error?.message || '加载节点列表失败')
    nodes.value = []
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<style scoped>
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
