<template>
  <section class="page">
    <div class="page-header">
      <p class="eyebrow">Generate</p>
      <h2>生成记录与公共参数</h2>
      <p>统一前端已直接读取生成系统记录，并支持查询单条详情与公共参数。</p>
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
          <span>算法名称</span>
          <input v-model="filters.encrytName" type="text" placeholder="如 AES / SM2 / SSCL" />
        </label>
        <button @click="loadKeys">刷新</button>
      </div>
      <p>API 前缀：<code>{{ apiBase }}</code></p>
      <RouterLink class="inline-link" to="/permissions">申请查看公共密钥列表</RouterLink>
      <p v-if="errorMessage" class="error-text">{{ errorMessage }}</p>
      <div v-if="keys.length === 0" class="empty-state">暂无生成记录</div>
      <div v-else class="record-list">
        <article v-for="key in keys" :key="key.keyId" class="record-card">
          <div class="record-head">
            <strong>{{ key.keyName || '未命名密钥' }}</strong>
            <span class="badge">{{ key.encrytName || '-' }}</span>
          </div>
          <p>密钥 ID：{{ key.keyId }}</p>
          <p>用户：{{ key.userName || '-' }}</p>
          <p>用途：{{ key.keyUse || '-' }}</p>
          <p>链上状态：{{ chainStatusText(key.chainStatus) }}</p>
          <button class="ghost-button" @click="showDetail(key.keyId)">查看详情</button>
        </article>
      </div>
    </article>

    <article class="panel">
      <div class="panel-head">
        <h3>公共参数查询</h3>
      </div>
      <div class="toolbar compact">
        <label>
          <span>算法类型</span>
          <select v-model="paramForm.encrytType">
            <option value="">请选择</option>
            <option value="无证书非对称加密">无证书非对称加密</option>
            <option value="对称加密">对称加密</option>
            <option value="非对称加密">非对称加密</option>
            <option value="单向加密">单向加密</option>
          </select>
        </label>
        <label>
          <span>算法名称</span>
          <input v-model="paramForm.encrytName" type="text" placeholder="例如 SSCL / SM2 / AES" />
        </label>
        <button @click="loadParams">查询公共参数</button>
      </div>
      <pre v-if="commonParams" class="json-block">{{ JSON.stringify(commonParams, null, 2) }}</pre>
    </article>

    <article v-if="selectedKey" class="panel">
      <div class="panel-head">
        <h3>生成详情</h3>
        <button class="ghost-button" @click="selectedKey = null">关闭</button>
      </div>
      <div class="detail-grid">
        <p><strong>密钥 ID：</strong>{{ selectedKey.keyId }}</p>
        <p><strong>用户 ID：</strong>{{ selectedKey.userId }}</p>
        <p><strong>用户名：</strong>{{ selectedKey.userName || '-' }}</p>
        <p><strong>算法类型：</strong>{{ selectedKey.encrytType || '-' }}</p>
        <p><strong>算法名称：</strong>{{ selectedKey.encrytName || '-' }}</p>
        <p><strong>密钥用途：</strong>{{ selectedKey.keyUse || '-' }}</p>
        <p><strong>状态：</strong>{{ selectedKey.status || '-' }}</p>
        <p><strong>链上状态：</strong>{{ chainStatusText(selectedKey.chainStatus) }}</p>
        <p><strong>创建时间：</strong>{{ selectedKey.creTime || '-' }}</p>
        <p><strong>更新时间：</strong>{{ selectedKey.updTime || '-' }}</p>
        <p class="detail-span"><strong>密钥值：</strong>{{ selectedKey.keyValue || '-' }}</p>
      </div>
    </article>
  </section>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { apiBases } from '@/config/api-bases'
import { getCommonParams, getGenerateKey, listGenerateKeys } from '@/services/generate-api'

const apiBase = apiBases.generateApi
const filters = reactive({ userId: '', userName: '', encrytName: '' })
const paramForm = reactive({ encrytType: '', encrytName: '' })
const keys = ref([])
const selectedKey = ref(null)
const commonParams = ref(null)
const errorMessage = ref('')

onMounted(() => {
  loadKeys()
})

async function loadKeys() {
  errorMessage.value = ''
  try {
    const data = await listGenerateKeys(filters)
    keys.value = data.rows || []
  } catch (error) {
    keys.value = []
    errorMessage.value = error.message
  }
}

async function showDetail(keyId) {
  errorMessage.value = ''
  try {
    const data = await getGenerateKey(keyId)
    selectedKey.value = data.data || null
  } catch (error) {
    errorMessage.value = error.message
  }
}

async function loadParams() {
  errorMessage.value = ''
  if (!paramForm.encrytType || !paramForm.encrytName.trim()) {
    errorMessage.value = '请先填写算法类型和算法名称。'
    return
  }
  try {
    commonParams.value = await getCommonParams(paramForm)
  } catch (error) {
    commonParams.value = null
    errorMessage.value = error.message
  }
}

function chainStatusText(status) {
  return { 0: '待上链', 1: '已上链', 2: '上链失败', '0': '待上链', '1': '已上链', '2': '上链失败' }[status] || (status ?? '未知')
}
</script>

<style scoped>
.toolbar {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: 12px;
  align-items: end;
}

.toolbar.compact {
  grid-template-columns: repeat(auto-fit, minmax(180px, 240px));
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

.json-block {
  margin: 0;
  padding: 16px;
  border-radius: 16px;
  background: #0f172a;
  color: #e2e8f0;
  overflow: auto;
}
</style>
