<template>
  <div class="app-container">
    <div class="sm-actions">
      <el-button icon="Refresh" :loading="loading" @click="load">刷新</el-button>
      <span v-if="loadedAt" class="sm-time">更新于 {{ loadedAt }}</span>
    </div>

    <!-- 节点 -->
    <h3 class="sm-title">节点</h3>
    <div class="sm-grid">
      <div class="sm-card"><span>节点总数</span><strong>{{ val('nodes.total') }}</strong></div>
      <div class="sm-card"><span>已激活</span><strong class="ok">{{ val('nodes.active') }}</strong></div>
      <div class="sm-card"><span>待初始化</span><strong class="warn">{{ val('nodes.pendingInit') }}</strong></div>
      <div class="sm-card"><span>已停用</span><strong>{{ val('nodes.disabled') }}</strong></div>
    </div>

    <h3 class="sm-title">节点权限等级分布</h3>
    <div class="sm-grid">
      <div v-for="(label, lvl) in LEVEL_LABELS" :key="lvl" class="sm-card">
        <span>{{ lvl }} · {{ label }}</span>
        <strong>{{ val(`nodes.byLevel.${lvl}`) }}</strong>
      </div>
    </div>

    <!-- 密钥 -->
    <h3 class="sm-title">密钥</h3>
    <div class="sm-grid">
      <div class="sm-card"><span>有效密钥</span><strong class="ok">{{ val('keys.active') }}</strong></div>
      <div class="sm-card"><span>已回收</span><strong>{{ val('keys.revoked') }}</strong></div>
    </div>

    <!-- 异常 -->
    <h3 class="sm-title">异常</h3>
    <div class="sm-grid">
      <div class="sm-card">
        <span>材料缺失（真实缺陷）</span>
        <strong :class="Number(val('anomalies.materialMissing')) > 0 ? 'danger' : 'ok'">
          {{ val('anomalies.materialMissing') }}
        </strong>
      </div>
      <div class="sm-card">
        <span>早期不可用（设计如此，非故障）</span>
        <strong>{{ val('anomalies.legacyUnusable') }}</strong>
      </div>
    </div>

    <!-- 预分配池 -->
    <h3 class="sm-title">预分配密钥池</h3>
    <div class="sm-grid">
      <div class="sm-card"><span>可取用 READY</span><strong class="ok">{{ val('pool.ready') }}</strong></div>
      <div class="sm-card"><span>占用中 RESERVED</span><strong>{{ val('pool.reserved') }}</strong></div>
      <div class="sm-card"><span>已消费 CONSUMED</span><strong>{{ val('pool.consumed') }}</strong></div>
      <div class="sm-card"><span>已失效 REVOKED</span><strong class="warn">{{ val('pool.revoked') }}</strong></div>
      <div class="sm-card"><span>已过期 EXPIRED</span><strong>{{ val('pool.expired') }}</strong></div>
    </div>

    <!-- 会话 -->
    <h3 class="sm-title">会话</h3>
    <div class="sm-grid">
      <div class="sm-card"><span>会话总数</span><strong>{{ val('sessions.total') }}</strong></div>
      <div class="sm-card"><span>已建立</span><strong class="ok">{{ val('sessions.established') }}</strong></div>
      <div class="sm-card"><span>已过期</span><strong>{{ val('sessions.expired') }}</strong></div>
      <div class="sm-card"><span>已撤销</span><strong>{{ val('sessions.revoked') }}</strong></div>
    </div>

    <!-- 分发 -->
    <h3 class="sm-title">分发</h3>
    <div class="sm-grid">
      <div class="sm-card"><span>分发批次总数</span><strong>{{ val('distribution.total') }}</strong></div>
      <div class="sm-card">
        <span>成功率</span>
        <strong class="ok">{{ rateText }}</strong>
      </div>
      <div class="sm-card"><span>成功</span><strong class="ok">{{ val('distribution.byStatus.success') }}</strong></div>
      <div class="sm-card"><span>部分成功</span><strong class="warn">{{ val('distribution.byStatus.partial') }}</strong></div>
      <div class="sm-card"><span>失败</span><strong class="danger">{{ val('distribution.byStatus.failed') }}</strong></div>
    </div>

    <h3 class="sm-title">跨域分发（§8.5）</h3>
    <div class="sm-grid">
      <div class="sm-card"><span>同域</span><strong>{{ val('distribution.crossDomain.same') }}</strong></div>
      <div class="sm-card"><span>跨域</span><strong class="warn">{{ val('distribution.crossDomain.cross') }}</strong></div>
      <div class="sm-card"><span>混合</span><strong>{{ val('distribution.crossDomain.mixed') }}</strong></div>
    </div>

    <p class="sm-note">
      统计失败项显示「不可用」而非 0 —— 0 是有效值，会被误读成"确实没有"。
      密钥计数经跨 schema 只读查询取自 kms.keymanage。
    </p>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import http, { unwrap } from '@/api/pqkds/http'

const LEVEL_LABELS = { L1: '查询', L2: '查询+生成+分发', L3: '查询+生成+分发+更新+回收' }

const loading = ref(false)
const loadedAt = ref('')
const data = ref({})

/**
 * 取值并按点路径展开。
 *
 * 关键：**缺失项返回「不可用」而不是 0**。监控面板上 0 是有效值，
 * 会被读成"确实没有"；而"这个数据源挂了"和"数量为零"是完全不同的事。
 * 混在一起会让一次统计故障看起来像一片健康。
 */
const val = (path) => {
  const v = path.split('.').reduce((o, k) => (o == null ? undefined : o[k]), data.value)
  if (v === null || v === undefined) return '不可用'
  return v
}

/** 成功率：后端在分母为 0 时返回 null（无定义），需与"0%"区分开 */
const rateText = computed(() => {
  const r = data.value?.distribution?.successRate
  if (r === null || r === undefined) return '不可用'
  return `${(Number(r) * 100).toFixed(1)}%`
})

async function load() {
  loading.value = true
  try {
    data.value = await http.get('/security-monitor/summary/').then(unwrap)
    loadedAt.value = new Date().toLocaleTimeString('zh-CN', { hour12: false })
  } catch (error) {
    ElMessage.error(`读取监控数据失败：${error.message}`)
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.sm-actions { display: flex; align-items: center; gap: 12px; margin-bottom: 8px; }
.sm-time { font-size: 12px; color: var(--kms-text-secondary, #909399); }
.sm-title { margin: 20px 0 10px; font-size: 14px; font-weight: 600; }
.sm-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 10px; }
.sm-card {
  border: 1px solid var(--el-border-color, #e4e7ed); border-radius: 6px;
  padding: 10px 14px; display: flex; flex-direction: column; gap: 4px;
}
.sm-card span { font-size: 12px; color: var(--kms-text-secondary, #909399); }
.sm-card strong { font-size: 20px; }
.sm-card .ok { color: var(--el-color-success, #67c23a); }
.sm-card .warn { color: var(--el-color-warning, #e6a23c); }
.sm-card .danger { color: var(--el-color-danger, #f56c6c); }
.sm-note { margin: 20px 0 0; font-size: 12px; color: var(--kms-text-secondary, #909399); line-height: 1.7; }
</style>