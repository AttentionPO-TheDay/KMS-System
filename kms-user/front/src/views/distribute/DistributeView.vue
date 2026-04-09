<template>
  <section class="page">
    <div class="page-header">
      <p class="eyebrow">Distribute</p>
      <h2>分发记录</h2>
      <p>统一前端已直接对接抗量子密钥分发系统后端，可查看记录列表并展开详情。</p>
    </div>

    <article class="panel">
      <div class="toolbar">
        <label>
          <span>用户名</span>
          <input v-model="filters.userName" type="text" placeholder="按用户名筛选" />
        </label>
        <label>
          <span>密钥名称</span>
          <input v-model="filters.keyName" type="text" placeholder="按密钥名称筛选" />
        </label>
        <label>
          <span>分发状态</span>
          <select v-model="filters.distributeStatus">
            <option value="">全部</option>
            <option value="0">待分发</option>
            <option value="1">分发中</option>
            <option value="2">分发成功</option>
            <option value="3">分发失败</option>
          </select>
        </label>
        <button @click="loadRecords">刷新</button>
      </div>
      <p class="muted">API 前缀：<code>{{ apiBase }}</code></p>
      <p v-if="errorMessage" class="error-text">{{ errorMessage }}</p>
      <div v-if="records.length === 0" class="empty-state">暂无分发记录</div>
      <div v-else class="record-list">
        <article v-for="record in records" :key="record.recordId" class="record-card">
          <div class="record-head">
            <strong>{{ record.keyName || '未命名密钥' }}</strong>
            <span class="badge" :class="`status-${record.distributeStatus || '0'}`">
              {{ statusText(record.distributeStatus) }}
            </span>
          </div>
          <p>记录 ID：{{ record.recordId }}</p>
          <p>用户名：{{ record.userName || '-' }}</p>
          <p>加密算法：{{ record.encrytName || '-' }}</p>
          <p>分发类型：{{ typeText(record.distributeType) }}</p>
          <p>分发时间：{{ record.distributeTime || '-' }}</p>
          <button class="ghost-button" @click="showDetail(record.recordId)">查看详情</button>
        </article>
      </div>
    </article>

    <article v-if="selectedRecord" class="panel">
      <div class="panel-head">
        <h3>记录详情</h3>
        <button class="ghost-button" @click="selectedRecord = null">关闭</button>
      </div>
      <div class="detail-grid">
        <p><strong>记录 ID：</strong>{{ selectedRecord.recordId }}</p>
        <p><strong>密钥 ID：</strong>{{ selectedRecord.keyId }}</p>
        <p><strong>用户名：</strong>{{ selectedRecord.userName || '-' }}</p>
        <p><strong>密钥名称：</strong>{{ selectedRecord.keyName || '-' }}</p>
        <p><strong>加密算法：</strong>{{ selectedRecord.encrytName || '-' }}</p>
        <p><strong>分发类型：</strong>{{ typeText(selectedRecord.distributeType) }}</p>
        <p><strong>分发状态：</strong>{{ statusText(selectedRecord.distributeStatus) }}</p>
        <p><strong>分发时间：</strong>{{ selectedRecord.distributeTime || '-' }}</p>
        <p><strong>区块高度：</strong>{{ selectedRecord.blockHeight ?? '-' }}</p>
        <p><strong>区块链 Hash：</strong>{{ selectedRecord.chainHash || '-' }}</p>
        <p class="detail-span"><strong>备注：</strong>{{ selectedRecord.remark || '-' }}</p>
      </div>
    </article>
  </section>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { apiBases } from '@/config/api-bases'
import { getDistributeRecord, listDistributeRecords } from '@/services/distribute-api'

const apiBase = apiBases.distributeApi
const filters = reactive({
  userName: '',
  keyName: '',
  distributeStatus: ''
})
const records = ref([])
const selectedRecord = ref(null)
const errorMessage = ref('')

onMounted(() => {
  loadRecords()
})

async function loadRecords() {
  errorMessage.value = ''
  selectedRecord.value = null
  try {
    const data = await listDistributeRecords(filters)
    records.value = data.rows || []
  } catch (error) {
    records.value = []
    errorMessage.value = error.message
  }
}

async function showDetail(recordId) {
  errorMessage.value = ''
  try {
    const data = await getDistributeRecord(recordId)
    selectedRecord.value = data.data || null
  } catch (error) {
    errorMessage.value = error.message
  }
}

function typeText(type) {
  return { 1: '初始分发', 2: '更新分发', 3: '回收后补发', '1': '初始分发', '2': '更新分发', '3': '回收后补发' }[type] || '未知'
}

function statusText(status) {
  return { 0: '待分发', 1: '分发中', 2: '分发成功', 3: '分发失败', '0': '待分发', '1': '分发中', '2': '分发成功', '3': '分发失败' }[status] || '未知'
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

.toolbar input,
.toolbar select {
  width: 100%;
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

.record-head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: center;
}

.detail-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 10px 16px;
}

.detail-span {
  grid-column: 1 / -1;
}

.status-0 { background: rgba(148, 163, 184, 0.18); }
.status-1 { background: rgba(59, 130, 246, 0.18); }
.status-2 { background: rgba(34, 197, 94, 0.18); }
.status-3 { background: rgba(239, 68, 68, 0.18); }
</style>
