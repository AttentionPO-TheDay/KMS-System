<template>
  <div class="app-container user-keys">
    <div class="avatar-container">
      <div class="left-title">密钥生成系统</div>
      <el-dropdown @command="handleCommand" class="right-menu-item hover-effect" trigger="click">
        <div class="avatar-wrapper">
          <img :src="userStore.avatar" class="user-avatar" />
          <el-icon><caret-bottom /></el-icon>
        </div>
        <template #dropdown>
          <el-dropdown-menu>
            <router-link to="/user/profile">
              <el-dropdown-item>个人中心</el-dropdown-item>
            </router-link>
            <el-dropdown-item divided command="logout">
              <span>退出登录</span>
            </el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
    </div>

    <el-card shadow="never" class="user-keys__card">
      <template #header>
        <div class="user-keys__header">
          <h2>我的密钥</h2>
          <div class="user-keys__header-side">
            <el-tag v-if="node.nodeId" type="info" size="small">{{ node.nodeId }}</el-tag>
            <el-button size="small" :loading="loading" @click="load">刷新</el-button>
          </div>
        </div>
      </template>

      <!-- 账号没关联节点：管理员账号，或数据异常。与「密钥更新」「密钥回收」同一判据。 -->
      <el-alert
        v-if="!loading && !mapped"
        type="warning"
        :closable="false"
        show-icon
        title="当前账号未关联任何节点"
        description="密钥是节点自己产生并保管的。请用节点账号登录，或在「节点管理」里创建节点后再由节点自行登录。"
      />

      <template v-else>
        <p class="user-keys__lead">
          这里列的是<strong>本节点</strong>在平台上登记的长期密钥，含已被取代与已回收的历史版本。
          私钥<strong>只保存在生成它的那台设备</strong>的浏览器加密存储里，平台从来不收 ——
          所以本页只有公开信息，不显示也不导出任何私钥。
        </p>
        <p class="user-keys__lead">
          换新版本请走<strong>「密钥更新」</strong>，整把作废请走<strong>「密钥回收」</strong>；
          本页是只读的，不提供任何写操作。
        </p>

        <!-- 后端一次最多回 200 行且没有分页参数，到顶必须说出来。 -->
        <el-alert
          v-if="possiblyTruncated"
          class="user-keys__notice"
          type="info"
          :closable="false"
          show-icon
          :title="`只显示了最近 ${SERVER_ROW_LIMIT} 条`"
          description="本节点登记过的密钥行数达到接口上限，更早的版本没有列出来。需要完整历史请直接查服务端 dvadmin_pqkds_node_long_term_keys 表。"
        />

        <el-form inline class="user-keys__filter" @submit.prevent>
          <el-form-item label="算法">
            <el-select v-model="algoFilter" clearable placeholder="全部" class="user-keys__filter-select">
              <el-option v-for="a in algorithmOptions" :key="a" :label="a" :value="a" />
            </el-select>
          </el-form-item>
          <el-form-item label="状态">
            <el-select v-model="statusFilter" clearable placeholder="全部" class="user-keys__filter-select">
              <el-option v-for="o in statusOptions" :key="o.value" :label="o.label" :value="o.value" />
            </el-select>
          </el-form-item>
          <el-form-item label="keyId">
            <el-input v-model="keyword" clearable placeholder="包含匹配" style="width: 200px" />
          </el-form-item>
          <el-form-item>
            <el-button @click="resetFilters">重置</el-button>
          </el-form-item>
        </el-form>

        <el-table v-loading="loading" :data="filtered" size="small" border>
          <el-table-column label="算法" width="92" prop="algorithm" />
          <el-table-column label="keyId" min-width="200" show-overflow-tooltip>
            <template #default="{ row }">
              <span class="mono">{{ row.keyId || '（未记录）' }}</span>
            </template>
          </el-table-column>
          <el-table-column label="版本" width="70">
            <template #default="{ row }">v{{ row.keyVersion }}</template>
          </el-table-column>
          <el-table-column label="状态" width="116">
            <template #default="{ row }">
              <el-tag :type="statusTagType(row.status)" size="small">{{ row.statusLabel }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="DID 绑定" min-width="180">
            <template #default="{ row }">
              <el-tag v-if="row.chainWriteState === 'PAUSED'" type="info" size="small">真实上链已暂停</el-tag>
              <template v-if="row.chainBinding">
                <el-tag :type="row.chainBinding.status === 'CONFIRMED' ? 'success' : 'warning'" size="small">
                  {{ row.chainBinding.status === 'CONFIRMED' ? '交易及回读已验证' : (row.chainBinding.status || '未确认') }}
                </el-tag>
                <div class="mono" style="overflow-wrap: anywhere">{{ row.chainBinding.did || '尚无 DID' }}</div>
              </template>
              <span v-else>{{ row.chainWriteState === 'PAUSED' ? '本地公钥已保留；不提交新交易' : '旧链模式（非 DID 确认）' }}</span>
            </template>
          </el-table-column>
          <el-table-column label="可用性" width="132">
            <template #default="{ row }">{{ usableText(row) }}</template>
          </el-table-column>
          <el-table-column label="安全级别" width="88">
            <template #default="{ row }">{{ row.securityLevel || '—' }}</template>
          </el-table-column>
          <el-table-column label="生效时间" width="150">
            <template #default="{ row }">{{ formatTime(row.effectiveAt || row.createdAt) }}</template>
          </el-table-column>
          <el-table-column label="更新时间" width="150">
            <template #default="{ row }">{{ formatTime(row.updatedAt) }}</template>
          </el-table-column>
          <el-table-column label="回收时间" width="150">
            <template #default="{ row }">{{ formatTime(row.revokedAt) }}</template>
          </el-table-column>
          <el-table-column label="回收原因" min-width="140" show-overflow-tooltip>
            <template #default="{ row }">{{ row.revokedReason || '—' }}</template>
          </el-table-column>
        </el-table>
        <p v-if="!loading && !filtered.length" class="user-keys__empty">
          {{ rows.length ? '没有符合筛选条件的密钥。' : '这个节点还没有登记过任何长期密钥 —— 先到「密钥生成」页生成第一把。' }}
        </p>
      </template>
    </el-card>
  </div>
</template>

<script setup name="UserKeys">
/**
 * 我的密钥（菜单 9023，节点端 `/userKeys/index`）。
 *
 * 改造前，这一页打在 updatedel 旧 `keymanage` 模型上，而且**带写操作**：
 * 列表读 `GET /generate/key/list`、「更新」按钮调 `PUT /generate/keymanage`，
 * 还会在本机算一遍 SM2/SSCL 的最终私钥并弹「本地最终密钥结果」对话框。
 *
 * 两个问题：
 * 1. 它操作的根本不是节点真正在用的长期密钥（`NodeLongTermKey`）——
 *    点完"更新成功"，节点手上的密钥没变（与 KMS-006 之前更新页同源）；
 * 2. 展示与让用户复制"最终私钥"与 §5.2「私钥在节点本地产生并保存、
 *    绝不下服务端」是两条口径，而且那段材料是从 keymanage 行现算的，
 *    与本机密钥库里那把真正用于解信封的私钥**不是同一把** ——
 *    复制走的那串看着像私钥、实际用不了，且不会报错。
 *
 * 现在这一页是**只读**的资产视图：
 * - 列表读 `GET /node-self/keys/`（本节点全部长期密钥行，含被取代/已回收的历史版本）；
 * - 「更新」动作整段删除 —— 它属于「密钥更新」页（keyupdate，KMS-006 已重写）；
 * - 「本地最终密钥结果」对话框连同全部密码学代码删除 —— 材料来源已不存在，
 *   留着只会继续产出"看着像私钥、实际对不上"的复制品。
 *
 * 展示口径：`statusLabel` / `allowsNewWork` / `allowsUnwrap` 全部来自服务端，
 * 前端不写第二份中文状态表与可用性判断（见 keydelete 页头注释：两份必然漂移）。
 */
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import useUserStore from '@/store/modules/user'
import { IS_DEMO } from '@/utils/entry-mode'
import { getSelfNode, listSelfNodeKeys } from '@/api/pqkds/node-self'

const { proxy } = getCurrentInstance()
const userStore = useUserStore()

/** 后端 `_long_term_keys_payload(node, limit=200)` 的条数上限，**与后端同改**。 */
const SERVER_ROW_LIMIT = 200

/** 状态 → 标签颜色。**只有颜色**是前端的，文案一律用服务端 `statusLabel`。 */
const STATUS_TAG_TYPE = { ACTIVE: 'success', PENDING: 'warning', REVOKED: 'danger' }

const loading = ref(true)
const mapped = ref(false)
const node = ref({})
const rows = ref([])

const algoFilter = ref('')
const statusFilter = ref('')
const keyword = ref('')

function handleCommand(command) {
  if (command === 'logout') {
    proxy.$confirm('确定注销并退出系统吗？', '提示', { confirmButtonText: '确定', cancelButtonText: '取消', type: 'warning' }).then(() => {
      userStore.logOut().then(() => { if (!IS_DEMO) location.href = `${import.meta.env.BASE_URL}index` })
    }).catch(() => {})
  }
}

async function load() {
  loading.value = true
  try {
    const data = await getSelfNode()
    mapped.value = Boolean(data?.mapped)
    node.value = data?.node || {}
    if (!mapped.value) {
      rows.value = []
      return
    }
    try {
      const payload = await listSelfNodeKeys()
      rows.value = payload?.keys || []
    } catch (error) {
      // 读不到 ≠ 没有密钥。后者会让用户以为密钥丢了（或去重新生成），
      // 而平台记录可能好好的。列空表 + 明确报错，不静默。
      rows.value = []
      ElMessage.error(`读取平台登记记录失败：${error.message}`)
    }
  } catch (error) {
    ElMessage.error(`读取节点信息失败：${error.message}`)
  } finally {
    loading.value = false
  }
}

const possiblyTruncated = computed(() => rows.value.length >= SERVER_ROW_LIMIT)

/** 选项从已载入的数据派生 —— 写死清单会在服务端新增算法/状态时静默漏掉。 */
const algorithmOptions = computed(() => [...new Set(rows.value.map((r) => r.algorithm).filter(Boolean))].sort())

const statusOptions = computed(() => {
  const seen = new Map()
  for (const row of rows.value) {
    if (row.status) seen.set(row.status, row.statusLabel || row.status)
  }
  return [...seen].map(([value, label]) => ({ value, label }))
})

const filtered = computed(() =>
  rows.value.filter((row) => {
    if (algoFilter.value && row.algorithm !== algoFilter.value) return false
    if (statusFilter.value && row.status !== statusFilter.value) return false
    if (keyword.value) {
      const wanted = keyword.value.trim().toLowerCase()
      if (wanted && !String(row.keyId || '').toLowerCase().includes(wanted)) return false
    }
    return true
  })
)

function resetFilters() {
  algoFilter.value = ''
  statusFilter.value = ''
  keyword.value = ''
}

function statusTagType(status) {
  return STATUS_TAG_TYPE[status] || 'info'
}

/** 「这把还能干什么」由服务端下发的两个布尔量拼出，前端不另写状态表。 */
function usableText(row) {
  if (row.allowsNewWork) return '可用于新会话'
  if (row.allowsUnwrap) return '仅可解开旧信封'
  return '不可用'
}

function formatTime(value) {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return String(value)
  const pad = (n) => String(n).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`
}

onMounted(load)
</script>

<style scoped>
::v-deep .el-dropdown { position: absolute; right: 0 }
.avatar-container { position: relative; display: flex; align-items: center }
.avatar-container .left-title { font-size: 24px; font-weight: 600 }
.avatar-container .avatar-wrapper { margin-top: 5px; position: relative }
.avatar-container .avatar-wrapper .user-avatar { cursor: pointer; width: 40px; height: 40px; border-radius: 10px }
.avatar-container .avatar-wrapper i { cursor: pointer; position: absolute; right: -20px; top: 25px; font-size: 12px }

.user-keys__card { max-width: 1320px; margin: 24px auto; }
.user-keys__header { display: flex; align-items: center; justify-content: space-between; }
.user-keys__header h2 { margin: 0; font-size: 18px; }
.user-keys__header-side { display: flex; align-items: center; gap: 8px; }
.user-keys__lead { margin: 0 0 8px; color: var(--kms-text-secondary, #606266); line-height: 1.7; }
.user-keys__notice { margin: 12px 0; }
.user-keys__filter { margin: 4px 0; }
.user-keys__filter-select { width: 160px; }
.user-keys__empty { margin: 12px 0 0; color: var(--kms-text-secondary, #909399); font-size: 13px; }
.mono { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
</style>
