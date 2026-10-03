<template>
  <div class="app-container">
    <el-card shadow="never">
      <template #header>
        <div class="panel-head">
          <span>会话管理</span>
          <el-button size="small" :loading="loading" @click="load">刷 新</el-button>
        </div>
      </template>

      <!--
        §10.10 会话管理（节点视角）+ KMS-011 的接收方处理流程。

        ⚠️ 只显示**元数据**，不显示 SM4 明文会话密钥。
        这不是界面取舍：服务端根本没有明文（§12「不能上传：SM4 明文会话密钥」），
        密钥只存在于会话双方各自的内存里。所以本页即使想显示也无从显示。

        隔离在**服务端**完成（`GET /pqkds-api/node-self/sessions/`）：
        按 node1/node2 外键主键过滤，不是按名字。前端不再做二次过滤 ——
        见 `@/api/pqkds/node-self` 里 listSelfSessions 的说明。

        KMS-011：我是**接收方**且会话还没走到 established 时，行上出现「处理」——
        全在本机完成：取信封 → 用发送方那一版 Falcon 公钥验签 → 用本机私钥解封
        → 自查解出的 K（sha256 与信封声明比）→ 算 HMAC proof → 回报并确认。
        每一步都**如实回报**服务端（verify/recover 端点），状态由状态机推进；
        本页不做"跳过某一步"的捷径 —— `initiated → established` 那条直跳
        在服务端就是非法的。
      -->

      <el-alert
        v-if="!loading && !mapped"
        type="info"
        :closable="false"
        show-icon
        class="mb16"
        title="当前账号没有对应的 KMS 节点"
        description="管理员账号不映射到节点，因此没有自己的会话。全系统的会话请见「密钥分发监管 → 会话监控」。"
      />

      <template v-if="mapped">
        <el-row :gutter="12" class="stat-row mb16">
          <el-col :span="6">
            <div class="stat"><div class="k">会话总数</div><div class="v">{{ all.length }}</div></div>
          </el-col>
          <el-col :span="6">
            <div class="stat"><div class="k">已建立</div><div class="v ok">{{ countBy('established') + countBy('blockchain_recorded') }}</div></div>
          </el-col>
          <el-col :span="6">
            <div class="stat"><div class="k">进行中</div><div class="v warn">{{ inProgress }}</div></div>
          </el-col>
          <el-col :span="6">
            <div class="stat"><div class="k">已过期 / 已撤销</div><div class="v danger">{{ countBy('expired') + countBy('revoked') }}</div></div>
          </el-col>
        </el-row>

        <el-form :inline="true" class="filter-bar">
          <el-form-item label="角色">
            <el-select v-model="filter.role" style="width: 160px">
              <el-option label="全部会话" value="all" />
              <el-option label="我发起的" value="sender" />
              <el-option label="我接收的" value="recipient" />
            </el-select>
          </el-form-item>
          <el-form-item label="状态">
            <el-select v-model="filter.status" clearable placeholder="全部" style="width: 170px">
              <el-option v-for="s in statusOptions" :key="s.value" :label="s.label" :value="s.value" />
            </el-select>
          </el-form-item>
          <el-form-item label="关键字">
            <el-input v-model="filter.keyword" clearable placeholder="会话ID / 对端节点" style="width: 220px" />
          </el-form-item>
          <el-form-item>
            <el-checkbox v-model="filter.includeExpired" @change="load">含已过期/已撤销</el-checkbox>
          </el-form-item>
        </el-form>

        <el-table v-loading="loading" :data="rows" border empty-text="没有符合条件的会话">
          <el-table-column label="会话 ID" prop="sessionId" min-width="190" show-overflow-tooltip />
          <el-table-column label="方向" width="100" align="center">
            <template #default="{ row }">
              <el-tag size="small" :type="row.isSender ? 'primary' : 'success'" effect="plain">
                {{ row.isSender ? '我发起' : '我接收' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="发送方" prop="senderNode" min-width="130" show-overflow-tooltip />
          <el-table-column label="接收方" prop="recipientNode" min-width="130" show-overflow-tooltip />
          <el-table-column label="保护算法" width="130">
            <template #default="{ row }">{{ typeLabel(row.protectionAlgorithm) }}</template>
          </el-table-column>
          <el-table-column label="密钥版本" min-width="180">
            <!--
              KMS-011：这条会话关联的**具体密钥版本**（计划 §7 阶段 4 第 1 条）。
              历史会话没有这些列 → 如实显示"—"，不编。
            -->
            <template #default="{ row }">
              <span v-if="row.recipientKeyId">
                接收 {{ shortId(row.recipientKeyId) }} v{{ row.recipientKeyVersion }}
              </span>
              <span v-else class="muted">接收 —</span>
              <br>
              <span v-if="row.falconKeyId" class="muted">
                签 {{ shortId(row.falconKeyId) }} v{{ row.falconKeyVersion }}
              </span>
              <span v-else class="muted">签名 —</span>
            </template>
          </el-table-column>
          <el-table-column label="状态" width="130" align="center">
            <template #default="{ row }">
              <el-tag size="small" :type="statusTag(row.status)">{{ statusLabel(row.status) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="120" align="center">
            <template #default="{ row }">
              <!-- 只有**接收方**且还没建立时才有"处理"；发送方与已建立的会话显示"—" -->
              <el-button
                v-if="row.isRecipient && canProcess(row)"
                link type="primary" size="small"
                :loading="busySession === row.sessionId"
                @click="handleProcess(row)"
              >
                处理
              </el-button>
              <span v-else class="muted">—</span>
            </template>
          </el-table-column>
          <el-table-column label="过期时间" width="170">
            <template #default="{ row }">{{ formatTime(row.expiresAt) }}</template>
          </el-table-column>
        </el-table>
      </template>
    </el-card>

    <!-- 处理结果：每一步都如实列出（验签 / 解封 / 自查 / proof / 状态），失败时停在失败那一步 -->
    <el-card v-if="progress" shadow="never" class="mt16">
      <template #header>
        <div class="panel-head">
          <span>处理会话 {{ progress.sessionId }}</span>
          <el-tag size="small" :type="progress.ok ? 'success' : 'danger'">
            {{ progress.ok ? '处理完成' : '处理中止' }}
          </el-tag>
        </div>
      </template>
      <ol class="steps">
        <li v-for="(step, index) in progress.steps" :key="index" :class="step.state">
          <b>{{ step.title }}</b>
          <span class="muted"> —— {{ step.detail }}</span>
        </li>
      </ol>
      <p v-if="progress.message" class="muted">{{ progress.message }}</p>
    </el-card>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import {
  confirmSelfSession,
  getSelfNode,
  getSessionVersions,
  listSelfEnvelopes,
  listSelfSessions,
  recoverEnvelope,
  verifyEnvelope
} from '@/api/pqkds/node-self'
import { cryptoProvider } from '@/utils/crypto/browser-provider.js'
import { buildKeyRef } from '@/utils/crypto/key-ref.js'
import {
  checkRecoveredKeyHash,
  nodeProof,
  unwrapNodeEnvelope,
  verifyNodeEnvelope
} from '@/utils/crypto/node-envelope.js'

const SESSION_TYPES = {
  aes_falcon: 'AES + Falcon',
  kyber_kem: 'Kyber 密钥协商',
  gm_sm2: '国密 SM2',
  gm_sscl: '国密 SSCL',
  falcon_lattice: 'Falcon 格密码'
}
const SESSION_STATUS = {
  initiated: '已发起',
  recipient_verified: '接收方已验签',
  key_recovered: '接收方已解封',
  established: '已建立',
  closed: '已关闭',
  blockchain_recorded: '已记录上链',
  expired: '已过期',
  revoked: '已撤销'
}

const loading = ref(false)
const mapped = ref(false)
const all = ref([])
const selfNodeId = ref('')
const filter = reactive({ role: 'all', status: '', keyword: '', includeExpired: false })
/** 正在处理的会话 ID（按钮 loading），以及上一次处理的逐步记录。 */
const busySession = ref('')
const progress = ref(null)

const typeLabel = (v) => SESSION_TYPES[v] || v || '-'
const statusLabel = (v) => SESSION_STATUS[v] || v || '-'

function statusTag(status) {
  if (status === 'established' || status === 'blockchain_recorded') return 'success'
  if (status === 'expired' || status === 'revoked') return 'danger'
  if (status === 'recipient_verified' || status === 'key_recovered') return 'primary'
  return 'warning'
}

function countBy(status) {
  return all.value.filter((s) => s.status === status).length
}

const inProgress = computed(
  () => all.value.filter((s) => !['established', 'blockchain_recorded', 'expired', 'revoked'].includes(s.status)).length
)

const statusOptions = computed(() => {
  const seen = new Map()
  all.value.forEach((s) => {
    if (s.status) seen.set(s.status, SESSION_STATUS[s.status] || s.status)
  })
  return [...seen].map(([value, label]) => ({ value, label }))
})

/** 还没走到终态的会话才需要"处理"（已建立/已关闭/过期/撤销都不必再动）。 */
function canProcess(row) {
  return !['established', 'blockchain_recorded', 'closed', 'expired', 'revoked'].includes(row.status)
}

function shortId(value) {
  const text = String(value || '')
  return text.length > 18 ? `${text.slice(0, 10)}…${text.slice(-6)}` : text
}

const rows = computed(() => {
  const kw = filter.keyword.trim().toLowerCase()
  return all.value.filter((s) => {
    if (filter.role === 'sender' && !s.isSender) return false
    if (filter.role === 'recipient' && s.isSender) return false
    if (filter.status && s.status !== filter.status) return false
    if (!kw) return true
    return [s.sessionId, s.senderNode, s.recipientNode]
      .filter(Boolean)
      .some((v) => String(v).toLowerCase().includes(kw))
  })
})

function formatTime(value) {
  if (!value) return '-'
  const d = new Date(String(value).replace(' ', 'T'))
  return Number.isNaN(d.getTime()) ? String(value) : d.toLocaleString('zh-CN', { hour12: false })
}

/** 把每一步汇成一条可读记录（成功/失败/跳过），处理中止时停在失败那一步。 */
function makeSteps() {
  const steps = []
  return {
    steps,
    add(title, state, detail) {
      steps.push({ title, state, detail })
    },
    lists() {
      return steps
    }
  }
}

/**
 * 处理一条会话（KMS-011）。全程在**本机**做密码学运算，服务端只收回报。
 *
 * 顺序是契约：取版本 → 取信封 → 验签 → 解封 → 自查 key_hash →
 * 回报 verify → 回报 recover → 算 proof → 提交确认。
 * 任何一步失败都**立即停**并如实显示停在哪一步 —— 不"跳过继续"，
 * 因为后面的每一句回报都以前面成立为前提（服务端状态机也会拒）。
 */
async function handleProcess(row) {
  const sessionId = row.sessionId
  busySession.value = sessionId
  progress.value = null
  const tracker = makeSteps()
  try {
    // ---- 1. 取这条会话的两版密钥（服务端从会话行读，不是"当前生产版"）----
    const versions = await getSessionVersions(sessionId)
    tracker.add('取密钥版本', 'ok',
      `验证用发送方 Falcon ${shortId(versions?.falconKeyId)} v${versions?.falconKeyVersion}；`
      + `解封用接收方 ${shortId(versions?.recipientKeyId)} v${versions?.recipientKeyVersion}`)
    if (!versions?.falconPublicKey) {
      tracker.add('取密钥版本', 'fail', '服务端没有可用的发送方 Falcon 公钥，无法验收（历史会话？）')
      throw new Error('缺少发送方 Falcon 公钥')
    }

    // ---- 2. 取本节点那腿信封（按会话找；服务端会带定位信息）----
    const envelopes = await listSelfEnvelopes()
    const entry = (envelopes?.items || []).find((item) => item.sessionId === sessionId)
    if (!entry) {
      tracker.add('取信封', 'fail', '本节点的信封列表里没有这条会话（可能已过期，勾选"含已过期"再试）')
      throw new Error('没有可处理的信封')
    }
    tracker.add('取信封', 'ok', `信封 #${entry.envelopeId}（${entry.wrappingAlgorithm}），密文摘要在信封内`)

    // ---- 3. 本机验签（用**发送方那一版**公钥 + 服务端同一份规范化实现）----
    const verified = await verifyNodeEnvelope({
      provider: cryptoProvider,
      envelope: entry.envelope,
      signatureB64: entry.envelope?.signature,
      senderFalconPublicKeyHex: versions.falconPublicKey
    })
    if (!verified.ok) {
      tracker.add('本机验签', 'fail', verified.detail)
      throw new Error(verified.detail)
    }
    tracker.add('本机验签', 'ok', verified.detail)

    // ---- 4. 本机解封（密钥引用必须拼自**服务端记的那一版**，不是猜）----
    const recipientKeyId = versions.recipientKeyId
    const recipientKeyVersion = Number(versions.recipientKeyVersion)
    if (!recipientKeyId || !Number.isInteger(recipientKeyVersion)) {
      tracker.add('本机解封', 'fail', '会话没有记录接收方密钥版本（历史会话），本页不做猜测解封')
      throw new Error('缺少接收方密钥版本')
    }
    const keyRef = buildKeyRef({
      nodeId: selfNodeId.value,
      algorithm: algorithmFromWrapping(versions.protectionAlgorithm || entry.wrappingAlgorithm),
      keyId: recipientKeyId,
      version: recipientKeyVersion
    })
    if (!(await cryptoProvider.hasKey(keyRef))) {
      tracker.add('本机解封', 'fail',
        `本机密钥库里没有 ${keyRef} 的私钥（换过设备或清过站点数据）—— 需回原设备处理`)
      throw new Error('本机缺少对应私钥')
    }
    const payloadKey = await unwrapNodeEnvelope({
      provider: cryptoProvider, keyRef, envelope: entry.envelope
    })
    tracker.add('本机解封', 'ok', `用 ${shortId(recipientKeyId)} v${recipientKeyVersion} 解出 16 字节 SM4`)

    // ---- 5. 自查：解出的 K 与发送方声明的是同一把 ----
    const hashCheck = await checkRecoveredKeyHash(payloadKey, entry.envelope)
    if (!hashCheck.ok) {
      tracker.add('密钥自查', 'fail', hashCheck.detail)
      throw new Error(hashCheck.detail)
    }
    tracker.add('密钥自查', 'ok', hashCheck.detail)

    // ---- 6. 回报验签通过（服务端会独立复核一次再推进状态）----
    const verifyResp = await verifyEnvelope(entry.envelopeId)
    tracker.add('回报验签通过', 'ok',
      `会话状态 → ${verifyResp?.status}${verifyResp?.advanced ? '' : '（此前已越过这一步）'}`)

    // ---- 7. 回报解封成功 ----
    const recoverResp = await recoverEnvelope(entry.envelopeId)
    tracker.add('回报解封成功', 'ok', `会话状态 → ${recoverResp?.status}`)

    // ---- 8. 算 proof 并提交（对方提交后双方一致才算建立）----
    const proof = await nodeProof({ payloadKey, sessionId })
    const confirmResp = await confirmSelfSession(sessionId, proof)
    tracker.add('提交持有证明', 'ok', confirmResp?.msg || '已提交')

    progress.value = {
      sessionId,
      ok: Boolean(confirmResp?.established) || confirmResp?.status === 'established',
      steps: tracker.lists(),
      message: confirmResp?.established
        ? '双方确认一致，会话已建立。'
        : '本机三步已如实回报；等待会话另一方确认 —— 双方 proof 一致才会提升为已建立。'
    }
    ElMessage.success(confirmResp?.established ? '会话已建立' : '本机处理完成，等待对方确认')
    await load()
  } catch (error) {
    // 失败时把已完成/失败的那几步如实留下（progress.steps 里最后一条是 fail）
    const steps = tracker.lists()
    if (!steps.some((s) => s.state === 'fail')) {
      steps.push({ title: '处理中止', state: 'fail', detail: describeError(error) })
    }
    progress.value = { sessionId, ok: false, steps, message: describeError(error) }
  } finally {
    busySession.value = ''
  }
}

/** 保护算法的规范名由信封拼写反推（收发双方的信封拼写是库内口径）。 */
function algorithmFromWrapping(wrapping) {
  const text = String(wrapping || '').toLowerCase()
  if (text === 'kyber_kem') return 'KYBER'
  if (text === 'gm_sm2') return 'SM2'
  if (text === 'gm_sscl') return 'SSCL'
  return text.toUpperCase()
}

/**
 * 把错误翻成"下一步做什么"。分支**按 `error.errorCode`**（由
 * `@/api/pqkds/http` 拦截器从 `body.data.error_code` 附上），不匹配文案 ——
 * 文案随时会改，匹配文案的失败方式是静默走错分支。
 */
function describeError(error) {
  const fallback = error?.message || String(error) || '未知错误'
  switch (error?.errorCode) {
    case 'NOT_SESSION_PARTY':
      return '只有该会话的接收方需要这两版密钥；当前节点不是接收方。'
    case 'SESSION_STATE_INVALID':
      return `这一步的顺序不对：${fallback}（请先完成前一步再重试）。`
    case 'SESSION_NOT_FOUND':
      return '会话不存在 —— 它可能刚被回收影响处理撤掉。列表已刷新。'
    case 'SIGNATURE_INVALID':
      return '服务端独立验签也未通过：信封内容与签名对不上（可能被改过）。请把它报给维护者，不要重试。'
    case 'ENVELOPE_TAMPERED':
      return '信封摘要与重算的不一致（序列化口径漂移或内容被改）。这是实现/安全问题，请联系维护者。'
    case 'NOT_ENVELOPE_RECIPIENT':
      return '这封信封不是发给当前节点的。'
    case 'ENVELOPE_NOT_FOUND':
      return '信封不存在 —— 请刷新列表后重试。'
    case 'KEY_REVOKED':
      return '这条会话依赖的长期密钥已被回收（终态）。本次会话无法继续，需要重新分发。'
    case 'KEY_EXPIRED':
      return '这条会话依赖的长期密钥已过期。需要重新分发或续期。'
    case 'KEY_VERSION_MISMATCH':
      return '会话记录的密钥版本查不到或不可用（历史会话）。请把它报给维护者。'
    case 'KEY_LOCAL_MISSING':
      return '本机密钥库里没有这把私钥（换过设备或清过站点数据）—— 需回生成密钥的那台设备处理。'
    case 'SIGNATURE_REQUIRED':
      return '该信封没有签名（历史数据），无法完成"验签通过"这一步。'
    default:
      return fallback
  }
}

async function load() {
  loading.value = true
  try {
    // 先确认这个账号是不是节点。管理员账号会得到 mapped=false ——
    // 那不是错误，是"这个账号不是节点"，不该报红。
    const self = await getSelfNode()
    mapped.value = Boolean(self?.mapped)
    selfNodeId.value = self?.node?.nodeId || ''

    if (!mapped.value) {
      all.value = []
      return
    }

    const res = await listSelfSessions({ includeExpired: filter.includeExpired })
    all.value = Array.isArray(res?.items) ? res.items : []
  } catch (error) {
    ElMessage.error(error?.message || '加载会话失败')
    all.value = []
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
.filter-bar { margin-bottom: 8px; }
.mb16 { margin-bottom: 16px; }
.mt16 { margin-top: 16px; }
.muted { color: var(--kms-text-secondary); font-size: 13px; }

.steps {
  margin: 0;
  padding-left: 20px;
}
.steps li {
  margin: 6px 0;
  font-size: 13px;
}
.steps li.fail { color: var(--kms-danger-strong, #f53f3f); }

.stat-row .stat {
  border: 1px solid var(--kms-border);
  border-radius: 8px;
  padding: 12px 16px;
  background: var(--kms-surface-2, #fafafa);
}
.stat .k {
  font-size: 13px;
  color: var(--kms-text-secondary);
  margin-bottom: 6px;
}
.stat .v {
  font-size: 22px;
  font-weight: 600;
  color: var(--kms-text-primary);
}
.stat .v.ok { color: var(--kms-success-strong, #00b42a); }
.stat .v.warn { color: var(--kms-warning-strong, #ff7d00); }
.stat .v.danger { color: var(--kms-danger-strong, #f53f3f); }
</style>
