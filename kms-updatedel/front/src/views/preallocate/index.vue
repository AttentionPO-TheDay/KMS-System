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
        任务书 §20「密钥预分配」。
        规范：发送节点在实际通信之前**在本机**生成 N 条随机 SM4、用接收节点的
        Kyber 公钥封成保护包、**用本地 Falcon 私钥签名**，再上传到密钥池；
        服务端只保存/调度/管理保护包（它解不开、也不生成 K）。
        实际建立会话时在「发起分发」页取用一条 —— 与本页的分工：
          预分配 —— **备料**：先备好 N 条，之后每次会话直接取一条；
          发起分发 —— **用**：取用一条（或现场封装）。
      -->

      <el-alert
        v-if="!loading && !nodes.length"
        type="warning"
        :closable="false"
        show-icon
        class="mb16"
        title="你还没有被授权任何节点"
        description="请先在「节点授权」中申请通信权限。"
      />

      <TechnicalView ref="technicalFlow" kind="preallocation" />
      <el-form label-width="120px" class="alloc-form" @submit.prevent>
        <el-form-item label="接收节点">
          <el-select
            v-model="form.nodeCode"
            filterable
            placeholder="选择接收方（这批密钥的解封方）"
            class="full-width"
            :disabled="!nodes.length"
          >
            <!-- 只为**已授权**的对端备料：预分配是分发的前置动作，
                 没有授权时备了也用不了（服务端同样会拒）。 -->
            <el-option
              v-for="node in nodes"
              :key="node.nodeCode"
              :label="`${node.nodeName}（${node.nodeCode}）`"
              :value="node.nodeCode"
            />
          </el-select>

        </el-form-item>

        <el-form-item label="保护算法">
          <!-- 预分配固定使用 Kyber 保护包；SM2/SSCL 是「发起分发」页的现场封装算法。 -->
          <el-tag size="small" type="success" effect="plain">Kyber（格密码）</el-tag>

        </el-form-item>

        <el-form-item label="数量">
          <el-input-number v-model="form.count" :min="1" :max="maxCount" />
          <span class="hint">
            1 ~ {{ maxCount }} 条
          </span>
        </el-form-item>

        <el-form-item label="有效期（小时）">
          <el-input-number v-model="form.ttlHours" :min="1" :max="720" />

        </el-form-item>

        <el-form-item label="签名密钥">
          <el-tag v-if="falconReady" size="small" type="success" effect="plain">
            {{ falconKey?.keyId }} v{{ falconKey?.keyVersion }}
          </el-tag>
          <el-tag v-else size="small" type="danger" effect="plain">本机不可用</el-tag>

        </el-form-item>

        <el-form-item>
          <el-button type="primary" :loading="submitting" :disabled="!canSubmit" @click="submit">
            发起预分配
          </el-button>
          <el-button @click="reset">重 置</el-button>
        </el-form-item>
      </el-form>

      <!-- 这里只展示本次业务操作结果。验收阈值、通过/失败和证据回传均由
           验收测试台的独立流程负责，普通预分配不得隐式触发。 -->
      <template v-if="result">
        <div class="section-title">最近一次预分配结果</div>
        <el-descriptions :column="2" border>
          <el-descriptions-item label="任务 ID">
            <span class="mono">{{ result.poolId }}</span>
          </el-descriptions-item>
          <el-descriptions-item label="接收节点">
            <span class="mono">{{ result.nodeCode }}</span>
          </el-descriptions-item>
          <el-descriptions-item label="总数量">{{ result.requested }}</el-descriptions-item>
          <el-descriptions-item label="完成数量">
            <b :class="result.generated === result.requested ? 'ok' : 'warn'">{{ result.generated }}</b>
          </el-descriptions-item>
          <el-descriptions-item label="失败数量">
            <b :class="result.failed.length ? 'warn' : 'ok'">{{ result.failed.length }}</b>
          </el-descriptions-item>
          <el-descriptions-item label="有效期至">{{ formatTime(result.expiresAt) }}</el-descriptions-item>
          <el-descriptions-item label="耗时（本机封装）">
            {{ result.localMs }} ms
          </el-descriptions-item>
          <el-descriptions-item label="耗时（服务端）">
            {{ result.serverMs }} ms
          </el-descriptions-item>
        </el-descriptions>

        <el-alert
          v-if="result.failed.length"
          type="warning"
          :closable="false"
          show-icon
          class="mt8"
        >
          <template #title>{{ result.failed.length }} 条未通过（其余已入池）</template>
          <div class="result-body">
            <p v-for="item in result.failed.slice(0, 8)" :key="item.index">
              第 {{ item.index + 1 }} 条：{{ item.message || item.errorCode }}
            </p>
            <p v-if="result.failed.length > 8" class="muted">
              （还有 {{ result.failed.length - 8 }} 条，见服务端日志）
            </p>
          </div>
        </el-alert>


      </template>
    </el-card>
  </div>
</template>

<script setup>
/**
 * 任务书 §20 密钥预分配。
 *
 * 三条与旧实现的差别（旧页面**从未成功过**，见 PROJECT_PROGRESS）：
 *   1. 参数名对上了：旧的发 `nodeIds: [...]`，而服务端只读 `node1_id`/`node2_id`
 *      → 永久 400「缺少 node1_id 或 node2_id」；
 *   2. K 在**本机**生成（旧实现由服务端生成 —— 那与"服务端不接触 SM4 明文"相抵）；
 *   3. 结果区按 §20 显示六项读数（旧页面一项都没有）。
 *
 * 数据流：本机生成 SM4 → `wrapForPeer(KYBER, 接收方公钥)` → `signNodeEnvelope`
 * → 分批 `POST /node-self/pool/preallocate/` → 服务端逐条验签后入池。
 */
import { computed, onMounted, reactive, ref } from 'vue'
import TechnicalView from '@/components/TechnicalView/index.vue'
import { ElMessage } from 'element-plus'
import {
  getSelfNode,
  listSelfNodeKeys,
  preallocatePool
} from '@/api/pqkds/node-self'
import { listUserNodes } from '@/services/user-distribution-api'
import { cryptoProvider } from '@/utils/crypto/browser-provider.js'
import { buildKeyRef } from '@/utils/crypto/key-ref.js'
import { sealPoolSecret, markPoolSecretsUploaded } from '@/utils/crypto/node-key-store.js'
import {
  buildNodeEnvelope,
  generatePayloadKey,
  signNodeEnvelope
} from '@/utils/crypto/envelope-signing.js'

/** 服务端单次上传上限（`node_self_views.MAX_POOL_ITEMS_PER_BATCH`）。 */
const chunkSize = 200
/** 页面单批上限（任务书 §20 的示例是 1000 条）。 */
const maxCount = 1000

const loading = ref(false)
const submitting = ref(false)
const nodes = ref([])
const result = ref(null)
const technicalFlow = ref(null)
const selfNodeId = ref('')
const falconKey = ref(null)
const falconReady = ref(false)

const form = reactive({
  nodeCode: '',
  count: 100,
  ttlHours: 24
})

const canSubmit = computed(() => Boolean(
  form.nodeCode && falconReady.value && !submitting.value && form.count >= 1
))

function reset() {
  form.nodeCode = ''
  form.count = 100
  form.ttlHours = 24
}

/** 本机那把可用的 Falcon 私钥（与服务端登记表**两个条件都要满足**）。 */
async function loadFalconKey() {
  falconKey.value = null
  falconReady.value = false
  if (!selfNodeId.value) {
    return
  }
  try {
    const data = await listSelfNodeKeys()
    const candidates = (data?.keys || []).filter(
      (k) => k.algorithm === 'FALCON' && k.allowsNewWork === true
    )
    for (const candidate of candidates) {
      const ref = buildKeyRef({
        nodeId: selfNodeId.value,
        algorithm: 'FALCON',
        keyId: candidate.keyId,
        version: candidate.keyVersion
      })
      if (await cryptoProvider.hasKey(ref)) {
        falconKey.value = { ...candidate, keyRef: ref }
        falconReady.value = true
        return
      }
    }
  } catch (error) {
    ElMessage.error(`加载本机签名密钥失败：${error?.message || error}`)
  }
}

/**
 * 接收方**当前可用**的那一版 Kyber 公钥。
 *
 * ⚠️ 拿服务端 `peers/<编号>/keys/` 返回的 `publicKey`（已是比对形式的小写 hex），
 *    并用 `allowsNewWork` 判它能不能用于新工作 —— **不在前端另写一套状态判断**。
 */
async function fetchPeerKyberKey(nodeCode) {
  const { default: http, unwrap } = await import('@/api/pqkds/http')
  const data = await http
    .get(`/node-self/peers/${encodeURIComponent(nodeCode)}/keys/`, {
      params: { algorithm: 'KYBER' }
    })
    .then(unwrap)
  const key = (data?.keys || []).find((k) => k.allowsNewWork === true)
  if (!key) {
    throw new Error(`对端 ${nodeCode} 没有可用于新工作的 Kyber 公钥版本`)
  }
  return key
}

async function submit() {
  if (!canSubmit.value) {
    return
  }
  submitting.value = true
  result.value = null
  const nodeId = selfNodeId.value, peerNodeId = form.nodeCode, requested = Number(form.count)
  technicalFlow.value?.start({ nodeId, peerNodeId, algorithm: 'KYBER', requested })
  try {
    technicalFlow.value?.stage('peer', 'running', '读取接收节点当前可用公钥')
    const peerKey = await fetchPeerKyberKey(peerNodeId)
    technicalFlow.value?.stage('peer', 'success', '接收公钥及版本已取得', { keyId: peerKey.keyId, version: peerKey.keyVersion })
    // 池号与有效期**必须在签名之前**定下（它们进签名：`batch_id`/`expires_at`）。
    const poolId = `pool_${toHex(crypto.getRandomValues(new Uint8Array(16)))}`
    const expiresAt = new Date(Date.now() + Number(form.ttlHours) * 3600 * 1000).toISOString()
    technicalFlow.value?.record('预分配批次与有效期已绑定', { poolId, expiresAt })
    technicalFlow.value?.stage('prepare', 'running', '逐条生成载荷密钥、封装保护包并签名', { generated: 0, wrapped: 0, signed: 0 })

    // ---- 本机生成 + 封装 + 签名（任务书那句"提前生成…形成加密保护包"）----
    const t0 = performance.now()
    const items = []
    for (let i = 0; i < requested; i++) {
      const payloadKey = generatePayloadKey()
      try {
        technicalFlow.value?.progress('prepare', { generated: i + 1 })
        const built = await buildNodeEnvelope({
          provider: cryptoProvider,
          payloadKey,
          wrapping: 'KYBER',
          recipientPublicKeyHex: peerKey.publicKey,
          batchId: poolId,
          senderNodeId: nodeId,
          receiverNodeId: peerNodeId,
          recipientKeyId: peerKey.keyId,
          recipientKeyVersion: peerKey.keyVersion,
          expiresAt
        })
        technicalFlow.value?.progress('prepare', { wrapped: i + 1 })
        const signature = await signNodeEnvelope(cryptoProvider, falconKey.value.keyRef, built.envelope)
        technicalFlow.value?.progress('prepare', { signed: i + 1 })
        // Retain the sender's K before upload; consume later binds it to a session.
        await sealPoolSecret({ nodeId, peerNodeId, poolId, keyHash: built.keyHash, expiresAt }, payloadKey)
        items.push({ envelope: built.envelope, signature, keyHash: built.keyHash })
      } finally { payloadKey.fill(0) }
    }
    const localMs = performance.now() - t0
    technicalFlow.value?.stage('prepare', 'success', '本机保护包全部准备完成', { prepared: items.length })

    // ---- 分批上传（服务端逐条验签；一批太大响应时间不可控）----
    let generated = 0
    const failed = []
    let serverMs = 0
    technicalFlow.value?.stage('submit', 'running', '上传保护包，等待服务端逐批入池回执', { uploaded: 0, accepted: 0, rejected: 0 })
    for (let start = 0; start < items.length; start += chunkSize) {
      const chunk = items.slice(start, start + chunkSize)
      const data = await preallocatePool({
        targetNodeCode: peerNodeId,
        poolId,
        expiresAt,
        items: chunk,
        falconKeyId: falconKey.value.keyId,
        falconKeyVersion: falconKey.value.keyVersion
      })
      generated += Number(data?.generated || 0)
      serverMs += Number(data?.serverMs || 0)
      for (const item of (data?.failed || [])) {
        failed.push({ ...item, index: start + Number(item.index || 0) })
      }
      technicalFlow.value?.progress('submit', { uploaded: start + chunk.length, accepted: generated, rejected: failed.length })
      technicalFlow.value?.record('服务端批次入池响应', { accepted: generated, rejected: failed.length })
      const rejected = new Set((data?.failed || []).map(item => Number(item.index)))
      const accepted = chunk.filter((_item, index) => !rejected.has(index))
      if (Number(data?.generated) === accepted.length) {
        await markPoolSecretsUploaded(nodeId, poolId, accepted.map(item => item.keyHash))
      }
    }

    technicalFlow.value?.stage('submit', generated === items.length ? 'success' : (generated > 0 ? 'partial' : 'failed'), '本次入池回执已汇总', { accepted: generated, rejected: failed.length })
    result.value = {
      poolId,
      nodeCode: peerNodeId,
      requested: items.length,
      generated,
      failed,
      expiresAt,
      localMs: Math.round(localMs),
      serverMs: Math.round(serverMs * 10) / 10
    }
    if (generated) {
      ElMessage.success(`已入池 ${generated} 条（${poolId}）`)
    }
    if (failed.length) {
      // 部分成功**如实说**：不能因为"有成功的"就把失败那几条吞掉。
      ElMessage.warning(`${failed.length} 条未通过，原因见下方明细`)
    }
    technicalFlow.value?.finish(generated === items.length ? 'success' : (generated > 0 ? 'partial' : 'failed'), '本次预分配响应汇总', { accepted: generated, rejected: failed.length })
  } catch (error) {
    technicalFlow.value?.finish('failed', '预分配中断，保留已收到的业务记录')
    ElMessage.error(error?.errorCode ? error.message : (error?.message || '预分配失败'))
  } finally {
    submitting.value = false
  }
}

async function load() {
  loading.value = true
  try {
    const data = await listUserNodes()
    nodes.value = data?.nodes || []
    const allowed = new Set(nodes.value.map((n) => n.nodeCode))
    if (form.nodeCode && !allowed.has(form.nodeCode)) {
      form.nodeCode = ''
    }
  } catch (error) {
    ElMessage.error(`加载可选节点失败：${error?.message || error}`)
    nodes.value = []
  } finally {
    loading.value = false
  }
}

function formatTime(value) {
  if (!value) return '-'
  return String(value).replace('T', ' ').slice(0, 19)
}

function toHex(bytes) {
  return Array.from(bytes).map((b) => b.toString(16).padStart(2, '0')).join('')
}

onMounted(async () => {
  await load()
  try {
    const self = await getSelfNode()
    selfNodeId.value = self?.node?.nodeId || ''
  } catch { /* 未映射时后续提交会被服务端拒，页面已禁用按钮 */ }
  await loadFalconKey()
})
</script>

<style scoped>
.panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.mb16 { margin-bottom: 16px; }
.mt8 { margin-top: 8px; }
.alloc-form { max-width: 760px; }
.full-width { width: 100%; }
.hint {
  margin-left: 10px;
  color: var(--kms-text-secondary);
  font-size: 12px;
}
.mono {
  font-family: 'JetBrains Mono', Consolas, monospace;
  font-size: 13px;
}
.section-title {
  margin: 24px 0 10px;
  font-size: 14px;
  font-weight: 600;
  color: var(--kms-text-primary);
}
.ok { color: var(--el-color-success); }
.warn { color: var(--el-color-warning); }
</style>
