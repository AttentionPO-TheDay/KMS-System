<template>
  <section class="page">
    <div class="page-header">
      <p class="eyebrow">Updatedel</p>
      <h2>更新与回收记录</h2>
      <p>统一前端已读取更新与回收系统密钥列表，并可直接切换自动更新状态。</p>
    </div>

    <article class="panel">
      <div class="toolbar">
        <label>
          <span>用户 ID</span>
          <input v-model="filters.userId" type="number" min="1" placeholder="按用户 ID 筛选" />
        </label>
        <label>
          <span>用户名</span>
          <input v-model="filters.userName" type="text" placeholder="按用户名筛选" />
        </label>
        <label>
          <span>自动更新</span>
          <select v-model="filters.autoUpdate">
            <option value="">全部</option>
            <option value="1">已开启</option>
            <option value="0">已关闭</option>
          </select>
        </label>
        <button @click="loadKeys">刷新</button>
      </div>
      <p>API 前缀：<code>{{ apiBase }}</code></p>
      <RouterLink class="inline-link" to="/permissions">申请密钥自动更新权限</RouterLink>
      <p v-if="errorMessage" class="error-text">{{ errorMessage }}</p>
      <div v-if="keys.length === 0" class="empty-state">暂无更新与回收记录</div>
      <div v-else class="record-list">
        <article v-for="key in keys" :key="key.keyId" class="record-card">
          <div class="record-head">
            <strong>{{ key.keyName || '未命名密钥' }}</strong>
            <span class="badge">{{ autoUpdateText(key.autoUpdate) }}</span>
          </div>
          <p>密钥 ID：{{ key.keyId }}</p>
          <p>用户：{{ key.userName || '-' }}</p>
          <p>算法：{{ key.encrytName || '-' }}</p>
          <p>状态：{{ key.status || '-' }}</p>
          <div class="card-actions">
            <button class="ghost-button" @click="showDetail(key.keyId)">查看详情</button>
            <button @click="toggleAutoUpdate(key)">
              {{ key.autoUpdate === '1' ? '关闭自动更新' : '开启自动更新' }}
            </button>
          </div>
        </article>
      </div>
    </article>

    <article v-if="selectedKey" class="panel">
      <div class="panel-head">
        <h3>更新与回收详情</h3>
        <button class="ghost-button" @click="selectedKey = null">关闭</button>
      </div>
      <div class="detail-grid">
        <p><strong>密钥 ID：</strong>{{ selectedKey.keyId }}</p>
        <p><strong>用户 ID：</strong>{{ selectedKey.userId }}</p>
        <p><strong>用户名：</strong>{{ selectedKey.userName || '-' }}</p>
        <p><strong>算法类型：</strong>{{ selectedKey.encrytType || '-' }}</p>
        <p><strong>算法名称：</strong>{{ selectedKey.encrytName || '-' }}</p>
        <p><strong>密钥名称：</strong>{{ selectedKey.keyName || '-' }}</p>
        <p><strong>用途：</strong>{{ selectedKey.keyUse || '-' }}</p>
        <p><strong>自动更新：</strong>{{ autoUpdateText(selectedKey.autoUpdate) }}</p>
        <p><strong>状态：</strong>{{ selectedKey.status || '-' }}</p>
        <p><strong>版本：</strong>{{ selectedKey.version ?? '-' }}</p>
        <p><strong>创建时间：</strong>{{ selectedKey.creTime || '-' }}</p>
        <p><strong>更新时间：</strong>{{ selectedKey.updTime || '-' }}</p>
      </div>
    </article>
  </section>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { apiBases } from '@/config/api-bases'
import { getLifecycleKey, listLifecycleKeys, updateLifecycleAutoUpdate } from '@/services/lifecycle-api'

const apiBase = apiBases.lifecycleApi
const filters = reactive({ userId: '', userName: '', autoUpdate: '' })
const keys = ref([])
const selectedKey = ref(null)
const errorMessage = ref('')

onMounted(() => {
  loadKeys()
})

async function loadKeys() {
  errorMessage.value = ''
  try {
    const data = await listLifecycleKeys(filters)
    keys.value = data.rows || []
  } catch (error) {
    keys.value = []
    errorMessage.value = error.message
  }
}

async function showDetail(keyId) {
  errorMessage.value = ''
  try {
    const data = await getLifecycleKey(keyId)
    selectedKey.value = data.data || null
  } catch (error) {
    errorMessage.value = error.message
  }
}

async function toggleAutoUpdate(key) {
  errorMessage.value = ''
  try {
    await updateLifecycleAutoUpdate({
      keyId: key.keyId,
      autoUpdate: key.autoUpdate === '1' ? '0' : '1'
    })
    await loadKeys()
    if (selectedKey.value?.keyId === key.keyId) {
      await showDetail(key.keyId)
    }
  } catch (error) {
    errorMessage.value = error.message
  }
}

function autoUpdateText(value) {
  return { 0: '已关闭', 1: '已开启', '0': '已关闭', '1': '已开启' }[value] || '未知'
}
</script>

<style scoped>
.toolbar {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: 12px;
  align-items: end;
}

.toolbar label {
  display: grid;
  gap: 6px;
}

.record-list {
  display: grid;
  gap: 12px;
}

.record-card {
  border: 1px solid rgba(148, 163, 184, 0.24);
  border-radius: 16px;
  padding: 16px;
  background: rgba(15, 23, 42, 0.03);
}

.record-head,
.card-actions {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: center;
  flex-wrap: wrap;
}

.detail-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 10px 16px;
}
</style>
