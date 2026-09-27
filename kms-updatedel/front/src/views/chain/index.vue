<template>
  <div class="app-container">
    <el-card class="panel" shadow="never">
      <template #header>
        <div class="panel-head">
          <div>
            <span>区块链存证</span>
            <span class="sub">密钥生命周期写入 FISCO 链的结果</span>
          </div>
          <el-button size="small" :loading="loading" @click="load">刷 新</el-button>
        </div>
      </template>

<el-row :gutter="12" class="stat-row">
        <el-col :span="6"><div class="stat"><div class="k">已上链</div><div class="v ok">{{ counts.onChain }}</div></div></el-col>
        <el-col :span="6"><div class="stat"><div class="k">待上链</div><div class="v warn">{{ counts.pending }}</div></div></el-col>
        <el-col :span="6"><div class="stat"><div class="k">上链失败</div><div class="v bad">{{ counts.failed }}</div></div></el-col>
        <el-col :span="6"><div class="stat"><div class="k">本页最高块高</div><div class="v">{{ maxBlock ?? '-' }}</div></div></el-col>
      </el-row>

      <el-form :inline="true" class="filter-bar">
        <el-form-item label="关键字">
          <el-input v-model="filter.keyword" clearable placeholder="密钥ID / 用户名 / tx 哈希" style="width: 260px" />
        </el-form-item>
        <el-form-item label="上链状态">
          <el-select v-model="filter.chainStatus" clearable placeholder="全部" style="width: 150px">
            <el-option label="已上链" value="1" />
            <el-option label="待上链" value="0" />
            <el-option label="失败" value="2" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button @click="resetFilter">重 置</el-button>
        </el-form-item>
      </el-form>

      <el-table :data="rows" size="small" v-loading="loading" empty-text="暂无存证记录">
        <el-table-column label="密钥ID" width="90" prop="keyId" />
        <el-table-column label="用户" width="120" prop="userName" />
        <el-table-column label="算法" width="90" prop="encrytName" />
        <el-table-column label="版本" width="70" prop="version" />
        <el-table-column label="上链状态" width="110">
          <template #default="scope">
            <el-tag size="small" :type="chainTag(scope.row.chainStatus)">{{ chainLabel(scope.row.chainStatus) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="区块高度" width="100">
          <template #default="scope">{{ scope.row.blockHeight ?? '-' }}</template>
        </el-table-column>
        <el-table-column label="交易哈希" min-width="220">
          <template #default="scope">
            <code v-if="scope.row.chainHash" class="hash">{{ scope.row.chainHash }}</code>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column label="更新时间" width="180">
          <template #default="scope">{{ scope.row.updTime || '-' }}</template>
        </el-table-column>
      </el-table>

      <div class="table-foot">
        本页 {{ rows.length }} 条 / 共 {{ total }} 条
      </div>
    </el-card>
  </div>
</template>

<script setup>
/**
 * 「区块链存证」——替换原来的 iframe「区块链浏览器」。
 *
 * 原页面是分发模块自带的区块链视图，它的口径是 **Ganache**（默认 provider
 * `http://127.0.0.1:7545`），跟 KMS 实际使用的 FISCO 链不是一条链；
 * 而且它嵌进来同样是它自己的登录页。
 *
 * 这里换成本系统真正需要的视角：**密钥生命周期在 FISCO 链上的存证**。
 * 数据来自 `kms.keymanage` 的 chain_status / block_height / chain_hash
 * （由 Java 后端上链成功后的回写），走管理端自己的登录态。
 */
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { listKeymanage } from '@/api/lifecycle/lifecycle'

const all = ref([])
const rows = ref([])
const total = ref(0)
const loading = ref(false)
const filter = reactive({ keyword: '', chainStatus: '' })

const CHAIN_LABELS = { '1': '已上链', '0': '待上链', '2': '失败' }
const chainLabel = (v) => CHAIN_LABELS[v] ?? (v || '未知')

function chainTag(v) {
  if (v === '1') return 'success'
  if (v === '2') return 'danger'
  return 'warning'
}

const counts = computed(() => ({
  onChain: all.value.filter((r) => r.chainStatus === '1').length,
  pending: all.value.filter((r) => r.chainStatus === '0' || !r.chainStatus).length,
  failed: all.value.filter((r) => r.chainStatus === '2').length
}))

const maxBlock = computed(() => {
  const nums = all.value.map((r) => Number(r.blockHeight)).filter((n) => Number.isFinite(n) && n > 0)
  return nums.length ? Math.max(...nums) : null
})

function applyFilter() {
  const kw = filter.keyword.trim().toLowerCase()
  rows.value = all.value.filter((r) => {
    if (filter.chainStatus && String(r.chainStatus ?? '') !== filter.chainStatus) return false
    if (!kw) return true
    return [r.keyId, r.userName, r.chainHash]
      .filter((v) => v !== null && v !== undefined)
      .some((v) => String(v).toLowerCase().includes(kw))
  })
}

function resetFilter() {
  filter.keyword = ''
  filter.chainStatus = ''
  applyFilter()
}

async function load() {
  loading.value = true
  try {
    // 一次性取较多记录做统计与筛选：这些字段的过滤/聚合在服务端没有对应接口，
    // 假装服务端过滤会让人把"没查到"误读成"没有数据"。
    const res = await listKeymanage({ pageNum: 1, pageSize: 500 })
    all.value = res?.rows || []
    total.value = res?.total ?? all.value.length
    applyFilter()
  } catch (error) {
    ElMessage.error(`加载上链记录失败：${error.message}`)
    all.value = []
    rows.value = []
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.panel { border-radius: 10px; }
.panel-head { display: flex; align-items: center; justify-content: space-between; }
.panel-head .sub { margin-left: 10px; color: var(--el-text-color-secondary); font-size: 12px; }
.sub-note { margin-top: 6px; color: var(--el-text-color-secondary); line-height: 1.7; }
.stat-row { margin-bottom: 12px; }
.stat { background: var(--el-fill-color-light); border-radius: 8px; padding: 10px 14px; }
.stat .k { color: var(--el-text-color-secondary); font-size: 12px; }
.stat .v { font-size: 20px; font-weight: 600; margin-top: 2px; }
.stat .v.ok { color: var(--el-color-success); }
.stat .v.warn { color: var(--el-color-warning); }
.stat .v.bad { color: var(--el-color-danger); }
.filter-bar { margin-bottom: 4px; }
.table-foot { margin-top: 10px; color: var(--el-text-color-secondary); font-size: 12px; }
.hash { font-size: 12px; word-break: break-all; }
.mb16 { margin-bottom: 16px; }
</style>