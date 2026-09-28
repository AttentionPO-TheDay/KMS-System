<template>
  <div class="app-container">
    <el-form :model="queryParams" ref="queryRef" :inline="true" v-show="showSearch" label-width="68px">
      <el-form-item label="用户ID" prop="userId">
        <el-input v-model="queryParams.userId" placeholder="请输入用户ID" clearable @keyup.enter="handleQuery" />
      </el-form-item>
      <el-form-item label="用户名" prop="userName">
        <el-input v-model="queryParams.userName" placeholder="请输入用户名" clearable @keyup.enter="handleQuery" />
      </el-form-item>
      <el-form-item label="算法名称" prop="encrytName">
        <el-input v-model="queryParams.encrytName" placeholder="请输入算法名称" clearable @keyup.enter="handleQuery" />
      </el-form-item>
      <el-form-item label="密钥名称" prop="keyName">
        <el-input v-model="queryParams.keyName" placeholder="请输入密钥名称" clearable @keyup.enter="handleQuery" />
      </el-form-item>
      <el-form-item>
        <el-button type="primary" icon="Search" @click="handleQuery">搜索</el-button>
        <el-button icon="Refresh" @click="resetQuery">重置</el-button>
      </el-form-item>
    </el-form>

    <el-row :gutter="10" class="mb8">
      <el-col :span="1.5">
        <el-button
          type="success"
          plain
          icon="Refresh"
          :disabled="single"
           @click="openUpdateDialog()"
           v-hasPermi="['lifecycle:keymanage:edit']"
           style="padding: 6px 12px; margin-top: 15px"
        >密钥更新</el-button>
      </el-col>
      <el-col :span="1.5">
        <el-button
          type="primary"
          plain
          icon="Refresh"
          :disabled="multiple"
          @click="handleBatchUpdate"
          v-hasPermi="['lifecycle:keymanage:edit']"
          style="padding: 6px 12px; margin-top: 15px"
        >批量更新</el-button>
      </el-col>
      <right-toolbar v-model:showSearch="showSearch" @queryTable="getList" />
    </el-row>

    <el-table v-loading="loading" :data="keymanageList" @selection-change="handleSelectionChange">
      <el-table-column type="selection" width="55" align="center" />
      <el-table-column label="密钥ID" align="center" prop="keyId" width="90" />
      <el-table-column label="用户ID" align="center" prop="userId" width="90" />
      <el-table-column label="用户名" align="center" prop="userName" width="120" />
      <el-table-column label="算法类型" align="center" prop="encrytType" min-width="130" />
      <el-table-column label="算法名称" align="center" prop="encrytName" width="120" />
      <el-table-column label="密钥名称" align="center" prop="keyName" min-width="140" />
      <el-table-column label="用途" align="center" prop="keyUse" min-width="140" />
      <el-table-column label="版本" align="center" prop="version" width="80" />
      <el-table-column label="自动更新" align="center" width="100">
        <template #default="scope">
          <el-tag :type="isAutoUpdateEnabled(scope.row.autoUpdate) ? 'success' : 'info'">
            {{ isAutoUpdateEnabled(scope.row.autoUpdate) ? '启用' : '关闭' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="状态" align="center" width="100">
        <template #default="scope">
          <el-tag :type="statusTagType(scope.row.status)">{{ statusText(scope.row.status) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="上链状态" align="center" width="100">
        <template #default="scope">
          <el-tag :type="chainStatusType(scope.row.chainStatus)">{{ chainStatusText(scope.row.chainStatus) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="更新时间" align="center" prop="updTime" width="170" />
      <el-table-column label="操作" align="center" width="120">
        <template #default="scope">
          <el-button
            link
            type="primary"
            icon="Refresh"
            :disabled="isRevoked(scope.row.status)"
            @click="openUpdateDialog(scope.row)"
            v-hasPermi="['lifecycle:keymanage:edit']"
          >更新</el-button>
          <el-button
            link
            type="warning"
            icon="View"
            @click="openAnalysisDialog(scope.row)"
          >安全分析</el-button>
        </template>
      </el-table-column>
    </el-table>

    <pagination
      v-show="total > 0"
      :total="total"
      v-model:page="queryParams.pageNum"
      v-model:limit="queryParams.pageSize"
      @pagination="getList"
    />

    <el-dialog :title="dialogTitle" v-model="open" width="560px" append-to-body>
      <el-form ref="keymanageRef" :model="form" :rules="rules" label-width="96px">
        <el-form-item label="密钥ID">
          <el-input :model-value="form.keyId" disabled />
        </el-form-item>
        <el-form-item label="用户名">
          <el-input :model-value="form.userName" disabled />
        </el-form-item>
        <el-form-item label="算法类型">
          <el-input :model-value="form.encrytType" disabled />
        </el-form-item>
        <el-form-item label="算法名称">
          <el-input :model-value="form.encrytName" disabled />
        </el-form-item>
        <el-form-item label="密钥名称" prop="keyName">
          <el-input v-model="form.keyName" placeholder="可选，不填则沿用当前值" />
        </el-form-item>
        <el-form-item label="密钥用途" prop="keyUse">
          <el-input v-model="form.keyUse" placeholder="可选，不填则沿用当前值" />
        </el-form-item>
        <el-form-item label="所属域" prop="keyDomain" v-if="isSsclKey(form)">
          <el-input v-model="form.keyDomain" placeholder="SSCL 更新时可调整所属域" />
        </el-form-item>
        <!--
          这里原来有一个「自动更新」开关，已移除（2026-09-24）：
          1. 菜单里已有独立的「密钥自动更新」页，这是重复入口；
          2. 它会让更新请求带上 autoUpdate（哪怕值与库里相同），
             后端据此判定为"要改自动更新"，于是只想改密钥名称的更新
             被拒，报错却是"当前用户没有自动更新操作权限"（用户截图）。
          现在更新只提交元数据；要改自动更新请到「密钥自动更新」页。
        -->

        <!--
          密钥轮换（文档 §5.3 部分刷新）。

          ⚠️ 这一块此前只做在 `views/lifecycle/index.vue` 上，而那个页面
             **没有路由、不在任何菜单里**（1696 行，全仓库无引用）——
             于是"部分刷新"这件事在后端做完并验证通过之后，
             用户**在界面上根本够不到**。本页才是菜单指向的更新入口
             （`sys_menu` 5000 → `keyupdate/index`），所以挪到这里。

          §5.3 的语义：保持节点侧秘密 u 与公开量 uA **不变**，
          只让 KGC 重新生成 w 与部分密钥。所以这里**不生成任何新材料**，
          而是用密钥环里**现有的**私钥去合成新版本的 d_A。
        -->
        <el-form-item v-if="isClAlgorithm(form)" label="密钥轮换">
          <div class="rotation-box">
            <el-switch v-model="rotateRequested" active-text="刷新密钥材料" inactive-text="仅改元数据" />
            <span class="rotation-hint">版本 {{ form.version ?? 1 }} → {{ rotateRequested ? (form.version ?? 1) + 1 : (form.version ?? 1) }}</span>
            <div v-if="rotateRequested" class="rotation-detail">
              <el-tag v-if="localKeyAvailable" size="small" type="warning">部分刷新（uA 保持不变）</el-tag>
              <el-alert
                v-else
                type="warning"
                :closable="false"
                show-icon
                title="本机没有这把密钥的密钥文件，无法合成新版本。请先到「密钥生成」页导出并导入。"
              />
            </div>
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <div class="dialog-footer">
          <el-button type="primary" @click="submitForm">确 定</el-button>
          <el-button @click="cancel">取 消</el-button>
        </div>
      </template>
    </el-dialog>

    <el-drawer v-model="analysisDrawerOpen" title="密钥防线全息扫描结果" size="65%">
      <div v-if="analysisLoading" class="analysis-loading" style="text-align: center; padding: 40px;">
        <p>正在拉取源端底层数据，请稍候...</p>
      </div>
      <div v-else-if="analysisResult" class="analysis-content">
        <h3 style="margin-top:0;">1. 嫌疑面报表 (Base Info)</h3>
        <el-descriptions border :column="2" style="margin-bottom: 20px;">
          <el-descriptions-item label="密钥ID">{{ analysisResult.baseInfo?.keyId }}</el-descriptions-item>
          <el-descriptions-item label="密钥名称">{{ analysisResult.baseInfo?.keyName }}</el-descriptions-item>
          <el-descriptions-item label="算法">{{ analysisResult.baseInfo?.encrytName }}</el-descriptions-item>
          <el-descriptions-item label="使用域">{{ analysisResult.baseInfo?.keyDomain }}</el-descriptions-item>
          <el-descriptions-item label="版本号">{{ analysisResult.baseInfo?.version }}</el-descriptions-item>
          <el-descriptions-item label="安全状态">
            <el-tag :type="statusTagType(analysisResult.baseInfo?.status)">{{ statusText(analysisResult.baseInfo?.status) }}</el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="链上哈希证实" :span="2">{{ analysisResult.baseInfo?.chainHash || '尚未存证' }}</el-descriptions-item>
        </el-descriptions>

        <h3>2. 历史分发存留溯源 (Distribute Footprints)</h3>
        <el-table :data="analysisResult.distributeFootprints" border stripe style="width: 100%; margin-bottom: 20px;" max-height="250">
          <el-table-column prop="user_name" label="下发终端实体"></el-table-column>
          <el-table-column label="分发类型">
             <template #default="scope">
                <el-tag v-if="scope.row.distribute_type == '1'" type="info">初始分发</el-tag>
                <el-tag v-else-if="scope.row.distribute_type == '2'" type="warning">自动更新分发</el-tag>
                <el-tag v-else type="danger">补发</el-tag>
             </template>
          </el-table-column>
          <el-table-column prop="distribute_time" label="下达时间"></el-table-column>
          <el-table-column label="缓存状态" width="120">
             <template #default="scope">
                <el-tag v-if="scope.row.distribute_status == '2'" type="danger">该节点持有缓存!</el-tag>
                <el-tag v-else type="success">未接收成功</el-tag>
             </template>
          </el-table-column>
        </el-table>

        <h3>3. 异常操作轨迹盘点 (Timeline Trails)</h3>
        <el-timeline style="padding-left: 10px;">
          <el-timeline-item
            v-for="(op, index) in analysisResult.operationTrails"
            :key="index"
            :timestamp="op.action_time ? parseTime(op.action_time) : '-'"
            :type="op.action_type === 'REVOKE' ? 'danger' : 'primary'"
            :color="op.result_status == '1' ? '#0bbd87' : '#e4e7ed'"
          >
            <strong>{{ op.action_type === 'UPDATE' ? '密钥更新' : op.action_type === 'REVOKE' ? '密钥回收' : op.action_type }}</strong> 
            操作来源: [{{ op.action_source == 'MANUAL' ? '手动' : op.action_source == 'AUTO' ? '自动' : op.action_source }}]
          </el-timeline-item>
          <el-timeline-item v-if="!analysisResult.operationTrails?.length" timestamp="暂无记录">
            该密钥暂无操作流转痕迹
          </el-timeline-item>
        </el-timeline>
      </div>
    </el-drawer>
  </div>
</template>

<script setup name="KeyUpdate">
import { listKeymanage, getKeymanage, updateKeymanage, getKeymanageAnalysis } from "@/api/lifecycle/lifecycle"
import { composeUpdatedPrivateKey } from '@/utils/cl-key'
import { buildKeyFile, serializeKeyFile } from '@/utils/key-file'
import useKeyringStore from '@/store/modules/keyring'
import { getCommonParams } from '@/services/generate-api'

const { proxy } = getCurrentInstance()
const keyring = useKeyringStore()

// ---------------------------------------------------------------------------
// 密钥轮换（文档 §5.3 部分刷新）
// ---------------------------------------------------------------------------
// 保持节点侧秘密 u 与公开量 uA 不变，只让 KGC 重新生成 w 与部分密钥。
// 所以这里**不生成任何新材料**，而是用密钥环里**现有的**私钥合成新版本 d_A。
const rotateRequested = ref(false)

/** 只有 SM2 / SSCL 走 KGC 份额协议；Kyber / Falcon 的私钥在服务端之外。 */
function isClAlgorithm(row) {
  const name = String(row?.encrytName || '').trim().toUpperCase()
  return name === 'SM2' || name === 'SSCL'
}

/** 本机是否有这把密钥的密钥文件 —— 没有就合成不了新版本。 */
const localKeyAvailable = computed(() => Boolean(keyring.get(form.value.keyId)))

function downloadText(text, filename) {
  const blob = new Blob([text], { type: 'text/plain;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.click()
  URL.revokeObjectURL(url)
}

/**
 * 轮换后在本机合成新版本的 `d_A` 并**就地替换**密钥环里的密钥文件。
 *
 * 服务端已经落库了新版本（这个动作不可逆）。这一步静默失败的后果很具体：
 * 用户看到"更新成功"，而本机保存的还是**旧版本**的私钥 ——
 * 下次解开新信封时只会得到一句含糊的"完整性校验失败"，
 * 没人能想到是轮换时没跟上。所以失败要单独报、报得足够具体。
 */
async function syncLocalKeyAfterRotation(updatedRecord, previousKeyFile) {
  if (!updatedRecord?.keyValue) {
    throw new Error('轮换成功但服务端未返回新的部分密钥，无法在本机合成新版本，请重新导出该密钥文件')
  }
  let commonParams = null
  if (String(updatedRecord.encrytName || '').trim().toUpperCase() === 'SSCL') {
    // SSCL 的合成需要拉格朗日插值用的公共参数（xIndex / yIndex / PPub）
    commonParams = await getCommonParams({
      encrytType: updatedRecord.encrytType,
      encrytName: updatedRecord.encrytName
    })
  }
  const composed = composeUpdatedPrivateKey({
    algorithm: updatedRecord.encrytName,
    keyValue: updatedRecord.keyValue,
    clientPrivateHex: previousKeyFile.private_share,
    commonParams
  })
  const nextKeyFile = await buildKeyFile({
    keyId: updatedRecord.keyId,
    userId: previousKeyFile.user_id,
    algorithm: updatedRecord.encrytName,
    privateShare: composed.finalPrivateKey,
    publicKey: composed.finalPublicKey || ''
  })
  // importKeyFile 在同 key_id 私钥不同时会抛错。这里本来就是要换，
  // 所以先移除旧的再导入 —— 移除的是**已被服务端废弃的版本**。
  keyring.remove(updatedRecord.keyId)
  try {
    await keyring.importKeyFile(nextKeyFile)
  } catch (error) {
    // 导入失败就把旧文件放回去：宁可留下一份已知过期的私钥（看得出问题），
    // 也不要留下一个空的密钥位（表现为"从来没导入过"，更难看懂）。
    try { await keyring.importKeyFile(previousKeyFile) } catch { /* 回填也失败就不再掩盖 */ }
    throw new Error(`本机密钥文件更新失败：${error.message}。请到「密钥生成」页重新导出该密钥文件`)
  }
  // 顺手下载一份：密钥环是本浏览器的，换台机器就没了，而这一版的私钥只存在于本机。
  downloadText(serializeKeyFile(nextKeyFile), `kms-key-${updatedRecord.keyId}-v${updatedRecord.version}.json`)
}

const keymanageList = ref([])
const open = ref(false)
const loading = ref(true)
const showSearch = ref(true)
const ids = ref([])
const single = ref(true)
const multiple = ref(true)
const total = ref(0)
const dialogTitle = ref('密钥更新')

const analysisDrawerOpen = ref(false)
const analysisLoading = ref(false)
const analysisResult = ref(null)

const data = reactive({
  form: {},
  queryParams: {
    pageNum: 1,
    pageSize: 10,
    userId: null,
    userName: null,
    encrytName: null,
    keyName: null
  },
  rules: {
    keyName: [{ max: 64, message: "密钥名称长度不能超过64个字符", trigger: "blur" }],
    keyUse: [{ max: 128, message: "密钥用途长度不能超过128个字符", trigger: "blur" }],
    keyDomain: [{ max: 64, message: "所属域长度不能超过64个字符", trigger: "blur" }]
  }
})

const { queryParams, form, rules } = toRefs(data)

function getList() {
  loading.value = true
  listKeymanage(queryParams.value).then(response => {
    keymanageList.value = response.rows || []
    total.value = response.total || 0
  }).finally(() => {
    loading.value = false
  })
}

function reset() {
  form.value = {
    keyId: null,
    userName: '',
    encrytType: '',
    encrytName: '',
    keyName: '',
    keyUse: '',
    keyDomain: '',
    // `ua` 只用于轮换请求的**一致性校验输入**（服务端要求它与库中一致）。
    // 打开弹窗时从库里取当前值，提交时原样带回 —— 绝不能改成别的值，
    // 那等于换节点侧秘密，服务端会拒绝（§5.3：更新必须保留 uA）。
    ua: '',
    version: null,
    batchMode: false,
    status: ''
  }
  // 每次打开都清掉上一次遗留的轮换意图 ——
  // 否则"上次勾了刷新材料、这次只想改名字"会意外触发轮换。
  rotateRequested.value = false
  proxy.resetForm("keymanageRef")
}

function cancel() {
  open.value = false
  reset()
}

function handleQuery() {
  queryParams.value.pageNum = 1
  getList()
}

function resetQuery() {
  proxy.resetForm("queryRef")
  handleQuery()
}

function handleSelectionChange(selection) {
  ids.value = selection.map(item => item.keyId)
  single.value = selection.length !== 1
  multiple.value = !selection.length
}

function openUpdateDialog(row) {
  reset()
  const keyId = row?.keyId || ids.value[0]
  if (!keyId) {
    proxy.$modal.msgWarning("请先选择一条密钥记录")
    return
  }
  getKeymanage(keyId).then(response => {
    const current = response.data
    form.value = {
      keyId: current.keyId,
      userName: current.userName,
      encrytType: current.encrytType,
      encrytName: current.encrytName,
      keyName: current.keyName,
      keyUse: current.keyUse,
      keyDomain: current.keyDomain,
      // 轮换请求要带回**库里当前**的 uA（服务端会校验一致，不等就拒）。
      // 这与旧实现"用新 uA 触发轮换"是相反的语义 —— §5.3 要求更新时
      // uA 保持不变，只换 KGC 那一半。
      ua: current.ua || '',
      version: current.version ?? 1,
      // 不再读 autoUpdateEnabled：更新弹窗只管元数据（见模板里的说明）
      batchMode: false,
      status: current.status
    }
    // 每次打开都清掉上一次的轮换意图（见 reset 的说明）
    rotateRequested.value = false
    if (isRevoked(current.status)) {
      proxy.$modal.msgWarning("该密钥已回收，无法更新")
      return
    }
    dialogTitle.value = '密钥更新'
    open.value = true
  })
}

async function openAnalysisDialog(row) {
  const keyId = row?.keyId || ids.value[0]
  if (!keyId) {
    proxy.$modal.msgWarning('请先选择一条密钥记录')
    return
  }
  analysisDrawerOpen.value = true
  analysisLoading.value = true
  analysisResult.value = null
  try {
    const res = await getKeymanageAnalysis(keyId)
    if (res.code === 200 || res.code === '200' || res.data) {
      analysisResult.value = res.data || res.baseInfo ? (res.data || res) : null
    } else {
      proxy.$modal.msgError(res.msg || '获取关联分析失败')
    }
  } catch (err) {
    proxy.$modal.msgError(err.message || '网络请求失败')
  } finally {
    analysisLoading.value = false
  }
}

async function handleBatchUpdate() {
  if (!ids.value.length) {
    proxy.$modal.msgWarning('请先选择需要更新的密钥')
    return
  }
  proxy.$modal.confirm(`是否确认批量更新选中的 ${ids.value.length} 条密钥记录？`).then(async () => {
    for (const keyId of ids.value) {
      const response = await getKeymanage(keyId)
      const current = response.data
      if (!current || isRevoked(current.status)) {
        continue
      }
      await updateKeymanage({
        keyId: current.keyId,
        keyName: current.keyName,
        keyUse: current.keyUse,
        keyDomain: isSsclKey(current) ? blankToNull(current.keyDomain) : null
        // 不带 autoUpdate：批量更新只改元数据。
        // 带上它（哪怕值与库里相同）会被后端判成「要改自动更新」而拒绝，
        // 报错还是「没有自动更新操作权限」，与用户在做的事对不上。
      })
    }
    proxy.$modal.msgSuccess('批量更新已提交，结果将推送给用户端接收')
    getList()
  }).catch(() => {})
}

function submitForm() {
  proxy.$refs["keymanageRef"].validate(async (valid) => {
    if (!valid) {
      return
    }
    const rotating = rotateRequested.value
    // 合成需要的那半私钥：拿不到就**不要提交**。
    // 先提交再合成会让库里出现一个版本 +1、而本机根本没有对应 d_A 的密钥 ——
    // 那正是"部分刷新"要消灭的静默错配，不能换个地方再造一次。
    const previousKeyFile = rotating ? keyring.get(form.value.keyId) : null
    if (rotating && !previousKeyFile) {
      proxy.$modal.msgError('本机没有这把密钥的密钥文件，无法合成新版本。请先到「密钥生成」页导出并导入。')
      return
    }
    try {
      const response = await updateKeymanage({
        keyId: form.value.keyId,
        keyName: blankToNull(form.value.keyName),
        keyUse: blankToNull(form.value.keyUse),
        keyDomain: isSsclKey(form.value) ? blankToNull(form.value.keyDomain) : null,
        // 显式声明意图。§5.3 要求更新时 uA **保持不变**，所以请求里带的
        // 正是与库中相同的那个值 —— 从数据上"要轮换"与"只改名字"没有区别，
        // 判据只能是这个显式标志。
        rotate: rotating,
        ua: rotating ? (form.value.ua || undefined) : undefined
        // 不带 autoUpdate：自动更新改由「密钥自动更新」页负责
      })
      if (rotating) {
        // 服务端只做完了"KGC 那一半"。要真正拿到可用的新密钥，
        // 必须在本机用**不变的 u** 与新的部分密钥合成新的 d_A。
        await syncLocalKeyAfterRotation(response?.data, previousKeyFile)
        proxy.$modal.msgSuccess('密钥已部分刷新（uA 不变），本机密钥文件已同步更新')
      } else {
        proxy.$modal.msgSuccess("更新成功，结果已推送到用户端")
      }
      open.value = false
      rotateRequested.value = false
      getList()
    } catch (error) {
      // 轮换失败要说清楚**卡在哪一步** —— 服务端已改而本机没跟上，
      // 与"整个请求都没发出去"是两回事，处置也不同。
      proxy.$modal.msgError(error?.message || '更新失败')
    }
  })
}

function blankToNull(value) {
  return value == null || String(value).trim() === '' ? null : String(value).trim()
}

function isSsclKey(row) {
  return row.encrytType === '无证书非对称加密' && row.encrytName === 'SSCL'
}

function isAutoUpdateEnabled(value) {
  return value === 1 || value === '1' || value === true || value === 'true'
}

function isRevoked(status) {
  return status === '3' || status === 'REVOKED'
}

function statusText(status) {
  return {
    Valid: '有效',
    Active: '有效',
    Frozen: '已冻结',
    Replaced: '已更新',
    Rotated: '已更新',
    Revoked: '已回收',
    '0': '有效',
    '1': '已冻结',
    '2': '已更新',
    '3': '已回收'
  }[status] || (status || '-')
}

function statusTagType(status) {
  if (isRevoked(status)) {
    return 'danger'
  }
  if (status === 'Frozen' || status === '1') {
    return 'info'
  }
  if (status === 'Replaced' || status === '2') {
    return 'warning'
  }
  return 'success'
}

function chainStatusText(status) {
  return { '0': '待上链', '1': '已上链', '2': '失败' }[status] || '-'
}

function chainStatusType(status) {
  return { '0': 'warning', '1': 'success', '2': 'danger' }[status] || 'info'
}

getList()
</script>

<style scoped>
/* 密钥轮换控件（§5.3 部分刷新）。本文件此前没有 style 块，
   这几条只为这一个控件而加，不去动全局样式。 */
.rotation-box { display: flex; flex-direction: column; gap: 8px; align-items: flex-start; }
.rotation-hint { font-size: 12px; color: var(--el-text-color-secondary, #909399); }
.rotation-detail { width: 100%; }
</style>
