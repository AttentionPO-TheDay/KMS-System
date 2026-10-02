<template>
  <div class="app-container">
    <el-card shadow="never">
      <template #header>
        <div class="panel-head">
          <span>预分配</span>
          <el-button size="small" :loading="loading" @click="load">刷 新</el-button>
        </div>
      </template>

      <!--
        §10.8 预分配。

        与「密钥池」（9472）的分工，两页不能合并：
          预分配 —— **动作**：为某个节点对提前准备 N 条会话密钥，指定算法与有效期
          密钥池 —— **资源**：那批已备好的密钥及其 READY/RESERVED/CONSUMED/... 状态

        发完之后本页只负责报结果，具体池项去「密钥池」看 ——
        在一页里既发起又管理池状态，会让"我刚发的这批现在怎么样了"这件事
        需要在两种数据模型之间来回跳，反而更难用。
      -->

      <el-alert
        v-if="!loading && !nodes.length"
        type="warning"
        :closable="false"
        show-icon
        class="mb16"
        title="你还没有被授权任何节点"
        description="请联系管理员在「节点管理 → 节点授权」里为你授权可通信的节点后再预分配。"
      />

      <el-form label-width="120px" class="alloc-form" @submit.prevent>
        <el-form-item label="接收节点">
          <el-select
            v-model="form.nodeIds"
            multiple
            filterable
            collapse-tags
            collapse-tags-tooltip
            :multiple-limit="maxSelectable"
            placeholder="选择接收该批预分配密钥的节点"
            class="full-width"
          >
            <!-- 选项形状与「发起分发」页保持一致（services/user-distribution-api 的
                 listUserNodes），label 用 nodeName，value 用 nodeId -->
            <el-option
              v-for="node in nodes"
              :key="node.nodeId"
              :label="`${node.nodeName}（${node.nodeCode}）`"
              :value="node.nodeId"
            />
          </el-select>
        </el-form-item>

        <el-form-item label="保护算法">
          <!-- §10.7：Falcon 不出现在保护算法选择中（它负责业务签名，不承担 SM4 加密）。
               这里对应后端 `/key-pool/generate/` 的 algorithm 参数：
                 kyber_kem      用**接收方** Kyber 公钥封装
                 falcon_lattice 用**接收方** Falcon 公钥封装
               —— 注意这与 `/key-pool/distribute/`（写死 Kyber、封装给发送方自己）
               是两条不同的路，别混用，详见 api/pqkds/distribution.js 的说明。 -->
          <el-radio-group v-model="form.algorithm">
            <el-radio label="kyber_kem">Kyber KEM（抗量子）</el-radio>
            <el-radio label="falcon_lattice">Falcon 格密码</el-radio>
          </el-radio-group>
        </el-form-item>

        <el-form-item label="数量">
          <el-input-number v-model="form.count" :min="1" :max="1000" />
          <span class="hint">单批 1 ~ 1000 条</span>
        </el-form-item>

        <el-form-item label="有效期（小时）">
          <el-input-number v-model="form.ttlHours" :min="1" :max="720" />
          <span class="hint">到期未消费的池项会被「密钥池」页的清理动作回收</span>
        </el-form-item>

        <el-form-item>
          <el-button type="primary" :loading="submitting" @click="submit">发起预分配</el-button>
          <el-button @click="reset">重 置</el-button>
        </el-form-item>
      </el-form>

      <!-- 发起结果：如实回报后端给的计数，不自己推算"应该成功几条" -->
      <template v-if="result">
        <div class="section-title">最近一次发起结果</div>
        <el-descriptions :column="2" border>
          <el-descriptions-item label="状态">
            <el-tag size="small" :type="result.ok ? 'success' : 'danger'">
              {{ result.ok ? '已提交' : '失败' }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="生成条数">
            {{ result.count ?? '-' }}
          </el-descriptions-item>
          <el-descriptions-item label="保护算法">
            {{ typeLabel(result.algorithm) }}
          </el-descriptions-item>
          <el-descriptions-item label="接收节点">
            {{ result.nodeLabels || '-' }}
          </el-descriptions-item>
          <el-descriptions-item label="说明" :span="2">
            {{ result.message || '-' }}
          </el-descriptions-item>
        </el-descriptions>
        <div class="hint" style="margin-top: 10px;">
          具体池项（状态 / 密钥哈希 / 过期时间）请在「密钥分发 → 密钥池」中查看。
        </div>
      </template>
    </el-card>
  </div>
</template>

<script setup>
/**
 * §11.2 密钥分发 → 预分配。
 *
 * 用既有的 `/pqkds-api/key-pool/generate/`（`generateNodePool`），
 * 它是唯一认 `algorithm` 参数的入口 —— 只有它能发 Falcon 格密码那一路。
 * `/key-pool/distribute/` 写死 Kyber 且封装给**发送方自己**，语义不同，不用。
 */
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { generateNodePool } from '@/api/pqkds/distribution'
import { listUserNodes } from '@/services/user-distribution-api'

const ALGORITHM_LABELS = { kyber_kem: 'Kyber KEM（抗量子）', falcon_lattice: 'Falcon 格密码' }

const loading = ref(false)
const submitting = ref(false)
const nodes = ref([])
const result = ref(null)

const form = reactive({
  nodeIds: [],
  algorithm: 'kyber_kem',
  count: 100,
  ttlHours: 24
})

const typeLabel = (v) => ALGORITHM_LABELS[v] || v || '-'

/** 与「发起分发」页同口径：单次最多选 5 个节点 */
const maxSelectable = 5

const nodeLabelMap = computed(() => {
  const map = new Map()
  nodes.value.forEach((n) => map.set(n.nodeId, n.nodeName || n.nodeCode || n.nodeId))
  return map
})

function reset() {
  form.nodeIds = []
  form.algorithm = 'kyber_kem'
  form.count = 100
  form.ttlHours = 24
}

async function submit() {
  if (!form.nodeIds.length) {
    ElMessage.warning('请先选择至少一个接收节点')
    return
  }

  submitting.value = true
  result.value = null
  try {
    const payload = {
      nodeIds: form.nodeIds,
      algorithm: form.algorithm,
      count: form.count,
      // 后端按小时接收有效期；字段名沿用分发模块既有约定
      expiresInHours: form.ttlHours
    }
    const res = await generateNodePool(payload)

    result.value = {
      ok: true,
      count: res?.count ?? res?.generated ?? form.count,
      algorithm: form.algorithm,
      nodeLabels: form.nodeIds.map((id) => nodeLabelMap.value.get(id) || id).join('、'),
      message: res?.message || `已为 ${form.nodeIds.length} 个节点发起预分配`
    }
    ElMessage.success('预分配已提交')
  } catch (error) {
    // 失败也要落到结果区，而不是只弹一条会消失的提示 ——
    // 预分配是"发出去就消耗资源"的操作，失败原因需要留在页面上可回看。
    result.value = {
      ok: false,
      count: null,
      algorithm: form.algorithm,
      nodeLabels: form.nodeIds.map((id) => nodeLabelMap.value.get(id) || id).join('、'),
      message: error?.message || '预分配失败'
    }
    ElMessage.error(error?.message || '预分配失败')
  } finally {
    submitting.value = false
  }
}

async function load() {
  loading.value = true
  try {
    nodes.value = await listUserNodes()
  } catch (error) {
    ElMessage.error(error?.message || '加载可选节点失败')
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
.mb16 { margin-bottom: 16px; }
.alloc-form { max-width: 720px; }
.full-width { width: 100%; }
.hint {
  margin-left: 10px;
  color: var(--kms-text-secondary);
  font-size: 12px;
}
.section-title {
  margin: 24px 0 10px;
  font-size: 14px;
  font-weight: 600;
  color: var(--kms-text-primary);
}
</style>
