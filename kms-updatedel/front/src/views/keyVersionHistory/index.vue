<template>
  <div class="app-container">
    <el-card shadow="never">
      <template #header>
        <div class="vh-header">
          <h2>版本历史</h2>
          <div class="vh-query">
            <el-input
              v-model="keyId"
              placeholder="输入密钥ID"
              clearable
              style="width: 180px"
              @keyup.enter="load"
            />
            <el-button type="primary" icon="Search" :loading="loading" @click="load">查询</el-button>
          </div>
        </div>
      </template>

      <el-alert
        v-if="!keyId"
        type="info"
        :closable="false"
        show-icon
        title="输入密钥 ID 查看它的历史版本"
        description="轮换与回收都会把当时的密钥材料快照归档。旧版本不会随轮换丢失 —— 历史分发记录、会话与链上存证的验证都需要它。"
      />

      <template v-else>
        <el-descriptions v-if="current" :column="4" border size="small" class="vh-current">
          <!-- 回显被查询的密钥 ID：不显示的话用户查完不知道看的是哪一把 -->
          <el-descriptions-item label="密钥ID">{{ keyId }}</el-descriptions-item>
          <el-descriptions-item label="当前版本">
            <el-tag type="success">v{{ current.version }}</el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="密钥名称">{{ current.keyName || '-' }}</el-descriptions-item>
          <el-descriptions-item label="算法">{{ current.encrytName || '-' }}</el-descriptions-item>
        </el-descriptions>

        <el-table :data="rows" size="small" v-loading="loading" border
                  empty-text="没有历史版本（该密钥尚未轮换或回收过）">
          <el-table-column label="版本" width="80">
            <template #default="{ row }"><el-tag size="small">v{{ row.version }}</el-tag></template>
          </el-table-column>
          <el-table-column label="算法" prop="encrytName" width="100" />
          <el-table-column label="归档原因" width="100">
            <template #default="{ row }">
              <el-tag :type="row.archivedReason === 'REVOKE' ? 'danger' : 'warning'" size="small">
                {{ row.archivedReason === 'REVOKE' ? '回收' : '轮换' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="归档时的状态" prop="status" width="90" />
          <el-table-column label="归档时间" prop="archivedAt" width="170" />
          <el-table-column label="用户部分公钥 uA" min-width="200">
            <template #default="{ row }">
              <span class="vh-hex">{{ truncate(row.ua) }}</span>
            </template>
          </el-table-column>
        </el-table>

        <p class="vh-note">
          历史版本只保留**公开量与被脱敏的材料摘要**；完整私钥从未进入本系统。
        </p>
      </template>
    </el-card>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { getKeyVersionHistory, getKeymanage } from '@/api/lifecycle/lifecycle'

const route = useRoute()
const keyId = ref('')
const loading = ref(false)
const rows = ref([])
const current = ref(null)

/** 长十六进制串只显示头尾，避免表格被撑爆 */
const truncate = (s) => {
  const t = String(s || '')
  return t.length > 28 ? `${t.slice(0, 14)}…${t.slice(-10)}` : (t || '-')
}

/** 后端返回 snake_case（key_name / encryt_name），这里归一成前端惯用的 camelCase */
const norm = (r) => ({
  version: r.version,
  encrytName: r.encryt_name ?? r.encrytName,
  ua: r.ua,
  status: r.status,
  archivedReason: r.archived_reason ?? r.archivedReason,
  archivedAt: r.upd_time ?? r.archived_at ?? r.archivedAt
})

async function load() {
  const id = String(keyId.value || '').trim()
  if (!id) return
  loading.value = true
  rows.value = []
  current.value = null
  try {
    // 当前版本与历史版本来自两张表，并行取
    const [hist, cur] = await Promise.all([
      getKeyVersionHistory(id),
      getKeymanage(id).catch(() => null)
    ])
    const list = hist?.data || hist || []
    rows.value = (Array.isArray(list) ? list : []).map(norm)
    if (cur?.data || cur?.keyId) {
      const c = cur.data || cur
      current.value = { version: c.version, keyName: c.key_name ?? c.keyName, encrytName: c.encryt_name ?? c.encrytName }
    } else {
      // 详情取不到（如密钥不存在）也要给出当前版本，否则整块摘要区不渲染、
      // 用户看不到"查的是哪把"。历史列表本身可能为空，那是合法结果。
      current.value = { version: '-', keyName: '-', encrytName: '-' }
    }
  } catch (error) {
    ElMessage.error(`读取版本历史失败：${error.message}`)
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  // 支持从密钥列表带 ?keyId= 跳进来
  const q = route.query.keyId
  if (q) {
    keyId.value = String(q)
    load()
  }
})
</script>

<style scoped>
.vh-header { display: flex; align-items: center; justify-content: space-between; }
.vh-header h2 { margin: 0; font-size: 18px; }
.vh-query { display: flex; gap: 8px; }
.vh-current { margin-bottom: 16px; }
.vh-hex { font-family: monospace; font-size: 12px; word-break: break-all; }
.vh-note { margin: 12px 0 0; font-size: 12px; color: var(--kms-text-secondary, #909399); }
</style>