<template>
  <div class="app-container">
    <el-card shadow="never">
      <template #header>
        <div class="kh-header">
          <h2>一致性与异常分析</h2>
          <div class="kh-query">
            <el-input
              v-model="keyId"
              placeholder="输入密钥ID"
              clearable
              style="width: 180px"
              @keyup.enter="load"
            />
            <el-button type="primary" icon="Search" :loading="loading" @click="load">检查</el-button>
          </div>
        </div>
      </template>

      <el-alert
        v-if="!keyId"
        type="info"
        :closable="false"
        show-icon
        title="输入密钥 ID 做健康检查"
        description="检查同一把密钥在数据库、版本标记、操作轨迹与链上状态之间是否一致，并按规则检测异常。"
      />

      <template v-else>
        <div v-if="result" class="kh-summary">
          <el-tag :type="healthTagType" size="large">{{ healthText }}</el-tag>
          <span class="kh-meta">
            密钥 {{ result.keyId }}（{{ result.keyName || '-' }}）· 版本 v{{ result.version }} · 状态 {{ result.status }}
          </span>
        </div>

        <el-table :data="result?.findings || []" size="small" border
                  empty-text="全部检查通过，未发现一致性问题或异常">
          <el-table-column label="级别" width="90">
            <template #default="{ row }">
              <el-tag :type="row.severity === 'ERROR' ? 'danger' : 'warning'" size="small">
                {{ row.severity === 'ERROR' ? '严重' : '警告' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="规则" prop="rule" width="170" />
          <el-table-column label="说明" prop="message" min-width="240" />
          <el-table-column label="建议" prop="advice" min-width="260" />
        </el-table>

        <!-- 观测值：给出判定的原始依据，便于人工复核。
             健康检查若只给结论不给依据，运维无法判断该不该信。 -->
        <el-collapse v-if="result?.observations?.length" class="kh-obs">
          <el-collapse-item :title="`观测值（${result.observations.length} 条）—— 判定依据，供人工核对`">
            <ul>
              <li v-for="(o, i) in result.observations" :key="i">{{ o }}</li>
            </ul>
          </el-collapse-item>
        </el-collapse>
      </template>
    </el-card>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { getKeyHealth } from '@/api/lifecycle/lifecycle'

const route = useRoute()
const keyId = ref('')
const loading = ref(false)
const result = ref(null)

const healthText = computed(() => ({
  OK: '一致，未发现异常',
  SUSPICIOUS: '发现可疑项',
  REVOKED: '已回收 / 材料不可用'
}[result.value?.health] || result.value?.health || '-'))

const healthTagType = computed(() => ({
  OK: 'success', SUSPICIOUS: 'warning', REVOKED: 'danger'
}[result.value?.health] || 'info'))

async function load() {
  const id = String(keyId.value || '').trim()
  if (!id) return
  loading.value = true
  result.value = null
  try {
    const res = await getKeyHealth(id)
    if (res?.code && res.code !== 200) {
      ElMessage.error(res.msg || '检查失败')
      return
    }
    result.value = res?.data || res
  } catch (error) {
    ElMessage.error(`检查失败：${error.message}`)
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  const q = route.query.keyId
  if (q) {
    keyId.value = String(q)
    load()
  }
})
</script>

<style scoped>
.kh-header { display: flex; align-items: center; justify-content: space-between; }
.kh-header h2 { margin: 0; font-size: 18px; }
.kh-query { display: flex; gap: 8px; }
.kh-summary { display: flex; align-items: center; gap: 12px; margin-bottom: 16px; }
.kh-meta { color: var(--kms-text-secondary, #606266); font-size: 13px; }
.kh-obs { margin-top: 16px; }
.kh-obs ul { margin: 0; padding-left: 18px; }
.kh-obs li { font-size: 12px; line-height: 1.9; color: var(--kms-text-secondary, #606266); }
</style>