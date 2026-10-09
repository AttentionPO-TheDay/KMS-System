<template>
  <div class="app-container">
    <el-card class="panel" shadow="never">
      <template #header>
        <div class="panel-head">
          <div>
            <span>密钥池</span>
</div>
          <div class="panel-actions">
            <el-button size="small" :loading="loading" @click="loadAll">刷 新</el-button>
            <!-- KMS-014：过期清理 / 批量删除是池子的**运维动作**，服务端只认管理员
                 （`views.KeyPoolViewSet` 的 admin 档）。节点用户不显示这些按钮 ——
                 让它点了再吃 403，不如一开始就不给预期。（生成并分发对节点用户是
                 正常动作：服务端要求 CAP_DISTRIBUTE 且必须是该节点对的一方。） -->
            <template v-if="isAdmin">
              <el-button size="small" @click="handleCleanup">清理过期</el-button>
              <el-button size="small" type="danger" :disabled="!selected.length" @click="handleBatchDelete">
                批量删除{{ selected.length ? `（${selected.length}）` : '' }}
              </el-button>
            </template>
            <el-button v-if="!IS_DEMO || isAdmin" size="small" type="primary" @click="openDistribute">生成并分发</el-button>
            <el-button v-else size="small" type="primary" @click="goPreallocate">预分配保护包</el-button>
          </div>
        </div>
      </template>

<el-row :gutter="12" class="stat-row">
        <el-col :span="4"><div class="stat"><div class="k">总数</div><div class="v">{{ stats.total ?? '-' }}</div></div></el-col>
        <el-col :span="4"><div class="stat"><div class="k">可用</div><div class="v">{{ stats.unused ?? '-' }}</div></div></el-col>
        <el-col :span="4"><div class="stat"><div class="k">已消费</div><div class="v">{{ stats.used ?? '-' }}</div></div></el-col>
        <el-col :span="4"><div class="stat"><div class="k">已过期</div><div class="v">{{ stats.expired ?? '-' }}</div></div></el-col>
        <el-col :span="4"><div class="stat"><div class="k">已回收</div><div class="v">{{ stats.revoked ?? '-' }}</div></div></el-col>
        <!-- 「预留」恒为 0：RESERVED 是保留值，没有任何写入点（KMS-013 定夺，
             `api_contract.POOL_TRANSITIONS` 里也没有指向它的边）。仍然显示它，
             是为了让"这个状态不存在"这件事在页面上可见，而不是被悄悄省略。 -->
        <el-col :span="4"><div class="stat"><div class="k">预留</div><div class="v">{{ stats.reserved ?? '-' }}</div></div></el-col>
      </el-row>

      <el-form :inline="true" class="filter-bar">
        <el-form-item label="关键字">
          <el-input v-model="filter.keyword" clearable placeholder="批次号 / 节点ID / 密钥哈希" style="width: 260px" />
        </el-form-item>
        <el-form-item label="算法">
          <el-select v-model="filter.algorithm" clearable placeholder="全部" style="width: 170px">
            <el-option v-for="a in algorithmOptions" :key="a.value" :label="a.label" :value="a.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="状态">
          <el-select v-model="filter.status" clearable placeholder="全部" style="width: 150px">
            <el-option v-for="st in statusOptions" :key="st.value" :label="st.label" :value="st.value" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button @click="resetFilter">重 置</el-button>
        </el-form-item>
      </el-form>

      <el-table :data="rows" size="small" v-loading="loading" row-key="id" :empty-text="IS_DEMO && !isAdmin ? '暂无预分配资源，请通过「预分配保护包」创建' : '密钥池还是空的，点右上角「生成并分发」建一批'"
                @selection-change="(v) => (selected = v)">
        <el-table-column type="selection" width="42" />
        <el-table-column label="批次号" min-width="200" prop="pool_id" show-overflow-tooltip />
        <el-table-column label="序号" width="70" prop="key_index" />
        <el-table-column label="归属节点" min-width="150">
          <template #default="scope">{{ scope.row.node1_name || scope.row.node1_id }}</template>
        </el-table-column>
        <el-table-column label="算法" width="120">
          <template #default="scope">{{ scope.row.algorithm_display || scope.row.algorithm }}</template>
        </el-table-column>
        <el-table-column label="状态" width="120">
          <template #default="scope">
            <!-- KMS-013：显示**真实状态**（effective_status）——
                 行还是 READY 但已过期的，消费接口不认它（expires_at 判据），
                 页面若不回退就会说"可用"而消费说"没有"。两者互相矛盾且
                 都不报错，所以以服务端的 effective_status 为准。
                 回退时把原始值也展示出来，避免读页面的人以为库里真的写了 EXPIRED。 -->
            <el-tag size="small" :type="statusTag(scope.row.effective_status || scope.row.status)">
              {{ statusLabel(scope.row.effective_status || scope.row.status) }}
            </el-tag>
            <div v-if="scope.row.effective_status && scope.row.effective_status !== scope.row.status" class="cell-sub">
              库内值：{{ statusLabel(scope.row.status) }}
            </div>
          </template>
        </el-table-column>
        <el-table-column label="接收密钥版本" min-width="180">
          <template #default="scope">
            <!-- 计划 §8.4「接收密钥版本」：这一项是用哪把长期密钥封的。
                 消费前的可用性复核按这两列查登记表（回收后拒消费），
                 显示出来，用户才能把池项与"已回收的那把"对上。 -->
            <template v-if="scope.row.long_term_key_id">
              <code class="ref">{{ shortRef(scope.row.long_term_key_id) }}</code>
              <span class="cell-sub"> v{{ scope.row.long_term_key_version }}</span>
            </template>
            <span v-else class="cell-sub">历史行（无引用）</span>
          </template>
        </el-table-column>
        <el-table-column label="密钥哈希" min-width="150">
          <template #default="scope"><code class="hash">{{ shortHash(scope.row.key_hash) }}</code></template>
        </el-table-column>
        <el-table-column label="消费情况" min-width="150">
          <template #default="scope">
            <template v-if="scope.row.used_at">
              <div>{{ formatTime(scope.row.used_at) }}</div>
              <div class="cell-sub">会话 #{{ scope.row.used_by_session_id ?? '-' }}</div>
            </template>
            <span v-else class="cell-sub">未消费</span>
          </template>
        </el-table-column>
        <el-table-column label="过期时间" width="170">
          <template #default="scope">{{ formatTime(scope.row.expires_at) }}</template>
        </el-table-column>
        <el-table-column label="创建时间" width="170">
          <template #default="scope">{{ formatTime(scope.row.create_datetime) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="90" fixed="right">
          <template #default="scope">
            <!-- KMS-014：单条删除同属运维动作（服务端 admin 档），节点用户不显示。 -->
            <el-button v-if="isAdmin" link type="danger" size="small" @click="handleDelete(scope.row)">删除</el-button>
            <span v-else class="cell-sub">—</span>
          </template>
        </el-table-column>
      </el-table>

      <div class="table-foot">
        共 {{ rows.length }} 条{{ rows.length !== allRows.length ? `（已按筛选显示，总 ${allRows.length} 条）` : '' }}
      </div>
    </el-card>

    <!-- 生成并分发 -->
    <el-dialog v-model="distOpen" title="生成并分发密钥池" width="560px">
      <el-form :model="distForm" label-width="110px">
        <!--
          封装算法（2026-09-26 新增）。
          此前这个对话框只调 `/key-pool/distribute/`，而那条路在服务端**写死 Kyber**，
          于是密钥池的算法列永远只有 Kyber KEM —— 抗量子只剩一半，
          想看 Falcon 得直接调接口，界面上无路可走。
          两条路的语义不同，所以选项标签里写清楚"谁封装、池子归谁"：
            * Kyber KEM     → /key-pool/distribute/：用**发送方**公钥封装，单向池
            * Falcon 格密码 → /key-pool/generate/  ：用**接收方**公钥封装，节点间池
        -->
        <!-- 阶段 5（文档 §6.2）：**移除 Falcon 选项**。
             理由是职责错配 —— SM4 的机密性必须由加密/封装算法提供，
             而 Falcon 是**签名**算法，签名不保密。原先这里能选它，
             意味着允许用签名算法"封装"会话密钥，概念上用错了。

             正确分工：SM2 / SSCL / Kyber 保护 SM4；Falcon 用于签名验签。

             保留 Kyber 一条：它是当前唯一被支持的抗量子封装算法。
             历史 falcon_lattice 池项仍可读（列表按记录自身的 algorithm 渲染），
             只是不再能新建。 -->
        <el-form-item label="封装算法">
          <el-select v-model="distForm.algorithm" style="width: 100%">
            <el-option label="Kyber KEM（抗量子封装）" value="kyber_kem" />
          </el-select>
        </el-form-item>
        <el-form-item label="发送方节点">
          <el-select v-model="distForm.sender_node_id" filterable placeholder="选择发送方节点" style="width: 100%">
            <el-option v-for="n in nodes" :key="n.node_id" :label="`${n.name}（${n.node_id}）`" :value="n.node_id" />
          </el-select>
          <div class="form-hint">
            用该节点的 Kyber 公钥封装，只有它能解开。
          </div>
        </el-form-item>
        <el-form-item label="接收方节点">
          <el-select v-model="distForm.receiver_node_id" filterable placeholder="选择接收方节点" style="width: 100%">
            <el-option v-for="n in nodes" :key="n.node_id" :label="`${n.name}（${n.node_id}）`" :value="n.node_id" />
          </el-select>
        </el-form-item>
        <el-form-item label="数量">
          <el-input-number v-model="distForm.count" :min="1" :max="500" controls-position="right" />
        </el-form-item>
        <el-form-item label="有效期(小时)">
          <el-input-number v-model="distForm.expiry_hours" :min="1" :max="720" controls-position="right" />
        </el-form-item>
      </el-form>
      <div v-if="distError" class="dialog-error">{{ distError }}</div>
      <div v-if="distResult" class="dialog-ok">{{ distResult }}</div>
      <template #footer>
        <el-button @click="distOpen = false">关 闭</el-button>
        <el-button type="primary" :loading="distributing" @click="submitDistribute">生成并分发</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
/**
 * 「密钥池」——从分发模块复用过来的**分发功能**页（原生实现）。
 *
 * 为什么不 iframe 嵌它原来的页面：那个子应用有自己的登录态，嵌进来只会显示它的登录页；
 * 而它的接口本来就是开放的、可被管理端直接调用。所以这里只复用**功能**，
 * 页面用管理端自己的组件与登录态重写。
 *
 * 服务端：`/pqkds-api/key-pool/*`（预分配密钥住在 falcon_kds）。
 */
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  batchDeleteKeyPool,
  cleanupKeyPool,
  deleteKeyPoolItem,
  distributeKeyPool,
  getKeyPoolStats,
  listKeyPool
} from '@/api/pqkds/distribution'
import { listNodes } from '@/api/nodes/nodes'
import { listNodeDirectory } from '@/api/pqkds/node-self'
import { IS_DEMO } from '@/utils/entry-mode'
import { findTopLevelPagePath } from '@/utils/subsystems'
import usePermissionStore from '@/store/modules/permission'
import { isAdminPrincipal } from '@/utils/principal'
import useUserStore from '@/store/modules/user'

const allRows = ref([])
const rows = ref([])
const selected = ref([])
const nodes = ref([])
const stats = ref({})
const loading = ref(false)
const filter = reactive({ keyword: '', algorithm: '', status: '' })

const distOpen = ref(false)
const distributing = ref(false)
const distError = ref('')
const distResult = ref('')
const distForm = reactive({ algorithm: 'kyber_kem', sender_node_id: '', receiver_node_id: '', count: 10, expiry_hours: 24 })

/**
 * KMS-014：当前主体是不是管理员。
 * 池页面由**两类人**看：管理员（监管视图，`poolgov`）与节点用户（`selfpool`）。
 * 服务端把过期清理/删除定为管理员动作（`views.KeyPoolViewSet` 的 admin 档），
 * 所以按钮可见性必须与那一档一致 —— 判据与 `permission.js` 的视图分流
 * 用**同一个** `resolvePrincipalType`，不在这里另写一套。
 */
const userStore = useUserStore()
const router = useRouter()
const isAdmin = computed(() => isAdminPrincipal({
  principalType: userStore.principalType,
  roleLevel: userStore.roleLevel
}))

const algorithmOptions = computed(() => {
  const seen = new Map()
  allRows.value.forEach((r) => {
    if (r.algorithm) seen.set(r.algorithm, r.algorithm_display || r.algorithm)
  })
  return [...seen].map(([value, label]) => ({ value, label }))
})

const statusOptions = computed(() => {
  // 选项取自**effective_status**（与表格显示同源）：只按库内 status 生成，
  // 会出现"筛选项里有『可被会话取用』、选完却一行都没有"（那些行其实已过期）。
  const seen = new Map()
  allRows.value.forEach((r) => {
    const st = r.effective_status || r.status
    if (st) seen.set(st, statusLabel(st))
  })
  return [...seen].map(([value, label]) => ({ value, label }))
})

function statusTag(status) {
  if (status === 'READY' || status === 'unused') return 'success'
  if (status === 'CONSUMED' || status === 'used' || status === 'distributed') return 'info'
  if (status === 'EXPIRED' || status === 'expired' || status === 'REVOKED') return 'danger'
  return 'warning'
}

/**
 * 状态文案表（KMS-013）。
 * ⚠️ 显示的以 `effective_status`（服务端归一 + 过期回退）为准；
 *    库内原值（status）只在两者不同时作为小字附注。别反过来 ——
 *    页面说"可用"、消费说"没有"的那种矛盾就是这么来的。
 */
const STATUS_LABELS = {
  READY: '可被会话取用',
  RESERVED: '预留（保留值）',
  CONSUMED: '已消费',
  EXPIRED: '已过期',
  REVOKED: '已回收',
  unused: '未使用（历史）',
  used: '已使用（历史）',
  expired: '已过期（历史）',
  distributed: '已下发（历史）'
}

function statusLabel(status) {
  return STATUS_LABELS[status] || status || '-'
}

function shortHash(hash) {
  if (!hash) return '-'
  return hash.length > 20 ? `${hash.slice(0, 10)}…${hash.slice(-6)}` : hash
}

/** 长期密钥 key_id 可能是 `kms-20260926-ab12cd34-XXXX` 这类长串，只留两头。 */
function shortRef(ref) {
  if (!ref) return '-'
  return ref.length > 24 ? `${ref.slice(0, 14)}…${ref.slice(-6)}` : ref
}

function formatTime(value) {
  if (!value) return '-'
  const d = new Date(String(value).replace(' ', 'T'))
  return Number.isNaN(d.getTime()) ? String(value) : d.toLocaleString('zh-CN', { hour12: false })
}

function applyFilter() {
  const kw = filter.keyword.trim().toLowerCase()
  rows.value = allRows.value.filter((r) => {
    if (filter.algorithm && r.algorithm !== filter.algorithm) return false
    // 按 effective_status 筛（与表格显示的同一个值）—— 见 statusOptions 的说明。
    if (filter.status && (r.effective_status || r.status) !== filter.status) return false
    if (!kw) return true
    return [r.pool_id, r.node1_id, r.node1_name, r.key_hash, r.long_term_key_id]
      .filter(Boolean)
      .some((v) => String(v).toLowerCase().includes(kw))
  })
}

function resetFilter() {
  filter.keyword = ''
  filter.algorithm = ''
  filter.status = ''
  applyFilter()
}

async function loadAll() {
  loading.value = true
  try {
    const [list, poolStats, nodeList] = await Promise.all([
      listKeyPool(),
      getKeyPoolStats().catch(() => ({})),
      (IS_DEMO && !isAdmin.value
        ? listNodeDirectory().then(data => (data.nodes || []).map(node => ({ node_id: node.nodeCode, name: node.name })))
        : listNodes()).catch(() => [])
    ])
    allRows.value = list || []
    stats.value = poolStats || {}
    nodes.value = nodeList || []
    applyFilter()
  } catch (error) {
    ElMessage.error(`加载密钥池失败：${error.message}`)
    allRows.value = []
    rows.value = []
  } finally {
    loading.value = false
  }
}

function goPreallocate() {
  // 演示节点走已经上线的本机 SM4/Kyber/Falcon 保护包流程，不调用旧服务端生成路径。
  // 页面路径取同一棵服务端菜单（9471），不另维护一份 Demo 菜单或路由。
  const path = findTopLevelPagePath(usePermissionStore().sidebarRouters, 9471)
  if (path) router.push(path)
  else ElMessage.error('当前主体未获得预分配页面入口')
}

function openDistribute() {
  distError.value = ''
  distResult.value = ''
  distOpen.value = true
}

async function submitDistribute() {
  distError.value = ''
  distResult.value = ''
  if (!distForm.sender_node_id || !distForm.receiver_node_id) {
    distError.value = '请先选择发送方与接收方节点'
    return
  }
  if (distForm.sender_node_id === distForm.receiver_node_id) {
    distError.value = '发送方与接收方不能是同一个节点'
    return
  }
  distributing.value = true
  try {
    // 阶段 5（文档 §6.2）后只剩 Kyber 一条路：单向池，封给**发送方**的 Kyber 公钥。
    //
    // 原此处按算法分流到 generateNodePool（Falcon 节点间池）。UI 移除 Falcon 选项后
    // 该分支恒不走，属死代码，已删除 —— 留着会让人以为系统仍支持 Falcon 封装。
    // 历史 falcon_lattice 池项仍可读（列表与筛选项按记录自身的 algorithm 渲染）。
    const res = await distributeKeyPool({ ...distForm })
    // 服务端实际返回 {success, pool_id, sender_node_id, receiver_node_id, generated, expires_at}。
    // 先按真实字段名读，再留几个兜底 —— 之前只猜了 count/keys/total，
    // 结果把一整串 JSON 当提示显示给用户了（能跑但难看，也算一种"没验证到位"）。
    //
    // KMS-013（计划 §7 阶段 5「不能用'请求成功'冒充'全部完成'」）：
    // `generated < count` 时**必须**如实说明缺了多少 —— 服务层对单条失败
    // 只记日志并 `continue`（例如某条的 KEM 封装失败），响应仍是 success。
    // 只报"已生成并分发 N 条"会把失败的 M 条整个吞掉。
    const count = res?.generated ?? res?.count ?? res?.keys?.length ?? res?.total ?? null
    const requested = distForm.count
    if (count !== null && Number(count) < Number(requested)) {
      distResult.value = `部分完成：请求 ${requested} 条，实际生成并分发 ${Number(count)} 条，`
        + `另有 ${Number(requested) - Number(count)} 条在服务端生成时失败（批次 ${res?.pool_id || '-'}）。`
        + `服务端日志里逐条记有失败原因；池列表只显示成功落库的条目，不会把失败算成完成。`
      ElMessage.warning('部分完成：有密钥生成失败，已如实列出数量')
    } else if (count) {
      distResult.value = `已生成并分发 ${count} 条（Kyber KEM，批次 ${res?.pool_id || '-'}）`
      ElMessage.success('生成并分发完成')
    } else {
      distResult.value = `服务端已受理：${JSON.stringify(res)?.slice(0, 160)}`
      ElMessage.success('生成并分发完成')
    }
    await loadAll()
  } catch (error) {
    distError.value = error.message
  } finally {
    distributing.value = false
  }
}

async function handleCleanup() {
  try {
    await ElMessageBox.confirm('清理所有已过期的预分配密钥？该操作不可撤销。', '清理过期', {
      type: 'warning', confirmButtonText: '清 理', cancelButtonText: '取 消'
    })
  } catch {
    return
  }
  try {
    const res = await cleanupKeyPool()
    const n = res?.deleted ?? res?.count ?? ''
    ElMessage.success(`已清理${n === '' ? '' : ` ${n} 条`}`)
    await loadAll()
  } catch (error) {
    ElMessage.error(`清理失败：${error.message}`)
  }
}

async function handleDelete(row) {
  try {
    await ElMessageBox.confirm(`删除批次 ${row.pool_id} 的第 ${row.key_index} 条？`, '删除', {
      type: 'warning', confirmButtonText: '删 除', cancelButtonText: '取 消'
    })
  } catch {
    return
  }
  try {
    await deleteKeyPoolItem(row.id)
    ElMessage.success('已删除')
    await loadAll()
  } catch (error) {
    ElMessage.error(`删除失败：${error.message}`)
  }
}

async function handleBatchDelete() {
  const ids = selected.value.map((r) => r.id)
  if (!ids.length) return
  try {
    await ElMessageBox.confirm(`删除选中的 ${ids.length} 条？该操作不可撤销。`, '批量删除', {
      type: 'warning', confirmButtonText: '删 除', cancelButtonText: '取 消'
    })
  } catch {
    return
  }
  try {
    await batchDeleteKeyPool(ids)
    ElMessage.success('已删除')
    selected.value = []
    await loadAll()
  } catch (error) {
    ElMessage.error(`批量删除失败：${error.message}`)
  }
}

onMounted(loadAll)
</script>

<style scoped>
.panel { border-radius: 10px; }
.panel-head { display: flex; align-items: center; justify-content: space-between; }
.panel-head .sub { margin-left: 10px; color: var(--el-text-color-secondary); font-size: 12px; }
.panel-actions { display: flex; gap: 8px; }
.stat-row { margin-bottom: 12px; }
.stat { background: var(--el-fill-color-light); border-radius: 8px; padding: 10px 14px; }
.stat .k { color: var(--el-text-color-secondary); font-size: 12px; }
.stat .v { font-size: 20px; font-weight: 600; margin-top: 2px; }
.filter-bar { margin-bottom: 4px; }
.table-foot { margin-top: 10px; color: var(--el-text-color-secondary); font-size: 12px; }
.hash { font-size: 12px; }
.ref { font-size: 12px; }
.cell-sub { color: var(--el-text-color-secondary); font-size: 12px; }
.form-hint { margin-top: 4px; color: var(--el-text-color-secondary); font-size: 12px; }
.dialog-error { margin-top: 8px; color: var(--el-color-danger); font-size: 12px; word-break: break-all; }
.dialog-ok { margin-top: 8px; color: var(--el-color-success); font-size: 12px; }
.mb16 { margin-bottom: 16px; }
</style>