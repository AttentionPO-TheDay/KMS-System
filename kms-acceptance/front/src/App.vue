<script setup>
import { computed, onMounted, ref } from 'vue'

const securitySuites = [
  {
    id: 'generate-attacks',
    name: '生成系统 3 类攻击',
    accent: 'accent-red',
    summary: '按验收口径展示生成系统 3 类攻击：重放、篡改、越权，重点验证密钥生成入口与用户态访问边界。',
    cases: [
      {
        caseId: 'generate-replay',
        title: '重放攻击',
        mode: '浏览器 + Postman',
        target: 'POST 生成请求',
        expected: '重复发送不应造成不可控重复有效业务结果。',
        steps: ['登录 testuser 并在用户密钥页抓取生成请求', 'Copy as cURL 后延迟 5 秒再重放']
      },
      {
        caseId: 'generate-tamper',
        title: '篡改攻击',
        mode: 'Postman',
        target: '公钥内容、公钥长度、公钥前缀',
        expected: '非法公钥、非法长度、非法前缀应被拒绝。',
        steps: ['将合法公钥改成非法曲线点', '分别改成 64 长度和 05 前缀重发']
      },
      {
        caseId: 'generate-privilege',
        title: '越权攻击',
        mode: '双 Token 对照',
        target: '公共密钥列表、非本人数据访问',
        expected: '普通用户不能访问管理员口径数据或他人密钥。',
        steps: ['分别登录普通用户与管理员获取 JWT', '用普通用户 Token 访问高权限接口']
      }
    ]
  },
  {
    id: 'lifecycle-attacks',
    name: '更新与回收 5 类攻击',
    accent: 'accent-orange',
    summary: '按验收口径展示更新与回收系统 5 类攻击：SQL 注入、XSS、重放、篡改、越权。',
    cases: [
      {
        caseId: 'lifecycle-sql',
        title: 'SQL 注入',
        mode: '半自动',
        target: '我的密钥、结果查询、操作记录查询条件',
        expected: '仅返回正常参数校验或空结果，不应出现异常 SQL 行为。',
        steps: ['对 keyName、actionType、record query 注入 SQL payload', '检查响应和列表结果是否异常']
      },
      {
        caseId: 'lifecycle-xss',
        title: 'XSS',
        mode: '半自动',
        target: '更新时可编辑的 keyName、keyUse、keyDomain',
        expected: '恶意脚本不应在我的密钥、详情、结果页执行。',
        steps: ['提交带 script/onload payload 的更新请求', '刷新列表和详情页确认仅文本显示']
      },
      {
        caseId: 'lifecycle-replay',
        title: '重放攻击',
        mode: '浏览器 + Postman',
        target: 'UPDATE_KEY / REVOKE_KEY 请求',
        expected: '重复请求不应造成越权或失控状态流转。',
        steps: ['抓取更新或回收请求', '延迟后重放并检查结果记录与状态变化']
      },
      {
        caseId: 'lifecycle-tamper',
        title: '篡改攻击',
        mode: 'Postman',
        target: 'keyId、user、body 字段',
        expected: '伪造用户、伪造 keyId、非法字段组合应被拒绝或无效。',
        steps: ['将 keyId 改为他人密钥或不存在的 key', '篡改 user、autoUpdate、domain 后重发']
      },
      {
        caseId: 'lifecycle-privilege',
        title: '越权攻击',
        mode: '双 Token 对照',
        target: '他人密钥更新与回收',
        expected: '普通用户不能操作他人 key，403/业务拒绝应可见。',
        steps: ['使用普通用户 Token 对 foreign key 发更新/回收', '验证返回和结果记录']
      }
    ]
  },
  {
    id: 'platform-protection',
    name: '平台防护验证',
    accent: 'accent-purple',
    summary: '验证扫描器拦截、登录暴破、点击劫持等平台级能力，和业务攻击区分展示。',
    cases: [
      {
        title: '扫描工具识别',
        mode: '自动化脚本',
        target: 'SmartSecurityFilter',
        expected: '恶意 User-Agent 访问应返回 403，后续访问进入黑名单窗口。',
        steps: ['运行 security/security_test.ps1', '观察 sqlmap User-Agent 探测返回码']
      },
      {
        title: '登录暴力破解',
        mode: '自动化脚本',
        target: '登录限流与锁定',
        expected: '连续 5 次错误后，第 6 次仍处于锁定窗口。',
        steps: ['脚本模拟 6 次错误登录', '检查锁定提示与 Redis 计数效果']
      },
      {
        title: '点击劫持',
        mode: '自动化 + 浏览器',
        target: '响应头与 iframe 嵌套行为',
        expected: '当前基线为 SAMEORIGIN；若要求更严，需要后续收紧为 deny/frame-ancestors none。',
        steps: ['检查 X-Frame-Options/CSP 响应头', '使用 iframe 页面嵌套验证']
      }
    ]
  }
]

const securityAssets = [
  { name: '安全测试总方案', path: 'doc/security-test-plan.md', desc: '覆盖攻击范围、执行方式、预期结果与后续加固建议。' },
  { name: '自动化脚本入口', path: 'security/security_test.ps1', desc: '包含扫描器探测、登录暴破、点击劫持响应头检查等基线脚本。' }
]

const scenarios = ref([])
const runs = ref([])
const securityRuns = ref([])
const proofRuns = ref([])
const health = ref(null)
const loading = ref(false)
const proofLoading = ref(false)
const securityLoadingCaseId = ref('')
const error = ref('')
const apiBase = import.meta.env.VITE_APP_ACCEPTANCE_API || '/acceptance-api'

const form = ref({
  scenarioId: '',
  baseUrl: '',
  path: '',
  threads: 12,
  connections: 400,
  durationSeconds: 30,
  body: '',
  headersText: '',
  wrkPath: ''
})

const proofForm = ref({
  batchSize: 5,
  treeFanout: 4,
  proofMode: 'semi_honest',
  lifecycleBaseUrl: ''
})

const activeScenario = computed(() => {
  return scenarios.value.find((item) => item.id === form.value.scenarioId) || null
})

const passCount = computed(() => runs.value.filter((item) => item.status === 'passed').length)
const securityCaseCount = computed(() => securitySuites.reduce((total, suite) => total + suite.cases.length, 0))
const latestProofRun = computed(() => proofRuns.value[0] || null)
const proofParentGroups = computed(() => {
  const run = latestProofRun.value
  if (!run || !run.records) {
    return []
  }
  const groups = new Map()
  for (const record of run.records) {
    const key = record.parentBatchId || 'parent'
    if (!groups.has(key)) {
      groups.set(key, [])
    }
    groups.get(key).push(record)
  }
  return Array.from(groups.entries()).map(([parent, leaves]) => ({
    parent,
    leaves: leaves.sort((a, b) => Number(a.nodeIndex || 0) - Number(b.nodeIndex || 0))
  }))
})

function applyScenario(scenario) {
  if (!scenario) {
    return
  }
  form.value.scenarioId = scenario.id
  form.value.baseUrl = scenario.baseUrl
  form.value.path = scenario.path
  form.value.threads = scenario.threads
  form.value.connections = scenario.connections
  form.value.durationSeconds = scenario.durationSeconds
  form.value.body = scenario.bodyTemplate
  form.value.headersText = Object.entries(scenario.headers || {})
    .map(([key, value]) => `${key}: ${value}`)
    .join('\n')
}

async function loadHealth() {
  const response = await fetch(`${apiBase}/health`)
  health.value = await response.json()
}

async function loadScenarios() {
  const response = await fetch(`${apiBase}/scenarios`)
  const payload = await response.json()
  scenarios.value = payload.data || []
  if (!form.value.scenarioId && scenarios.value.length > 0) {
    applyScenario(scenarios.value[0])
  }
}

async function loadRuns() {
  const response = await fetch(`${apiBase}/runs`)
  const payload = await response.json()
  runs.value = payload.data || []
}

async function loadSecurityRuns() {
  const response = await fetch(`${apiBase}/security/runs`)
  const payload = await response.json()
  securityRuns.value = payload.data || []
}

async function loadProofRuns() {
  const response = await fetch(`${apiBase}/proof/runs`)
  const payload = await response.json()
  proofRuns.value = payload.data || []
}

async function runScenario() {
  error.value = ''
  loading.value = true
  try {
    const response = await fetch(`${apiBase}/runs`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        scenarioId: form.value.scenarioId,
        baseUrl: form.value.baseUrl,
        path: form.value.path,
        threads: Number(form.value.threads),
        connections: Number(form.value.connections),
        durationSeconds: Number(form.value.durationSeconds),
        body: form.value.body,
        headers: form.value.headersText
          .split('\n')
          .map((line) => line.trim())
          .filter(Boolean),
        wrkPath: form.value.wrkPath
      })
    })

    const payload = await response.json()
    if (!response.ok) {
      throw new Error(payload.message || payload.error || '执行失败')
    }
    await loadRuns()
  } catch (err) {
    error.value = err.message
  } finally {
    loading.value = false
  }
}

async function runSecurityCase(caseId) {
  error.value = ''
  securityLoadingCaseId.value = caseId
  try {
    const response = await fetch(`${apiBase}/security/runs`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({ caseId })
    })
    const payload = await response.json()
    if (!response.ok) {
      throw new Error(payload.message || payload.error || '安全攻击执行失败')
    }
    await loadSecurityRuns()
  } catch (err) {
    error.value = err.message
  } finally {
    securityLoadingCaseId.value = ''
  }
}

async function runProofVisualTest() {
  error.value = ''
  proofLoading.value = true
  try {
    const response = await fetch(`${apiBase}/proof/runs`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        batchSize: Number(proofForm.value.batchSize),
        treeFanout: Number(proofForm.value.treeFanout),
        proofMode: proofForm.value.proofMode,
        lifecycleBaseUrl: proofForm.value.lifecycleBaseUrl
      })
    })
    const payload = await response.json()
    if (!response.ok) {
      throw new Error(payload.message || payload.error || '可视化证明测试执行失败')
    }
    await loadProofRuns()
  } catch (err) {
    error.value = err.message
  } finally {
    proofLoading.value = false
  }
}

function latestSecurityRun(caseId) {
  return securityRuns.value.find((item) => item.caseId === caseId) || null
}

function securityVerdictLabel(caseId) {
  const item = latestSecurityRun(caseId)
  if (!item) {
    return '未执行'
  }
  if (item.status === 'error') {
    return '执行失败'
  }
  return item.passed ? '已拦截' : '存在风险'
}

function securityVerdictClass(caseId) {
  const item = latestSecurityRun(caseId)
  if (!item) {
    return 'warn'
  }
  if (item.status === 'error') {
    return 'accent-red'
  }
  return item.passed ? 'ok' : 'accent-orange'
}

function metricLabel(item) {
  if (!item.metricCheck || !item.metricCheck.kind) {
    return '未采集'
  }
  return `${item.metricCheck.value?.toFixed?.(2) || item.metricCheck.value}% / ${item.metricCheck.target}%`
}

function proofStatusClass(check) {
  if (!check) {
    return 'warn'
  }
  return check.passed ? 'ok' : 'accent-orange'
}

function proofStatusLabel(check) {
  if (!check) {
    return '未执行'
  }
  return check.passed ? '通过' : '未通过'
}

function shortHash(value) {
  if (!value) {
    return '-'
  }
  if (value.length <= 18) {
    return value
  }
  return `${value.slice(0, 12)}...${value.slice(-4)}`
}

onMounted(async () => {
  await Promise.all([loadHealth(), loadScenarios(), loadRuns(), loadSecurityRuns(), loadProofRuns()])
})
</script>

<template>
  <main class="page-shell">
    <section class="hero">
      <div>
        <p class="eyebrow">KMS Acceptance</p>
        <h1>测试系统</h1>
        <p class="hero-copy">
          独立前后端的测试系统，用于执行 `wrk` 压测、汇总 TPS 指标，并支撑联调验证与回收率判定。
        </p>
      </div>
      <div class="hero-cards">
        <article class="stat-card accent-green">
          <span>场景数</span>
          <strong>{{ scenarios.length }}</strong>
        </article>
        <article class="stat-card accent-blue">
          <span>历史执行</span>
          <strong>{{ runs.length }}</strong>
        </article>
        <article class="stat-card accent-purple">
          <span>通过次数</span>
          <strong>{{ passCount }}</strong>
        </article>
      </div>
    </section>

    <section class="grid two-columns">
      <article class="panel">
        <div class="panel-header">
          <h2>执行配置</h2>
          <span class="badge" :class="health?.wrkAvailable ? 'ok' : 'warn'">
            {{ health?.wrkAvailable ? 'wrk 已发现' : 'wrk 未发现' }}
          </span>
        </div>

        <label class="field">
          <span>测试场景</span>
          <select v-model="form.scenarioId" @change="applyScenario(activeScenario)">
            <option v-for="scenario in scenarios" :key="scenario.id" :value="scenario.id">
              {{ scenario.name }}
            </option>
          </select>
        </label>

        <div v-if="activeScenario" class="scenario-note">
          <p>{{ activeScenario.description }}</p>
          <ul>
            <li v-for="note in activeScenario.notes || []" :key="note">{{ note }}</li>
          </ul>
        </div>

        <div class="field-row">
          <label class="field">
            <span>Base URL</span>
            <input v-model="form.baseUrl" />
          </label>
          <label class="field">
            <span>Path</span>
            <input v-model="form.path" />
          </label>
        </div>

        <div class="field-row triple">
          <label class="field">
            <span>Threads</span>
            <input v-model="form.threads" type="number" min="1" />
          </label>
          <label class="field">
            <span>Connections</span>
            <input v-model="form.connections" type="number" min="1" />
          </label>
          <label class="field">
            <span>Duration(s)</span>
            <input v-model="form.durationSeconds" type="number" min="1" />
          </label>
        </div>

        <label class="field">
          <span>Headers</span>
          <textarea v-model="form.headersText" rows="4" />
        </label>

        <label class="field">
          <span>Request Body</span>
          <textarea v-model="form.body" rows="8" />
        </label>

        <label class="field">
          <span>Wrk Path</span>
          <input v-model="form.wrkPath" placeholder="为空则使用后端自动探测路径" />
        </label>

        <div class="actions">
          <button class="primary" :disabled="loading || !form.scenarioId" @click="runScenario">
            {{ loading ? '执行中...' : '启动测试' }}
          </button>
          <button class="ghost" @click="loadRuns">刷新历史</button>
        </div>
        <p v-if="error" class="error-text">{{ error }}</p>
      </article>

      <article class="panel status-panel">
        <div class="panel-header">
          <h2>运行环境</h2>
        </div>
        <dl class="meta-list">
          <div>
            <dt>服务状态</dt>
            <dd>{{ health?.status || '-' }}</dd>
          </div>
          <div>
            <dt>wrk 路径</dt>
            <dd>{{ health?.wrkPath || '未发现' }}</dd>
          </div>
          <div>
            <dt>结果目录</dt>
            <dd>{{ health?.dataDir || '-' }}</dd>
          </div>
          <div>
            <dt>时间</dt>
            <dd>{{ health?.now || '-' }}</dd>
          </div>
          <div>
            <dt>验收用户</dt>
            <dd>{{ health?.acceptanceUser || '-' }}</dd>
          </div>
        </dl>
        <div class="callout">
          <h3>当前回收率口径</h3>
          <p>
            生成、更新、回收默认都直接压 Go 接口并自动携带内部 token。回收率场景会在压测结束后去生命周期 Java
            内部接口核验 `status=3`，按最终状态计算回收率。
          </p>
        </div>
      </article>
    </section>

    <section class="panel">
      <div class="panel-header">
        <h2>执行历史</h2>
      </div>
      <div class="history-list">
        <article v-for="item in runs" :key="item.id" class="history-item">
          <div class="history-top">
            <div>
              <h3>{{ item.scenario }}</h3>
              <p>{{ item.startedAt }} <span v-if="item.finishedAt">-> {{ item.finishedAt }}</span></p>
            </div>
            <span class="badge" :class="item.status === 'passed' ? 'ok' : 'warn'">{{ item.status }}</span>
          </div>

          <div class="history-metrics">
            <div>
              <span>TPS</span>
              <strong>{{ item.summary.requestsPerSec?.toFixed?.(2) || '0.00' }}</strong>
              <small>目标 {{ item.targetTps }}</small>
            </div>
            <div>
              <span>平均延迟</span>
              <strong>{{ item.summary.avgLatencyMs?.toFixed?.(2) || '0.00' }} ms</strong>
            </div>
            <div>
              <span>P99</span>
              <strong>{{ item.summary.p99LatencyMs?.toFixed?.(2) || '0.00' }} ms</strong>
            </div>
            <div>
              <span>附加指标</span>
              <strong>{{ metricLabel(item) }}</strong>
            </div>
          </div>

          <details class="raw-output">
            <summary>查看 wrk 输出</summary>
            <pre>{{ item.summary.rawOutput }}</pre>
          </details>
        </article>
        <p v-if="runs.length === 0" class="empty-text">还没有测试记录。</p>
      </div>
    </section>

    <section class="panel proof-panel">
      <div class="panel-header">
        <div>
          <h2>树型更新与半诚实证明可视化测试</h2>
          <p class="proof-intro">小批量触发 BATCH_UPDATE_KEYS，自动读取批次证明记录，展示树型节点、承诺摘要、一致性摘要与批次根验证结果。</p>
        </div>
        <span class="badge" :class="latestProofRun?.passed ? 'ok' : 'warn'">
          {{ latestProofRun?.passed ? '最近一次通过' : '等待验证' }}
        </span>
      </div>

      <div class="proof-config">
        <label class="field">
          <span>批量 key 数</span>
          <input v-model="proofForm.batchSize" type="number" min="1" max="32" />
        </label>
        <label class="field">
          <span>树扇出</span>
          <input v-model="proofForm.treeFanout" type="number" min="2" max="128" />
        </label>
        <label class="field">
          <span>证明模式</span>
          <input v-model="proofForm.proofMode" />
        </label>
        <label class="field">
          <span>Lifecycle Go Base URL</span>
          <input v-model="proofForm.lifecycleBaseUrl" placeholder="为空时使用后端默认 UPDATE_KEY 地址" />
        </label>
        <div class="proof-actions">
          <button class="primary" :disabled="proofLoading" @click="runProofVisualTest">
            {{ proofLoading ? '执行中...' : '执行可视化测试' }}
          </button>
          <button class="ghost" @click="loadProofRuns">刷新结果</button>
        </div>
      </div>

      <div v-if="latestProofRun" class="proof-grid">
        <article class="proof-card">
          <div class="proof-card-head">
            <h3>树型结构测试</h3>
            <span class="badge" :class="proofStatusClass(latestProofRun.treeCheck)">{{ proofStatusLabel(latestProofRun.treeCheck) }}</span>
          </div>
          <p>{{ latestProofRun.treeCheck?.message }}</p>
          <div class="proof-tree">
            <div class="tree-root">
              <span>Batch Root</span>
              <strong>{{ shortHash(latestProofRun.summary?.batchRoot) }}</strong>
            </div>
            <div class="tree-parents">
              <div v-for="group in proofParentGroups" :key="group.parent" class="tree-parent">
                <div class="parent-node">
                  <span>Parent</span>
                  <strong>{{ shortHash(group.parent) }}</strong>
                </div>
                <div class="leaf-row">
                  <div v-for="leaf in group.leaves" :key="leaf.recordId" class="leaf-node">
                    <span>#{{ leaf.nodeIndex }}</span>
                    <strong>Key {{ leaf.keyId }}</strong>
                    <small>{{ leaf.treePath }}</small>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </article>

        <article class="proof-card">
          <div class="proof-card-head">
            <h3>半诚实证明测试</h3>
            <span class="badge" :class="proofStatusClass(latestProofRun.proofCheck)">{{ proofStatusLabel(latestProofRun.proofCheck) }}</span>
          </div>
          <p>{{ latestProofRun.proofCheck?.message }}</p>
          <div class="proof-flow">
            <div>
              <span>更新承诺</span>
              <strong>{{ latestProofRun.summary?.allCommitmentsPresent ? '完整' : '缺失' }}</strong>
            </div>
            <div>
              <span>一致性摘要</span>
              <strong>{{ latestProofRun.summary?.allConsistencyHashesPresent ? '完整' : '缺失' }}</strong>
            </div>
            <div>
              <span>验证状态</span>
              <strong>{{ latestProofRun.summary?.verifyStatus || '-' }}</strong>
            </div>
            <div>
              <span>验证说明</span>
              <strong>{{ latestProofRun.summary?.verifyMessage || '-' }}</strong>
            </div>
          </div>
          <div class="proof-records">
            <article v-for="record in latestProofRun.records || []" :key="record.recordId">
              <span>Key {{ record.keyId }} / v{{ record.keyVersion }}</span>
              <code>commitment {{ shortHash(record.commitment) }}</code>
              <code>consistency {{ shortHash(record.consistencyHash) }}</code>
            </article>
          </div>
        </article>
      </div>

      <p v-else class="empty-text">还没有可视化证明测试记录。</p>
    </section>

    <section class="panel security-panel">
      <div class="panel-header">
        <h2>安全测试总览</h2>
        <span class="badge" :class="health?.securityAvailable ? 'ok' : 'warn'">{{ securityCaseCount }} 个攻击场景</span>
      </div>
      <p class="security-intro">
        这里直接执行生成 3 类、更新与回收 5 类真实攻击。平台防护项仍保留为资产入口，业务攻击结果会回填到每张卡片。
      </p>

      <div class="asset-grid">
        <article v-for="asset in securityAssets" :key="asset.path" class="asset-card">
          <span class="asset-label">资产</span>
          <strong>{{ asset.name }}</strong>
          <code>{{ asset.path }}</code>
          <p>{{ asset.desc }}</p>
        </article>
      </div>

      <div class="security-suite-grid">
        <article v-for="suite in securitySuites" :key="suite.id" class="suite-card">
          <div class="suite-head">
            <div>
              <p class="suite-kicker">Security Suite</p>
              <h3>{{ suite.name }}</h3>
            </div>
            <span class="badge" :class="suite.accent">{{ suite.cases.length }} 项</span>
          </div>
          <p class="suite-summary">{{ suite.summary }}</p>

          <div class="attack-list">
            <article v-for="item in suite.cases" :key="`${suite.id}-${item.title}`" class="attack-card">
              <div class="attack-head">
                <div>
                  <h4>{{ item.title }}</h4>
                  <span>{{ item.mode }}</span>
                </div>
                <span v-if="item.caseId" class="badge" :class="securityVerdictClass(item.caseId)">{{ securityVerdictLabel(item.caseId) }}</span>
              </div>
              <p><strong>目标：</strong>{{ item.target }}</p>
              <p><strong>预期：</strong>{{ item.expected }}</p>
              <ul>
                <li v-for="step in item.steps" :key="step">{{ step }}</li>
              </ul>
              <div v-if="item.caseId" class="attack-actions">
                <button class="ghost" :disabled="securityLoadingCaseId === item.caseId || !health?.securityAvailable" @click="runSecurityCase(item.caseId)">
                  {{ securityLoadingCaseId === item.caseId ? '执行中...' : '执行真实攻击' }}
                </button>
              </div>
              <div v-if="item.caseId && latestSecurityRun(item.caseId)" class="attack-result">
                <p><strong>结论：</strong>{{ latestSecurityRun(item.caseId).summary }}</p>
                <p v-if="latestSecurityRun(item.caseId).error"><strong>错误：</strong>{{ latestSecurityRun(item.caseId).error }}</p>
                <ul v-if="latestSecurityRun(item.caseId).notes?.length">
                  <li v-for="note in latestSecurityRun(item.caseId).notes" :key="note">{{ note }}</li>
                </ul>
                <details v-if="latestSecurityRun(item.caseId).requests?.length" class="raw-output">
                  <summary>查看攻击请求</summary>
                  <pre>{{ JSON.stringify(latestSecurityRun(item.caseId).requests, null, 2) }}</pre>
                </details>
              </div>
            </article>
          </div>
        </article>
      </div>
    </section>
  </main>
</template>

<style scoped>
.page-shell {
  max-width: 1400px;
  margin: 0 auto;
  padding: 32px 20px 64px;
}

.hero {
  display: grid;
  grid-template-columns: 1.4fr 1fr;
  gap: 20px;
  margin-bottom: 24px;
}

.eyebrow {
  margin: 0 0 12px;
  color: #7dd3fc;
  letter-spacing: 0.16em;
  text-transform: uppercase;
  font-size: 12px;
}

h1,
h2,
h3,
p {
  margin: 0;
}

h1 {
  font-size: clamp(32px, 5vw, 52px);
  line-height: 1;
}

.hero-copy {
  margin-top: 16px;
  max-width: 760px;
  color: #9fb3c8;
  line-height: 1.7;
}

.hero-cards {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px;
}

.stat-card,
.panel,
.history-item {
  background: rgba(6, 18, 33, 0.8);
  border: 1px solid rgba(148, 163, 184, 0.18);
  border-radius: 20px;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.28);
  backdrop-filter: blur(12px);
}

.stat-card {
  min-height: 132px;
  padding: 20px;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
}

.stat-card span {
  color: #9fb3c8;
}

.stat-card strong {
  font-size: 38px;
}

.accent-green {
  background: linear-gradient(135deg, rgba(22, 101, 52, 0.45), rgba(6, 18, 33, 0.92));
}

.accent-blue {
  background: linear-gradient(135deg, rgba(14, 116, 144, 0.45), rgba(6, 18, 33, 0.92));
}

.accent-purple {
  background: linear-gradient(135deg, rgba(91, 33, 182, 0.45), rgba(6, 18, 33, 0.92));
}

.accent-red {
  color: #fecaca;
  background: rgba(127, 29, 29, 0.4);
  border-color: rgba(248, 113, 113, 0.35);
}

.accent-orange {
  color: #fdba74;
  background: rgba(124, 45, 18, 0.42);
  border-color: rgba(251, 146, 60, 0.35);
}

.grid.two-columns {
  display: grid;
  grid-template-columns: 1.4fr 0.9fr;
  gap: 20px;
  margin-bottom: 24px;
}

.panel {
  padding: 24px;
}

.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 20px;
}

.badge {
  border-radius: 999px;
  padding: 6px 12px;
  font-size: 12px;
  border: 1px solid transparent;
}

.badge.ok {
  color: #86efac;
  background: rgba(20, 83, 45, 0.45);
  border-color: rgba(34, 197, 94, 0.3);
}

.badge.warn {
  color: #fde68a;
  background: rgba(120, 53, 15, 0.45);
  border-color: rgba(251, 191, 36, 0.3);
}

.field,
.meta-list div {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.field {
  margin-bottom: 16px;
}

.field span,
.meta-list dt,
.history-metrics span,
.scenario-note li,
.history-top p,
.empty-text {
  color: #9fb3c8;
}

.field-row {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 16px;
}

.field-row.triple {
  grid-template-columns: repeat(3, 1fr);
}

input,
textarea,
select {
  width: 100%;
  border: 1px solid rgba(148, 163, 184, 0.2);
  border-radius: 14px;
  background: rgba(15, 23, 42, 0.78);
  color: #f8fafc;
  padding: 12px 14px;
}

textarea {
  resize: vertical;
  min-height: 110px;
}

.scenario-note,
.callout {
  margin-bottom: 16px;
  padding: 16px;
  border-radius: 16px;
  background: rgba(15, 23, 42, 0.72);
  border: 1px solid rgba(125, 211, 252, 0.16);
}

.scenario-note ul {
  margin: 12px 0 0;
  padding-left: 18px;
}

.meta-list {
  display: grid;
  gap: 16px;
  margin: 0 0 20px;
}

.meta-list dd {
  margin: 0;
  font-weight: 600;
  word-break: break-all;
}

.actions {
  display: flex;
  gap: 12px;
  margin-top: 8px;
}

button {
  border: 0;
  border-radius: 999px;
  padding: 12px 18px;
  cursor: pointer;
}

button.primary {
  background: linear-gradient(135deg, #38bdf8, #22c55e);
  color: #04111f;
  font-weight: 700;
}

button.ghost {
  background: rgba(15, 23, 42, 0.78);
  color: #e2e8f0;
  border: 1px solid rgba(148, 163, 184, 0.2);
}

button:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.error-text {
  margin-top: 14px;
  color: #fca5a5;
}

.history-list {
  display: grid;
  gap: 16px;
}

.proof-panel,
.security-panel {
  margin-top: 24px;
}

.proof-intro {
  margin-top: 8px;
  color: #9fb3c8;
  line-height: 1.6;
}

.proof-config {
  display: grid;
  grid-template-columns: 0.7fr 0.7fr 0.9fr 1.5fr auto;
  gap: 14px;
  align-items: end;
  margin-bottom: 20px;
}

.proof-config .field {
  margin-bottom: 0;
}

.proof-actions {
  display: flex;
  gap: 10px;
  margin-bottom: 0;
}

.proof-grid {
  display: grid;
  grid-template-columns: 1.15fr 0.85fr;
  gap: 16px;
}

.proof-card {
  padding: 18px;
  border-radius: 18px;
  border: 1px solid rgba(148, 163, 184, 0.18);
  background: rgba(15, 23, 42, 0.68);
}

.proof-card-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
  margin-bottom: 10px;
}

.proof-card p,
.tree-root span,
.parent-node span,
.leaf-node span,
.leaf-node small,
.proof-flow span,
.proof-records span {
  color: #9fb3c8;
}

.proof-tree {
  margin-top: 18px;
  display: grid;
  gap: 16px;
}

.tree-root,
.parent-node,
.leaf-node,
.proof-flow div,
.proof-records article {
  border-radius: 8px;
  border: 1px solid rgba(125, 211, 252, 0.22);
  background: rgba(2, 6, 23, 0.55);
}

.tree-root {
  padding: 16px;
  text-align: center;
}

.tree-root strong,
.parent-node strong,
.leaf-node strong {
  display: block;
  margin-top: 6px;
  word-break: break-all;
}

.tree-parents {
  display: grid;
  gap: 14px;
}

.tree-parent {
  display: grid;
  gap: 10px;
}

.parent-node {
  padding: 12px;
}

.leaf-row {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(130px, 1fr));
  gap: 10px;
}

.leaf-node {
  min-height: 104px;
  padding: 12px;
}

.leaf-node small {
  display: block;
  margin-top: 8px;
  word-break: break-all;
}

.proof-flow {
  margin-top: 18px;
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

.proof-flow div {
  padding: 14px;
}

.proof-flow strong {
  display: block;
  margin-top: 6px;
  word-break: break-word;
}

.proof-records {
  margin-top: 16px;
  display: grid;
  gap: 10px;
  max-height: 320px;
  overflow: auto;
}

.proof-records article {
  padding: 12px;
}

.proof-records code {
  display: block;
  margin-top: 6px;
  color: #7dd3fc;
  word-break: break-all;
}

.security-intro,
.suite-summary,
.asset-card p,
.attack-card p,
.attack-card li,
.suite-kicker,
.asset-label,
.attack-head span {
  color: #9fb3c8;
}

.asset-grid,
.security-suite-grid,
.attack-list {
  display: grid;
  gap: 16px;
}

.asset-grid {
  grid-template-columns: repeat(2, minmax(0, 1fr));
  margin: 18px 0 22px;
}

.security-suite-grid {
  grid-template-columns: repeat(3, minmax(0, 1fr));
}

.asset-card,
.suite-card,
.attack-card {
  border-radius: 18px;
  border: 1px solid rgba(148, 163, 184, 0.18);
  background: rgba(15, 23, 42, 0.68);
}

.asset-card,
.suite-card {
  padding: 18px;
}

.asset-card code {
  display: block;
  margin: 8px 0 10px;
  color: #7dd3fc;
  word-break: break-all;
}

.suite-head,
.attack-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.suite-kicker,
.asset-label {
  text-transform: uppercase;
  letter-spacing: 0.14em;
  font-size: 11px;
  margin-bottom: 8px;
}

.attack-card {
  padding: 16px;
}

.attack-card strong {
  color: #f8fafc;
}

.attack-card ul {
  margin: 10px 0 0;
  padding-left: 18px;
}

.attack-actions {
  margin-top: 14px;
}

.attack-result {
  margin-top: 14px;
  padding: 14px;
  border-radius: 14px;
  background: rgba(2, 6, 23, 0.68);
  border: 1px solid rgba(148, 163, 184, 0.16);
}

.attack-result p + p {
  margin-top: 8px;
}

.history-item {
  padding: 20px;
}

.history-top {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.history-metrics {
  margin-top: 18px;
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
}

.history-metrics div {
  padding: 14px;
  border-radius: 14px;
  background: rgba(15, 23, 42, 0.72);
}

.history-metrics strong {
  display: block;
  margin-top: 6px;
  font-size: 18px;
}

.history-metrics small {
  display: block;
  margin-top: 6px;
  color: #64748b;
}

.raw-output {
  margin-top: 16px;
}

.raw-output summary {
  cursor: pointer;
  color: #7dd3fc;
}

pre {
  margin: 12px 0 0;
  padding: 16px;
  overflow: auto;
  border-radius: 16px;
  background: #020617;
  color: #cbd5e1;
}

@media (max-width: 1024px) {
  .hero,
  .grid.two-columns {
    grid-template-columns: 1fr;
  }

  .history-metrics,
  .hero-cards,
  .proof-grid,
  .proof-config,
  .security-suite-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (max-width: 720px) {
  .page-shell {
    padding: 20px 14px 48px;
  }

  .field-row,
  .field-row.triple,
  .history-metrics,
  .hero-cards,
  .proof-grid,
  .proof-config,
  .proof-flow,
  .asset-grid,
  .security-suite-grid {
    grid-template-columns: 1fr;
  }

  .history-top,
  .panel-header,
  .actions {
    flex-direction: column;
    align-items: stretch;
  }
}
</style>
