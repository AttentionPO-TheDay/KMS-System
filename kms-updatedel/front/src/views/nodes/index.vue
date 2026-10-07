<template>
  <div class="app-container">
    <el-card class="panel" shadow="never">
      <template #header>
        <div class="panel-head">
          <span>节点管理</span>
          <div class="panel-actions">
            <el-button size="small" :loading="loading" @click="load">刷 新</el-button>
            <el-button
              size="small"
              :disabled="!missingFalcon.length || falconBatchRunning"
              :loading="falconBatchRunning"
              @click="handleBatchGenerateFalcon"
            >
              {{ falconBatchRunning
                ? `生成中 ${falconBatchDone}/${falconBatchTotal}`
                : `批量生成 Falcon${missingFalcon.length ? `（${missingFalcon.length}）` : ''}` }}
            </el-button>
            <el-button size="small" type="danger" :disabled="!selected.length" @click="handleBatchDelete">
              批量删除{{ selected.length ? `（${selected.length}）` : '' }}
            </el-button>
            <el-button size="small" type="primary" @click="openCreate">新增演示节点</el-button>
          </div>
        </div>
      </template>

<el-form :inline="true" class="filter-bar">
        <el-form-item label="关键字">
          <el-input
            v-model="filter.keyword"
            clearable
            placeholder="节点ID / 名称 / IP"
            style="width: 220px"
            @keyup.enter="load"
          />
        </el-form-item>
        <el-form-item label="类型">
          <el-select v-model="filter.nodeType" clearable placeholder="全部" style="width: 150px">
            <el-option v-for="t in NODE_TYPES" :key="t.value" :label="t.label" :value="t.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="状态">
          <el-select v-model="filter.status" clearable placeholder="全部" style="width: 170px">
            <el-option v-for="s in NODE_STATUS" :key="s.value" :label="s.label" :value="s.value" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="load">查询</el-button>
          <el-button @click="resetFilter">重置</el-button>
        </el-form-item>
      </el-form>

      <el-table
        :data="rows"
        size="small"
        v-loading="loading"
        row-key="id"
        empty-text="还没有节点，点右上角「新增演示节点」建一个"
        @selection-change="(v) => (selected = v)"
      >
        <el-table-column type="selection" width="42" />
        <el-table-column label="节点ID" min-width="150" prop="node_id" show-overflow-tooltip />
        <el-table-column label="名称" min-width="140" prop="name" show-overflow-tooltip />
        <el-table-column label="地址" min-width="160">
          <template #default="scope">{{ scope.row.ip_address }}:{{ scope.row.port }}</template>
        </el-table-column>
        <el-table-column label="类型" width="100">
          <template #default="scope">{{ typeLabel(scope.row.node_type) }}</template>
        </el-table-column>
        <el-table-column label="状态" width="120">
          <template #default="scope">
            <el-tag size="small" :type="statusTagType(scope.row.status)">
              {{ statusLabel(scope.row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <!--
          三个密钥列都只读**就绪布尔值**（*_key_ready）。
          列表接口刻意不返回公钥本身 —— falcon_public_key 实测 7.8MB/节点，
          带上它列表会到几十 MB 并最终压垮 gunicorn 的 120s 超时。
          公钥内容在「密钥」弹窗里按需取（/nodes/{id}/keys/）。
        -->
        <el-table-column label="Kyber 密钥" width="110" align="center">
          <template #default="scope">
            <el-tag v-if="scope.row.kyber_key_ready" size="small" type="success">已就绪</el-tag>
            <el-tag v-else size="small" type="info">未生成</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="Falcon 密钥" width="110" align="center">
          <template #default="scope">
            <!-- 批量生成时逐行反映进度：Falcon 要 ~17s，页面上必须看得见在跑 -->
            <el-tooltip
              v-if="falconState[scope.row.node_id] === 'running'"
              content="正在生成 Falcon 密钥（约需十几秒）"
              placement="top"
            >
              <el-tag size="small" type="warning" effect="plain">生成中…</el-tag>
            </el-tooltip>
            <el-tooltip
              v-else-if="falconState[scope.row.node_id] === 'failed'"
              :content="falconError[scope.row.node_id] || '生成失败'"
              placement="top"
            >
              <el-tag size="small" type="danger" effect="plain">生成失败</el-tag>
            </el-tooltip>
            <el-tag v-else-if="scope.row.falcon_key_ready" size="small" type="success">已就绪</el-tag>
            <el-tag v-else size="small" type="info">未生成</el-tag>
          </template>
        </el-table-column>
        <!-- 国密密钥（SM2 + SSCL）：分发时选「国密」体系要用它对节点封装 —— 2026-09-26 新增 -->
        <el-table-column label="国密密钥" width="110" align="center">
          <template #default="scope">
            <el-tag v-if="scope.row.gm_key_ready && scope.row.sscl_key_ready" size="small" type="success">已就绪</el-tag>
            <el-tag v-else-if="scope.row.gm_key_ready || scope.row.sscl_key_ready" size="small" type="warning">部分就绪</el-tag>
            <el-tag v-else size="small" type="info">未生成</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="组织" min-width="120" prop="organization" show-overflow-tooltip />
        <el-table-column label="最后活跃" width="170">
          <template #default="scope">{{ formatTime(scope.row.last_active) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="260" fixed="right">
          <template #default="scope">
            <el-button link type="primary" size="small" @click="openEdit(scope.row)">编辑</el-button>
            <el-button link type="primary" size="small" @click="openKeys(scope.row)">密钥</el-button>
            <!-- 重签凭证：节点没有口令，凭证是它上线的唯一入口，
                 所以这个动作放在列表里常驻，而不是藏在某个二级页面 -->
            <el-button link type="warning" size="small" @click="handleReissue(scope.row)">重签凭证</el-button>
            <el-button link type="danger" size="small" @click="handleDelete(scope.row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="table-foot">共 {{ rows.length }} 个节点</div>
    </el-card>

    <!-- 新增 -->
    <el-dialog v-model="createOpen" title="新增演示节点" width="620px">
      <el-form ref="createFormRef" :model="createForm" :rules="createRules" label-width="110px">
        <el-form-item label="节点ID" prop="node_id">
          <el-input v-model="createForm.node_id" placeholder="例如 DEMO-NODE-03（唯一）" />
        </el-form-item>
        <el-form-item label="节点名称" prop="name">
          <el-input v-model="createForm.name" placeholder="例如 演示节点3" />
        </el-form-item>
        <el-form-item label="IP 地址" prop="ip_address">
          <el-input v-model="createForm.ip_address" placeholder="例如 127.0.0.13" />
        </el-form-item>
        <el-form-item label="端口" prop="port">
          <el-input-number v-model="createForm.port" :min="1" :max="65535" controls-position="right" />
        </el-form-item>
        <el-form-item label="节点类型">
          <el-select v-model="createForm.node_type" style="width: 100%">
            <el-option v-for="t in NODE_TYPES" :key="t.value" :label="t.label" :value="t.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="所属组织">
          <el-input v-model="createForm.organization" />
        </el-form-item>
        <el-form-item label="联系人">
          <el-input v-model="createForm.contact_person" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="createForm.description" type="textarea" :rows="2" />
        </el-form-item>
      </el-form>
      <el-alert type="warning" :closable="false" show-icon>
        <!--
          ⚠️ 这里原先写"会生成 Kyber + 国密 + Falcon 三套密钥、约需 20 秒"——
             那是**改造前**的行为。现在 `provision_node` 只创建节点记录与登录账号，
             四套基础密钥在节点**首次登录时于本机浏览器**生成（文档 §2.4 / §3.1）。
             继续沿用旧文案会让人以为密钥已经在服务端了，
             恰好与"私钥不出本机"这条边界相反。
        -->
        新增只创建节点与登录账号，<b>不在服务端生成任何密钥</b>。
        四套基础密钥（SM2 / SSCL / Kyber / Falcon）由节点首次登录时在
        <b>本机浏览器</b>生成，私钥只留在那台设备上。
        创建完成后会显示一次<b>激活凭证</b>，请交给节点操作者。
      </el-alert>
      <div v-if="createError" class="dialog-error">{{ createError }}</div>
      <template #footer>
        <el-button @click="createOpen = false">取 消</el-button>
        <el-button type="primary" :loading="creating" @click="submitCreate">确 定</el-button>
      </template>
    </el-dialog>

    <!-- 编辑 -->
    <el-dialog v-model="editOpen" title="编辑节点" width="620px">
      <el-form :model="editForm" label-width="110px">
        <el-form-item label="节点ID">
          <el-input :model-value="editForm.node_id" disabled />
</el-form-item>
        <el-form-item label="所属组织">
          <el-input v-model="editForm.organization" />
        </el-form-item>
        <el-form-item label="部门">
          <el-input v-model="editForm.department" />
        </el-form-item>
        <el-form-item label="联系人">
          <el-input v-model="editForm.contact_person" />
        </el-form-item>
        <el-form-item label="手机号">
          <el-input v-model="editForm.phone" />
        </el-form-item>
        <el-form-item label="邮箱">
          <el-input v-model="editForm.email" />
        </el-form-item>
        <el-form-item label="物理位置">
          <el-input v-model="editForm.location" />
        </el-form-item>
        <el-form-item label="节点类型">
          <el-select v-model="editForm.node_type" style="width: 100%">
            <el-option v-for="t in NODE_TYPES" :key="t.value" :label="t.label" :value="t.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="标签">
          <el-input v-model="editForm.tags" placeholder="逗号分隔" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="editForm.description" type="textarea" :rows="2" />
        </el-form-item>
      </el-form>
      <div v-if="editError" class="dialog-error">{{ editError }}</div>
      <template #footer>
        <el-button @click="editOpen = false">取 消</el-button>
        <el-button type="primary" :loading="saving" @click="submitEdit">保 存</el-button>
      </template>
    </el-dialog>

    <!-- 密钥概览 -->
    <el-dialog v-model="keysOpen" :title="`节点密钥：${keysNode.node_id || ''}`" width="640px">
      <div v-loading="keysLoading">
        <el-descriptions :column="1" border size="small">
          <el-descriptions-item label="节点状态">{{ statusLabel(keysNode.status) }}</el-descriptions-item>
          <el-descriptions-item label="Kyber 安全级别">{{ keysNode.kyber_security_level || '-' }}</el-descriptions-item>
          <el-descriptions-item label="Falcon 安全级别">{{ keysNode.falcon_security_level || '-' }}</el-descriptions-item>
          <el-descriptions-item label="已接收部分私钥">
            {{ keysNode.partial_key_received ? '是' : '否' }}
          </el-descriptions-item>
          <!--
            这里只显示**指纹**（前 64 字符），不是完整公钥。
            falcon_public_key 完整值实测 17MB，全部拉回来渲染会把弹窗卡死几秒；
            而这一屏的用途只是确认"生成了没有 / 是不是同一把"。
            要看完整值请用分发模块后台的「查看详情」，或直接查库。
          -->
          <el-descriptions-item label="Kyber 公钥">
            <code v-if="keysNode.kyber_key_ready" class="key-line">{{ keysNode.kyber_public_key_fingerprint }}</code>
            <span v-else class="muted">（未生成）</span>
          </el-descriptions-item>
          <el-descriptions-item label="Falcon 公钥">
            <code v-if="keysNode.falcon_key_ready" class="key-line">{{ keysNode.falcon_public_key_fingerprint }}</code>
            <span v-else class="muted">（未生成）</span>
          </el-descriptions-item>
          <el-descriptions-item label="国密公钥（SM2）">
            <code class="key-line">{{ keysNode.gm_public_key || '（未生成）' }}</code>
          </el-descriptions-item>
          <el-descriptions-item label="国密公钥（SSCL）">
            <code class="key-line">{{ keysNode.sscl_public_key || '（未生成）' }}</code>
          </el-descriptions-item>
        </el-descriptions>
        <div class="fingerprint-hint">
          Kyber / Falcon 仅展示公钥指纹（前 64 字符）—— Falcon 公钥完整值约 17MB，
          全量加载会让弹窗卡顿。国密公钥较短，显示完整值。
        </div>
        <div v-if="keysError" class="dialog-error">{{ keysError }}</div>
      </div>
      <template #footer>
        <el-button @click="keysOpen = false">关 闭</el-button>
        <el-button :loading="gmGenerating" :disabled="!keysNode.id" @click="handleGenerateGm">
          {{ keysNode.gm_key_ready ? '重新生成国密密钥' : '生成国密密钥' }}
        </el-button>
        <el-button
          type="primary"
          :loading="falconGenerating"
          :disabled="!keysNode.id"
          @click="handleGenerateFalcon"
        >
          {{ keysNode.falcon_key_ready ? '重新生成 Falcon 密钥' : '生成 Falcon 密钥' }}
        </el-button>
      </template>
    </el-dialog>

    <!--
      一次性激活凭证。**只显示一次** —— 服务端只存哈希，关掉这个弹窗后
      没有任何办法再取回（只能重签一张新的）。所以文案必须把这件事说清楚，
      不能让人以为"以后还能在哪儿看到"。
    -->
    <el-dialog v-model="activationOpen" title="节点激活凭证" width="560px" :close-on-click-modal="false">
      <el-alert
        type="warning"
        :closable="false"
        show-icon
        title="此凭证只显示这一次"
        description="服务端只保存哈希，关闭后无法再次查看。请立即交给节点操作者；遗失可随时重签（旧凭证会失效）。"
        class="mb16"
      />
      <el-descriptions :column="1" border class="mb16">
        <el-descriptions-item label="节点">{{ activationTarget || '-' }}</el-descriptions-item>
        <el-descriptions-item label="激活凭证">
          <!--
            凭证按**密码**的方式展示：默认打码，点「显示」才现明文。

            ⚠️ 打码防的是"被旁人一眼看走"与顺手截屏，**不防**复制 ——
               这块内容本来就在管理员自己屏幕上，任何"看不到也拿不走"的
               设计在这里只会妨碍正当使用（他总得把凭证交给节点操作者）。
               所以「复制」始终可用，取的是 `activationCode` 而不是屏幕上那串点。
          -->
          <div class="code-row">
            <code class="code-text" :class="{ 'is-masked': !revealActivationCode }">
              {{ revealActivationCode ? activationCode : activationCodeMasked }}
            </code>
            <el-button size="small" plain @click="revealActivationCode = !revealActivationCode">
              {{ revealActivationCode ? '隐藏' : '显示' }}
            </el-button>
            <el-button size="small" type="primary" plain @click="copyActivationCode">复制</el-button>
          </div>
        </el-descriptions-item>
      </el-descriptions>
      <div class="hint-text">
        凭证默认隐藏显示（点「显示」查看原文；「复制」不受影响）。<br />
        节点操作者打开登录页 → 选择「节点」→ 输入节点名称与这张凭证即可完成激活。
        激活后设备凭据留在那台浏览器本机，之后该节点可在此浏览器直接点击登录。
      </div>
      <template #footer>
        <el-button type="primary" @click="activationOpen = false">我已保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
/**
 * 管理端「节点管理」页。
 *
 * 背景（这次改造要解决的问题）：本菜单原先用 `frame/index` 以 iframe 内嵌
 * `/distribute/#/node`。那个子应用有自己的登录态，而 iframe 里没有，
 * 于是页面渲染出来的是它的登录页 —— 管理员明明已经登录了管理端，
 * 点进来却看到"抗量子分发系统 欢迎您！账号密码登录"。
 * 这一页改成原生实现，直接调分发模块的节点接口，复用管理端登录态。
 *
 * 边界：这里管的是**分发系统的业务节点**（可增删改的演示节点），
 * 不是 FISCO 链的记账节点 —— 所以本页与链是否出块无关，链挂了它照样能用。
 *
 * 密钥生成（2026-09-26 起）：新建节点会**自动**生成三套密钥 ——
 * Kyber、国密（SM2 + SSCL）、Falcon。其中 Falcon 最慢（服务端 KGC + 密钥对
 * 约 7.8s 计算，加上写库上链整体约十几到二十秒），因此：
 *   * 创建对话框必须显示 loading 并抑制重复提交；
 *   * 某一套失败不阻断注册（后端只记日志），页面上用就绪状态如实反映，
 *     并提供单节点与批量补生成入口。
 *
 * 字段说明：列表接口（NodeListSerializer）**不返回公钥本身**，只返回
 * `kyber_key_ready` / `falcon_key_ready` / `gm_key_ready` / `sscl_key_ready`
 * 四个布尔值 —— falcon_public_key 实测 7.8MB/节点，列表带上它会超时。
 * 公钥内容只有「密钥」弹窗（/nodes/{id}/keys/）才会取。
 */
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { batchDeleteNodes, deleteNode, generateNodeFalconKey, generateNodeGmKey, getNodeKeys, listNodes, registerNode, reissueActivationCode, updateNode } from '@/api/nodes/nodes'

const NODE_TYPES = [
  { value: 'full', label: '全节点' },
  { value: 'light', label: '轻节点' },
  { value: 'validator', label: '验证节点' },
  { value: 'storage', label: '存储节点' },
  { value: 'compute', label: '计算节点' }
]

const NODE_STATUS = [
  { value: 'registered', label: '已注册' },
  { value: 'kyber_uploaded', label: 'Kyber公钥已上传' },
  { value: 'partial_key_received', label: '部分私钥已接收' },
  { value: 'falcon_generated', label: 'Falcon密钥已生成' },
  { value: 'active', label: '活跃' },
  { value: 'inactive', label: '非活跃' }
]

const rows = ref([])
const selected = ref([])
const loading = ref(false)
const filter = reactive({ keyword: '', nodeType: '', status: '' })

const createOpen = ref(false)
const creating = ref(false)

// 一次性激活凭证弹窗。凭证只在签发响应里出现一次，关掉就再也拿不到
// （库里只存哈希），所以这里不做"稍后再看"之类的入口。
const activationOpen = ref(false)
const activationCode = ref('')
const activationTarget = ref('')
/**
 * 是否明文显示凭证。**每次打开弹窗都重置为 false** ——
 * 上一位管理员点开过眼睛、没关页面就换个节点重签，下一位一进来就是明文，
 * 那与"默认隐藏"这个约定直接相悖。
 */
const revealActivationCode = ref(false)
/**
 * 打码后的占位。
 *
 * 用**定长**，不按凭证长度生成：凭证长度本身不敏感，但长度一致的点阵
 * 读起来更像"一段被隐藏的内容"，也不会因为 43 个点把弹窗撑出换行。
 */
const activationCodeMasked = computed(() => '•'.repeat(24))
const createError = ref('')
const createFormRef = ref()
const createForm = reactive({
  node_id: '',
  name: '',
  ip_address: '',
  port: 9003,
  node_type: 'full',
  organization: '',
  contact_person: '',
  description: ''
})
const createRules = {
  node_id: [{ required: true, message: '节点ID必填', trigger: 'blur' }],
  name: [{ required: true, message: '节点名称必填', trigger: 'blur' }],
  ip_address: [{ required: true, message: 'IP 地址必填', trigger: 'blur' }],
  port: [{ required: true, message: '端口必填', trigger: 'blur' }]
}

const editOpen = ref(false)
const saving = ref(false)
const editError = ref('')
const editForm = reactive({ id: null, node_id: '' })

const keysOpen = ref(false)
const keysLoading = ref(false)
const keysError = ref('')
const keysNode = ref({})
// Falcon 密钥生成是重操作（服务端实测：KGC 部分私钥 5.9s + 密钥对 1.9s，
// 加上写库与上链整体约 20s），必须有 loading 且防重复点击 ——
// 否则用户会以为没反应而反复点，每次都触发一次完整重算。
const falconGenerating = ref(false)
// 国密密钥生成（SM2 + SSCL）：与 Falcon 一样是重操作，需要 loading 与防重复点击
const gmGenerating = ref(false)

/**
 * Falcon 逐节点生成状态。
 *
 * 为什么要它：注册时 Falcon 是**自动生成**的，但要跑十几秒；若某次失败
 * （KGC 异常等），那一行就停在"未生成"上，而页面上没有任何痕迹说明失败过。
 * 所以这里按 node_id 记录 running / failed，让失败**可见**且能重试。
 */
const falconState = reactive({})
const falconError = reactive({})

const falconBatchRunning = ref(false)
const falconBatchDone = ref(0)
const falconBatchTotal = ref(0)

/** 还缺 Falcon 密钥的节点 —— 批量生成的候选集，也是按钮上的计数 */
const missingFalcon = computed(() => rows.value.filter((n) => !n.falcon_key_ready))

function typeLabel(value) {
  return NODE_TYPES.find((t) => t.value === value)?.label || value || '-'
}

function statusLabel(value) {
  return NODE_STATUS.find((s) => s.value === value)?.label || value || '-'
}

function statusTagType(value) {
  if (value === 'active') return 'success'
  if (value === 'inactive') return 'info'
  return 'warning'
}

function formatTime(value) {
  if (!value) return '-'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString('zh-CN', { hour12: false })
}

async function load() {
  loading.value = true
  try {
    // 过滤放在前端做：分发模块的列表接口不支持这些查询参数，
    // 假装服务端过滤会让人以为"查不到 = 没有数据"。
    const all = await listNodes()
    const kw = filter.keyword.trim().toLowerCase()
    rows.value = (all || []).filter((n) => {
      if (filter.nodeType && n.node_type !== filter.nodeType) return false
      if (filter.status && n.status !== filter.status) return false
      if (!kw) return true
      return [n.node_id, n.name, n.ip_address, n.organization]
        .filter(Boolean)
        .some((v) => String(v).toLowerCase().includes(kw))
    })
  } catch (error) {
    ElMessage.error(`加载节点失败：${error.message}`)
    rows.value = []
  } finally {
    loading.value = false
  }
}

function resetFilter() {
  filter.keyword = ''
  filter.nodeType = ''
  filter.status = ''
  load()
}

function openCreate() {
  createError.value = ''
  Object.assign(createForm, {
    node_id: '',
    name: '',
    ip_address: '',
    port: 9003,
    node_type: 'full',
    organization: '',
    contact_person: '',
    description: ''
  })
  createOpen.value = true
}

async function submitCreate() {
  createError.value = ''
  try {
    await createFormRef.value.validate()
  } catch {
    return
  }
  creating.value = true
  try {
    const res = await registerNode({ ...createForm })
    // 服务端对"已存在"也返回成功，靠 is_duplicate 区分 —— 如实提示，不谎报新增成功
    if (res && res.is_duplicate) {
      ElMessage.warning(res.message || '该节点已存在，未新增')
    } else {
      // ⚠️ 这里**不能**说"密钥已生成"：provision_node 只建账号与节点记录，
      //    四套基础密钥要等节点首次登录时在**本机**生成（文档 §2.4 / §3.1）。
      //    文案写错会让人以为密钥已经在服务端了 —— 恰好与"私钥不出本机"相悖。
      ElMessage.success('节点已创建')
      createOpen.value = false
      // 一次性激活凭证：只在这里出现一次，必须立刻展示并提示"仅显示一次"。
      activationCode.value = res?.activation_code || ''
      activationTarget.value = res?.node_id || createForm.node_id || ''
      // 每次打开都回到默认隐藏（见 revealActivationCode 的注释）。
      revealActivationCode.value = false
      if (activationCode.value) {
        activationOpen.value = true
      } else {
        // 签发失败不能静默 —— 节点没有口令，没有凭证就等于进不去。
        ElMessage.warning('节点已创建，但激活凭证签发失败。请用列表里的「重签凭证」补发。')
      }
    }
    await load()
  } catch (error) {
    createError.value = error.message
  } finally {
    creating.value = false
  }
}

/** 为已有节点补发凭证（凭证丢了/过期/换设备） */
async function handleReissue(row) {
  try {
    await ElMessageBox.confirm(
      `为节点 ${row.node_id} 重新签发激活凭证？旧凭证会立即失效。已激活设备的登录不受影响。`,
      '重新签发激活凭证',
      { confirmButtonText: '签 发', cancelButtonText: '取 消', type: 'warning' },
    )
  } catch {
    return
  }
  try {
    const res = await reissueActivationCode(row.id)
    activationCode.value = res?.activation_code || ''
    activationTarget.value = row.node_id
    // 重签同样回到默认隐藏 —— 上一次展开过不代表这一次也该展开。
    revealActivationCode.value = false
    if (activationCode.value) {
      activationOpen.value = true
    } else {
      ElMessage.error('签发失败：服务端未返回凭证')
    }
  } catch (error) {
    ElMessage.error(error?.message || '重新签发失败')
  }
}

async function copyActivationCode() {
  try {
    await navigator.clipboard.writeText(activationCode.value)
    ElMessage.success('凭证已复制')
  } catch {
    // 剪贴板 API 在非 HTTPS / 无权限时会失败。不弹错误打断流程 ——
    // 凭证就在屏幕上，手动选中复制也行。
    ElMessage.warning('浏览器不允许自动复制，请手动选中复制')
  }
}

function openEdit(row) {
  editError.value = ''
  Object.assign(editForm, {
    id: row.id,
    node_id: row.node_id,
    organization: row.organization || '',
    department: row.department || '',
    contact_person: row.contact_person || '',
    phone: row.phone || '',
    email: row.email || '',
    location: row.location || '',
    node_type: row.node_type || 'full',
    tags: row.tags || '',
    description: row.description || ''
  })
  editOpen.value = true
}

async function submitEdit() {
  editError.value = ''
  saving.value = true
  try {
    const { id, node_id, ...payload } = editForm
    await updateNode(id, payload)
    ElMessage.success('已保存')
    editOpen.value = false
    await load()
  } catch (error) {
    editError.value = error.message
  } finally {
    saving.value = false
  }
}

async function openKeys(row) {
  keysNode.value = { ...row }
  keysOpen.value = true
  keysLoading.value = true
  keysError.value = ''
  try {
    const data = await getNodeKeys(row.id)
    if (data && typeof data === 'object' && !Array.isArray(data)) {
      keysNode.value = { ...row, ...data }
    }
  } catch (error) {
    // 列表里已经有公钥字段了，详情接口失败不该让弹窗空着
    keysError.value = `密钥详情接口不可用，以下为列表字段：${error.message}`
  } finally {
    keysLoading.value = false
  }
}

async function handleGenerateGm() {
  const node = keysNode.value
  if (!node?.node_id) {
    return
  }
  const already = Boolean(node.gm_key_ready)
  try {
    await ElMessageBox.confirm(
      already
        ? `节点「${node.name}」已有国密密钥。重新生成会**更换**它们，` +
          '此前用旧公钥封装的密钥池将无法解开。确认继续？'
        : `为节点「${node.name}」生成国密密钥对（SM2 + SSCL）。之后分发时即可选择「国密」体系。`,
      already ? '重新生成国密密钥' : '生成国密密钥',
      { type: already ? 'warning' : 'info', confirmButtonText: '确认生成', cancelButtonText: '取消' }
    )
  } catch {
    return
  }

  gmGenerating.value = true
  keysError.value = ''
  try {
    const res = await generateNodeGmKey(node.node_id)
    ElMessage.success(res?.message || '国密密钥生成成功')
    await openKeys(node)
    await load()
  } catch (error) {
    keysError.value = `国密密钥生成失败：${error.message}`
  } finally {
    gmGenerating.value = false
  }
}

async function handleGenerateFalcon() {
  const node = keysNode.value
  if (!node?.node_id) {
    return
  }
  const already = Boolean(node.falcon_key_ready)
  try {
    await ElMessageBox.confirm(
      already
        ? `节点「${node.name}」已有 Falcon 公钥。重新生成会**更换**它，` +
          '此前用旧公钥封装的密钥池将无法解开。确认继续？'
        : `为节点「${node.name}」生成 Falcon-512 密钥对（V2 陷门方案）。` +
          '生成过程约需十几秒，请勿重复点击。',
      already ? '重新生成 Falcon 密钥' : '生成 Falcon 密钥',
      { type: already ? 'warning' : 'info', confirmButtonText: '确认生成', cancelButtonText: '取消' }
    )
  } catch {
    return
  }

  falconGenerating.value = true
  keysError.value = ''
  falconState[node.node_id] = 'running'
  delete falconError[node.node_id]
  try {
    const res = await generateNodeFalconKey(node.node_id)
    ElMessage.success(res?.message || 'Falcon 密钥生成成功')
    // 清掉失败/进行中的行内状态，否则刚生成成功的那一行还挂着上次的「生成失败」红标
    falconState[node.node_id] = 'done'
    // 重新拉一次详情与列表：公钥很长，界面上的"已就绪"标签要跟着变
    await openKeys(node)
    await load()
  } catch (error) {
    falconState[node.node_id] = 'failed'
    falconError[node.node_id] = error.message
    keysError.value = `Falcon 密钥生成失败：${error.message}`
  } finally {
    falconGenerating.value = false
  }
}

/**
 * 批量给缺 Falcon 的节点补生成。
 *
 * 为什么需要：注册时 Falcon 已自动生成，但 KGC 或网络抖动会让个别节点落空，
 * 而 Falcon 是密钥池 Falcon 路径的硬性前提（缺了会被服务端直接拒绝）。
 * 逐个点开弹窗太慢，这里串行补齐。
 *
 * **串行而非并发**：每次 Falcon 生成在服务端要跑十几秒的重计算，
 * 并发发起只会让它们互相拖慢、并可能撞上 gunicorn 的 timeout=120。
 * 串行还能让每一行的进度如实反映出来。
 *
 * 单个失败不中断整批 —— 失败的行标红并留 tooltip，其余继续。
 */
async function handleBatchGenerateFalcon() {
  const targets = missingFalcon.value.slice()
  if (!targets.length) return

  try {
    await ElMessageBox.confirm(
      `将为 ${targets.length} 个节点依次生成 Falcon-512 密钥，每个约需二十秒，` +
        `合计约 ${Math.max(1, Math.ceil((targets.length * 20) / 60))} 分钟。过程中请勿关闭页面。确认继续？`,
      '批量生成 Falcon 密钥',
      { type: 'info', confirmButtonText: '开始生成', cancelButtonText: '取消' }
    )
  } catch {
    return
  }

  falconBatchRunning.value = true
  falconBatchDone.value = 0
  falconBatchTotal.value = targets.length
  let failed = 0

  for (const node of targets) {
    falconState[node.node_id] = 'running'
    delete falconError[node.node_id]
    try {
      await generateNodeFalconKey(node.node_id)
      falconState[node.node_id] = 'done'
      falconBatchDone.value += 1
    } catch (error) {
      // 如实标记失败并保留原因，不吞掉 —— 否则用户只会看到"点了没反应"
      falconState[node.node_id] = 'failed'
      falconError[node.node_id] = error.message
      failed += 1
    }
  }

  falconBatchRunning.value = false
  await load()

  if (failed) {
    ElMessage.warning(`批量生成结束：成功 ${targets.length - failed} 个，失败 ${failed} 个（悬停「生成失败」标签可看原因）`)
  } else {
    ElMessage.success(`批量生成完成：${targets.length} 个节点 Falcon 密钥均已就绪`)
  }
}

async function handleDelete(row) {
  try {
    await ElMessageBox.confirm(
      `确定删除节点「${row.name}」（${row.node_id}）？该操作不可撤销。`,
      '删除节点',
      { type: 'warning', confirmButtonText: '删 除', cancelButtonText: '取 消' }
    )
  } catch {
    return
  }
  try {
    await deleteNode(row.id)
    ElMessage.success('已删除')
    await load()
  } catch (error) {
    ElMessage.error(`删除失败：${error.message}`)
  }
}

async function handleBatchDelete() {
  const ids = selected.value.map((r) => r.id)
  if (!ids.length) return
  try {
    await ElMessageBox.confirm(`确定删除选中的 ${ids.length} 个节点？该操作不可撤销。`, '批量删除', {
      type: 'warning',
      confirmButtonText: '删 除',
      cancelButtonText: '取 消'
    })
  } catch {
    return
  }
  try {
    await batchDeleteNodes(ids)
    ElMessage.success('已删除')
    selected.value = []
    await load()
  } catch (error) {
    ElMessage.error(`批量删除失败：${error.message}`)
  }
}

onMounted(load)
</script>

<style scoped>
.panel {
  border-radius: 10px;
}

.panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.panel-actions {
  display: flex;
  gap: 8px;
}

.filter-bar {
  margin-bottom: 8px;
}

.table-foot {
  margin-top: 10px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

.dialog-error {
  margin-top: 8px;
  color: var(--el-color-danger);
  font-size: 12px;
  word-break: break-all;
}

.form-hint {
  margin-top: 4px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
  line-height: 1.6;
}

.key-line {
  word-break: break-all;
  font-size: 12px;
}

.muted {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

.fingerprint-hint {
  margin-top: 8px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
  line-height: 1.6;
}

.mb16 {
  margin-bottom: 16px;
}

/* 激活凭证：等宽字体 + 可选中等宽，便于核对与抄写 */
.code-row {
  display: flex;
  align-items: center;
  gap: 12px;
}

.code-text {
  flex: 1;
  min-width: 0;
  padding: 6px 10px;
  border-radius: 6px;
  background: var(--kms-surface-2, #fafafa);
  font-family: 'JetBrains Mono', Consolas, monospace;
  font-size: 13px;
  /* 凭证是长随机串，必须能换行，否则会被对话框裁掉一截 —— 而这一截
     恰好是用户抄不着又看不出来的部分 */
  word-break: break-all;
  user-select: all;
}

/* 打码态：点阵不该被"全选复制"选中 —— 复制到的必须永远是凭证本身，
   而不是一串点。`user-select: none` 让 Ctrl+A / 拖选都跳过它。 */
.code-text.is-masked {
  color: var(--kms-text-secondary, #909399);
  letter-spacing: 2px;
  user-select: none;
}

.hint-text {
  font-size: 12px;
  line-height: 1.7;
  color: var(--kms-text-secondary);
}
</style>
