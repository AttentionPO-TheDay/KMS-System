<template>
  <section class="page">
    <header class="page-head">
      <div>
        <h2>密钥分发</h2>
        <p class="page-desc">
          选择接收节点与自己的非对称密钥，系统会为每个节点和你本人各生成一份对称密钥信封。
          对称密钥由分发模块生成并保管，你手上只有用自己公钥封好的那一份 —— 有效期 24 小时。
        </p>
      </div>
    </header>

    <el-row :gutter="16">
      <!-- ------------------------------------------------------------------
           发起分发
           ------------------------------------------------------------------ -->
      <el-col :xs="24" :lg="14">
        <el-card class="panel" shadow="never">
          <template #header>
            <div class="panel-head">
              <span>发起分发</span>
              <el-tag v-if="nodes.length" size="small" type="info" effect="plain">
                可选节点 {{ nodes.length }} 个 · 单次上限 {{ maxSelectable }}
              </el-tag>
            </div>
          </template>

          <el-alert
            v-if="!nodes.length && !nodesLoading"
            title="你还没有被授权任何节点。请联系管理员在「节点鉴权」里为你授权后再分发。"
            type="warning"
            :closable="false"
            show-icon
            class="mb16"
          />

          <el-form label-width="110px" @submit.prevent>
            <el-form-item label="接收节点">
              <el-select
                v-model="form.nodeIds"
                multiple
                filterable
                collapse-tags
                collapse-tags-tooltip
                :multiple-limit="maxSelectable"
                placeholder="选择要接收该对称密钥的节点"
                class="full-width"
              >
                <el-option
                  v-for="node in nodes"
                  :key="node.nodeId"
                  :label="`${node.nodeName}（${node.nodeCode}）`"
                  :value="node.nodeId"
                />
              </el-select>
            </el-form-item>

            <!--
              封装体系 → 节点腿算法（2026-09-26）。
              抗量子不是"每次都必须"，而是与国密并列的一种选择：
                * 抗量子 → 再选 Kyber 还是 Falcon（用**节点**的抗量子公钥封装）
                * 国密   → 不额外选算法，节点腿**跟随你在下面选的那把源密钥**
                           （SM2 源密钥 → 节点腿用国密 SM2；SSCL → 国密 SSCL）
                           —— 也就是"用你自己生成的密钥"
            -->
            <el-form-item label="封装体系">
              <el-radio-group v-model="form.cryptoFamily">
                <el-radio-button label="pq">抗量子</el-radio-button>
                <el-radio-button label="gm">国密</el-radio-button>
              </el-radio-group>
            </el-form-item>

            <!-- 阶段 5（文档 §6.2）：抗量子分支下只剩 Kyber。
                 原先还有 Falcon —— 那是概念混用：Falcon 是**签名**算法，
                 不提供机密性，不能用它保护 SM4 会话密钥。
                 正确分工是 SM2/SSCL/Kyber 保护 SM4，Falcon 负责签名验签。 -->
            <el-form-item v-if="form.cryptoFamily === 'pq'" label="抗量子算法">
              <el-radio-group v-model="form.nodeWrappingAlgorithm">
                <el-radio-button label="kyber_kem">Kyber</el-radio-button>
              </el-radio-group>
            </el-form-item>

            <el-form-item label="节点封装算法">
              <el-tag size="small" type="info">{{ effectiveNodeWrappingLabel }}</el-tag>
            </el-form-item>

            <el-form-item label="我的解封密钥">
              <el-select
                v-model="form.sourceKeyId"
                filterable
                placeholder="选择给你自己解封用的非对称密钥"
                class="full-width"
              >
                <el-option
                  v-for="key in usableKeys"
                  :key="key.keyId"
                  :label="`${key.keyName}（${key.encrytName}）`"
                  :value="key.keyId"
                />
              </el-select>
            </el-form-item>

            <el-form-item label="每节点份数">
              <el-input-number v-model="form.count" :min="1" :max="100" />
            </el-form-item>

            <el-form-item>
              <el-button type="primary" :loading="submitting" :disabled="!canSubmit" @click="handleDistribute">
                分发
              </el-button>
              <el-button @click="loadNodes">刷新节点</el-button>
            </el-form-item>
          </el-form>

          <el-alert v-if="result" type="success" :closable="false" show-icon class="mt8">
            <template #title>分发完成：批次 {{ result.batchId }}</template>
            <div class="result-body">
              <p>为你本人生成 <strong>{{ result.envelopeCount }}</strong> 份信封，有效期至 {{ formatTime(result.expiresAt) }}。</p>
              <p>目标节点 {{ result.nodeCount }} 个（节点侧投递尚未接线，批次状态如实记为「部分成功」）。</p>
</div>
          </el-alert>

          <el-alert v-if="errorMessage" type="error" :closable="false" show-icon class="mt8">
            {{ errorMessage }}
          </el-alert>
        </el-card>
      </el-col>

      <!-- ------------------------------------------------------------------
           批次历史
           ------------------------------------------------------------------ -->
      <el-col :xs="24" :lg="10">
        <el-card class="panel" shadow="never">
          <template #header>
            <div class="panel-head">
              <span>我的分发批次</span>
              <el-button link type="primary" @click="loadBatches">刷新</el-button>
            </div>
          </template>

          <el-table :data="batches" size="small" v-loading="batchesLoading" empty-text="还没有分发记录">
            <el-table-column label="批次号" prop="batchId" min-width="170" show-overflow-tooltip />
            <el-table-column label="算法" prop="wrappingAlgorithm" width="76" />
            <el-table-column label="节点" width="64">
              <template #default="scope">{{ scope.row.nodeSuccessCount }}/{{ scope.row.nodeCount }}</template>
            </el-table-column>
            <el-table-column label="状态" width="88">
              <template #default="scope">
                <el-tag size="small" :type="statusType(scope.row.status)">{{ statusText(scope.row.status) }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="时间" width="150">
              <template #default="scope">{{ formatTime(scope.row.createdAt) }}</template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-col>
    </el-row>
  </section>
</template>

<script setup>
/**
 * 密钥分发页（P3 步骤 9）。
 *
 * 这里**原来是一个只读的记录查询页**（只能看历史分发记录 + Excel 导出），
 * 现在重做成真正的分发操作页。
 *
 * 三件事由服务端保证，前端只做体验优化：
 *   1. 节点列表只含**已授权给当前用户**的（D5）；
 *   2. 可选密钥只列 SM2 / SSCL（D17）—— 真正的拦截在服务端，
 *      前端过滤只是避免用户白跑一趟；
 *   3. `user_id` 由服务端从令牌解析，本页**不传也不该传**。
 */
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { listGenerateKeys } from '@/services/generate-api'
import { distributeToUser, listDistributionBatches, listUserNodes } from '@/services/user-distribution-api'

/** 用户腿允许的算法（D17）。与服务端白名单保持一致。 */
const USER_LEG_ALGORITHMS = ['SM2', 'SSCL']

const nodes = ref([])
const nodesLoading = ref(false)
const maxSelectable = ref(10)
const keys = ref([])
const batches = ref([])
const batchesLoading = ref(false)
const submitting = ref(false)
const errorMessage = ref('')
const result = ref(null)

const form = reactive({
  nodeIds: [],
  sourceKeyId: null,
  count: 1,
  cryptoFamily: 'pq',            // pq = 抗量子；gm = 国密
  nodeWrappingAlgorithm: 'kyber_kem' // 仅抗量子体系下使用
})

/**
 * 本次分发**实际**用的节点腿算法。
 *
 * 国密体系下不额外选算法：节点腿跟随所选源密钥 —— 选了 SM2 密钥就用国密 SM2，
 * 选了 SSCL 密钥就用国密 SSCL。这既符合"用你自己生成的密钥"的直觉，
 * 也避免让用户在两个地方重复表达同一件事。
 */
const effectiveNodeWrapping = computed(() => {
  if (form.cryptoFamily === 'pq') {
    return form.nodeWrappingAlgorithm
  }
  const source = usableKeys.value.find((k) => k.keyId === form.sourceKeyId)
  return String(source?.encrytName || '').toUpperCase() === 'SSCL' ? 'gm_sscl' : 'gm_sm2'
})

const effectiveNodeWrappingLabel = computed(() => ({
  kyber_kem: '抗量子 Kyber',
  falcon_lattice: '抗量子 Falcon',
  gm_sm2: '国密 SM2（跟随源密钥）',
  gm_sscl: '国密 SSCL（跟随源密钥）'
}[effectiveNodeWrapping.value] || effectiveNodeWrapping.value))

/**
 * 可用于分发的密钥，两个条件缺一不可：
 *   1) 算法必须是 SM2 / SSCL（D17 的前端侧过滤，服务端另有强制）；
 *   2) 状态必须是「有效」。
 *
 * 第 2 条是 2026-09-26 补的：此前只按算法过滤，于是**已回收的密钥照样列在
 * 下拉里**，用户选它、点分发，才吃到一个 400（后端返回 KEY_REVOKED
 * 「该密钥已被回收，不能作为分发目标」）。后端拦得住，但让用户去点一次
 * 必然失败的提交，本身就是界面在骗人 —— 回收了还能拿来封装，也会让人
 * 怀疑回收到底生效没有。
 */
const ACTIVE_STATUS = '0'
const usableKeys = computed(() =>
  keys.value.filter((key) => {
    const algorithm = String(key.encrytName || '').toUpperCase()
    const status = key.status == null ? '' : String(key.status)
    return USER_LEG_ALGORITHMS.includes(algorithm) && status === ACTIVE_STATUS
  })
)

const canSubmit = computed(() => form.nodeIds.length > 0 && Boolean(form.sourceKeyId) && !submitting.value)

async function loadNodes() {
  nodesLoading.value = true
  try {
    const data = await listUserNodes()
    nodes.value = data?.nodes || []
    maxSelectable.value = data?.maxSelectable || 10
    // 授权可能被管理员收回：把已不在列表里的选择清掉，
    // 否则提交时只会拿到一个"越权"错误，而用户看不出是自己选了个失效节点。
    const allowed = new Set(nodes.value.map((n) => n.nodeId))
    form.nodeIds = form.nodeIds.filter((id) => allowed.has(id))
  } catch (error) {
    errorMessage.value = `加载节点失败：${error.message}`
  } finally {
    nodesLoading.value = false
  }
}

async function loadKeys() {
  try {
    const data = await listGenerateKeys({ pageNum: 1, pageSize: 200 })
    keys.value = data?.rows || []
  } catch (error) {
    errorMessage.value = `加载密钥列表失败：${error.message}`
  }
}

async function loadBatches() {
  batchesLoading.value = true
  try {
    const data = await listDistributionBatches({ limit: 50 })
    batches.value = data?.items || []
  } catch (error) {
    errorMessage.value = `加载批次失败：${error.message}`
  } finally {
    batchesLoading.value = false
  }
}

async function handleDistribute() {
  if (!canSubmit.value) {
    return
  }
  submitting.value = true
  errorMessage.value = ''
  result.value = null
  try {
    const data = await distributeToUser({
      sourceKeyId: form.sourceKeyId,
      nodeIds: form.nodeIds,
      count: form.count,
      // 节点腿封装算法由用户选（抗量子 Kyber / Falcon）
      // 节点腿算法：抗量子体系下取用户选的那个；国密体系下跟随源密钥（见 effectiveNodeWrapping）
      nodeWrappingAlgorithm: effectiveNodeWrapping.value
    })
    result.value = {
      batchId: data?.batchId,
      envelopeCount: data?.userEnvelopeCount || 0,
      nodeCount: data?.nodeResults?.length || 0,
      expiresAt: data?.expiresAt
    }
    ElMessage.success('分发完成')
    await loadBatches()
  } catch (error) {
    // 服务端的拒绝理由已经足够具体（越权节点 / 算法不允许 / 超过上限），
    // 原样展示比前端再编一句更准确。
    errorMessage.value = error.message
  } finally {
    submitting.value = false
  }
}

function statusText(status) {
  return { success: '全部成功', partial: '部分成功', pending: '进行中', failed: '失败' }[status] || status || '-'
}

function statusType(status) {
  return { success: 'success', partial: 'warning', pending: 'info', failed: 'danger' }[status] || 'info'
}

function formatTime(value) {
  if (!value) {
    return '-'
  }
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString('zh-CN', { hour12: false })
}

onMounted(async () => {
  await Promise.all([loadNodes(), loadKeys(), loadBatches()])
})
</script>

<style scoped>
.page-head h2 {
  margin: 0 0 4px;
  font-size: 18px;
}

.page-desc {
  margin: 0 0 16px;
  color: var(--kms-text-secondary);
  font-size: 13px;
  line-height: 1.6;
}

.panel {
  border-radius: 10px;
}

.panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.full-width {
  width: 100%;
}

.form-hint {
  margin-top: 4px;
  color: var(--kms-text-secondary);
  font-size: 12px;
  line-height: 1.6;
}

.result-body p {
  margin: 4px 0;
  font-size: 13px;
}

.muted {
  color: var(--kms-text-secondary);
}

.mb16 {
  margin-bottom: 16px;
}

.mt8 {
  margin-top: 8px;
}
</style>
