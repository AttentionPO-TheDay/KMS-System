<template>
  <div class="app-container">
    <el-card class="panel" shadow="never">
      <template #header>
        <div class="panel-head">
          <div>
            <span>分发总览</span>
</div>
          <el-button size="small" :loading="loading" @click="load">刷 新</el-button>
        </div>
      </template>

<el-row :gutter="12" class="stat-row">
        <el-col :span="4"><div class="stat"><div class="k">节点（活跃/总数）</div><div class="v">{{ overview.active_nodes ?? '-' }}/{{ overview.total_nodes ?? '-' }}</div></div></el-col>
        <el-col :span="4"><div class="stat"><div class="k">密钥池总数</div><div class="v">{{ pool.total ?? '-' }}</div></div></el-col>
        <el-col :span="4"><div class="stat"><div class="k">密钥池未用</div><div class="v">{{ pool.unused ?? '-' }}</div></div></el-col>
        <el-col :span="4"><div class="stat"><div class="k">会话数</div><div class="v">{{ overview.total_sessions ?? '-' }}</div></div></el-col>
        <el-col :span="4"><div class="stat"><div class="k">分发日志</div><div class="v">{{ logs.length }}</div></div></el-col>
        <el-col :span="4"><div class="stat"><div class="k">已就绪 Kyber 节点</div><div class="v">{{ kyberReady }}/{{ nodes.length }}</div></div></el-col>
      </el-row>

      <el-row :gutter="12">
        <el-col :span="12">
          <el-card shadow="never" class="inner">
            <template #header><span class="inner-title">密钥池按算法分布</span></template>
            <el-table :data="algorithmRows" size="small" empty-text="密钥池为空">
              <el-table-column label="算法" min-width="140" prop="label" />
              <el-table-column label="总数" width="90" prop="total" />
              <el-table-column label="未用" width="90" prop="unused" />
              <el-table-column label="已用" width="90" prop="used" />
            </el-table>
            <div class="hint">
              过期 {{ pool.expired ?? 0 }} 条；过期的可在「密钥池」页一键清理。
            </div>
          </el-card>
        </el-col>

        <el-col :span="12">
          <el-card shadow="never" class="inner">
            <template #header><span class="inner-title">节点密钥就绪情况</span></template>
            <el-table :data="nodes" size="small" empty-text="还没有演示节点">
              <el-table-column label="节点" min-width="160">
                <template #default="scope">{{ scope.row.name }}（{{ scope.row.node_id }}）</template>
              </el-table-column>
              <el-table-column label="Kyber" width="90" align="center">
                <template #default="scope">
                  <el-tag size="small" :type="scope.row.kyber_key_ready ? 'success' : 'info'">
                    {{ scope.row.kyber_key_ready ? '就绪' : '未生成' }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column label="Falcon" width="90" align="center">
                <template #default="scope">
                  <el-tag size="small" :type="scope.row.falcon_key_ready ? 'success' : 'info'">
                    {{ scope.row.falcon_key_ready ? '就绪' : '未生成' }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column label="国密" width="90" align="center">
                <template #default="scope">
                  <el-tag
                    size="small"
                    :type="scope.row.gm_key_ready && scope.row.sscl_key_ready ? 'success'
                      : (scope.row.gm_key_ready || scope.row.sscl_key_ready ? 'warning' : 'info')"
                  >
                    {{ scope.row.gm_key_ready && scope.row.sscl_key_ready ? '就绪'
                      : (scope.row.gm_key_ready || scope.row.sscl_key_ready ? '部分' : '未生成') }}
                  </el-tag>
                </template>
              </el-table-column>
            </el-table>
            <div class="hint">
              只有 <strong>Kyber 就绪</strong>的节点才能作为发送方接收密钥池 —— 密钥池是用它的 Kyber 公钥封装的。
            </div>
          </el-card>
        </el-col>
      </el-row>

      <el-card shadow="never" class="inner mt12">
        <template #header><span class="inner-title">最近分发动作为</span></template>
        <el-table :data="logs.slice(0, 8)" size="small" empty-text="暂无分发日志">
          <el-table-column label="时间" width="180">
            <template #default="scope">{{ formatTime(scope.row.timestamp) }}</template>
          </el-table-column>
          <el-table-column label="节点" min-width="140">
            <template #default="scope">{{ scope.row.node_name || scope.row.node }}</template>
          </el-table-column>
          <el-table-column label="操作" width="130" prop="action" />
          <el-table-column label="结果" width="90">
            <template #default="scope">
              <el-tag size="small" :type="scope.row.success ? 'success' : 'danger'">{{ scope.row.success ? '成功' : '失败' }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="详情" min-width="220" show-overflow-tooltip>
            <template #default="scope">{{ scope.row.error_message || scope.row.details || '-' }}</template>
          </el-table-column>
        </el-table>
      </el-card>
    </el-card>
  </div>
</template>

<script setup>
/**
 * 「分发总览」——替换原来的 iframe「分发控制台」。
 *
 * 原来的做法是把分发模块自带的控制台整页 iframe 进来，结果因为那个子应用有自己的
 * 登录态，管理端里点开只会看到它的登录页（用户截图："抗量子分发系统 欢迎您！"）。
 * 现在改成原生聚合页：只取它**接口**里的数据，用管理端的组件渲染。
 *
 * 数据来源全部是 `/pqkds-api/*`（分发模块 Django），没有一个字来自 iframe。
 */
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { getKeyPoolStats, getOverviewStats, listDistributionLogs } from '@/api/pqkds/distribution'
import { listNodes } from '@/api/nodes/nodes'

const overview = ref({})
const pool = ref({})
const logs = ref([])
const nodes = ref([])
const loading = ref(false)

// 列表接口只回就绪布尔值（*_key_ready），不带公钥本身 ——
// falcon_public_key 实测 7.8MB/节点，带上它这个总览页也会超时。
const kyberReady = computed(() => nodes.value.filter((n) => n.kyber_key_ready).length)

const algorithmRows = computed(() => {
  const by = pool.value.by_algorithm || {}
  const LABELS = { kyber_kem: 'Kyber KEM', falcon_lattice: 'Falcon 格签名' }
  return Object.entries(by).map(([key, v]) => ({
    key,
    label: LABELS[key] || key,
    total: v?.total ?? 0,
    unused: v?.unused ?? 0,
    used: v?.used ?? 0
  }))
})

function formatTime(value) {
  if (!value) return '-'
  const d = new Date(String(value).replace(' ', 'T'))
  return Number.isNaN(d.getTime()) ? String(value) : d.toLocaleString('zh-CN', { hour12: false })
}

async function load() {
  loading.value = true
  try {
    const [ov, ps, lg, nd] = await Promise.all([
      getOverviewStats().catch(() => ({})),
      getKeyPoolStats().catch(() => ({})),
      listDistributionLogs().catch(() => []),
      listNodes().catch(() => [])
    ])
    overview.value = ov || {}
    pool.value = ps || {}
    logs.value = lg || []
    nodes.value = nd || []
  } catch (error) {
    ElMessage.error(`加载分发总览失败：${error.message}`)
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.panel { border-radius: 10px; }
.panel-head { display: flex; align-items: center; justify-content: space-between; }
.panel-head .sub { margin-left: 10px; color: var(--el-text-color-secondary); font-size: 12px; }
.stat-row { margin-bottom: 12px; }
.stat { background: var(--el-fill-color-light); border-radius: 8px; padding: 10px 14px; }
.stat .k { color: var(--el-text-color-secondary); font-size: 12px; }
.stat .v { font-size: 20px; font-weight: 600; margin-top: 2px; }
.inner { border-radius: 8px; }
.inner-title { font-weight: 600; }
.hint { margin-top: 8px; color: var(--el-text-color-secondary); font-size: 12px; line-height: 1.6; }
.mt12 { margin-top: 12px; }
.mb16 { margin-bottom: 16px; }
</style>