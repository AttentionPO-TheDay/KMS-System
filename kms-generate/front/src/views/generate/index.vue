<template>
  <div class="app-container">
    <el-form :model="queryParams" ref="queryRef" :inline="true" v-show="showSearch" label-width="68px">
      <el-form-item label="用户ID" prop="userId">
        <el-input v-model="queryParams.userId" placeholder="请输入用户ID" clearable @keyup.enter="handleQuery" />
      </el-form-item>
      <el-form-item label="用户名" prop="userName">
        <el-input v-model="queryParams.userName" placeholder="请输入用户名" clearable @keyup.enter="handleQuery" />
      </el-form-item>
      <el-form-item label="加密算法名称" prop="encrytName">
        <el-input v-model="queryParams.encrytName" placeholder="请输入加密算法名称" clearable @keyup.enter="handleQuery" />
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
        <el-button type="primary" plain icon="Plus" @click="handleAdd" v-hasPermi="['keymanage:keymanage:add']" style="padding: 6px 12px; margin-top: 15px;">密钥生成</el-button>
      </el-col>
      <right-toolbar v-model:showSearch="showSearch" @queryTable="getList"></right-toolbar>
    </el-row>

    <el-table v-loading="loading" :data="keymanageList" @selection-change="handleSelectionChange">
      <el-table-column type="selection" width="55" align="center" />
      <el-table-column label="密钥ID" align="center" prop="keyId" />
      <el-table-column label="用户ID" align="center" prop="userId" />
      <el-table-column label="加密算法类型" align="center" prop="encrytType" />
      <el-table-column label="加密算法名称" align="center" prop="encrytName" />
      <el-table-column label="密钥名称" align="center" prop="keyName" />
      <el-table-column label="密钥用途" align="center" prop="keyUse" />
      <el-table-column label="创建时间" align="center" prop="creTime" />
      <el-table-column label="更新时间" align="center" prop="updTime" />
      <el-table-column label="密钥自动更新状态" align="center" prop="autoUpdate" />
      <el-table-column label="操作" align="center" width="150">
        <template #default="scope">
          <el-button type="primary" link icon="View" @click="handleViewDetails(scope.row)">详情</el-button>
        </template>
      </el-table-column>
    </el-table>

    <pagination v-show="total>0" :total="total" v-model:page="queryParams.pageNum" v-model:limit="queryParams.pageSize" @pagination="getList" />

    <el-dialog :title="title" v-model="open" width="500px" append-to-body>
      <el-form ref="keymanageRef" :model="form" :rules="rules" label-width="80px">
        <el-form-item label="选择用户" prop="userId">
          <el-select v-model="form.userId" placeholder="请选择用户" filterable>
            <el-option v-for="user in userList" :key="user.userId" :label="`${user.userName} (ID: ${user.userId})`" :value="user.userId" />
          </el-select>
        </el-form-item>
        <el-form-item label="加密算法类型" prop="encrytType">
          <el-select v-model="form.encrytType" placeholder="请选择加密算法类型" @change="handleEncrytTypeChange">
            <el-option label="无证书非对称加密" value="无证书非对称加密" />
            <el-option label="对称加密" value="对称加密" />
            <el-option label="非对称加密" value="非对称加密" />
            <el-option label="单向加密" value="单向加密" />
          </el-select>
        </el-form-item>
        <el-form-item label="加密算法名称" prop="encrytName">
          <el-select v-model="form.encrytName" placeholder="请选择加密算法名称">
            <el-option v-for="option in encrytNameOptions" :key="option.value" :label="option.label" :value="option.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="密钥名称" prop="keyName">
          <el-input v-model="form.keyName" placeholder="请输入密钥名称" />
        </el-form-item>
        <el-form-item label="密钥用途" prop="keyUse">
          <el-input v-model="form.keyUse" placeholder="请输入密钥用途" />
        </el-form-item>
        <el-form-item label="密钥所属域(SSCL)" prop="keyDomain">
          <el-input v-model="form.keyDimain" placeholder="请输入密钥所属域" />
        </el-form-item>
      </el-form>
      <template #footer>
        <div class="dialog-footer">
          <el-button type="primary" @click="submitForm">确 定</el-button>
          <el-button @click="cancel">取 消</el-button>
        </div>
      </template>
    </el-dialog>

    <el-dialog title="密钥详细信息" v-model="detailOpen" width="700px" append-to-body destroy-on-close>
      <div class="detail-container">
        <el-divider content-position="left">基础信息</el-divider>
        <el-descriptions :column="2" border>
          <el-descriptions-item label="密钥ID"><el-tag type="info">{{ detailInfo.keyId }}</el-tag></el-descriptions-item>
          <el-descriptions-item label="密钥名称">{{ detailInfo.keyName }}</el-descriptions-item>
          <el-descriptions-item label="用户ID">{{ detailInfo.userId }}</el-descriptions-item>
          <el-descriptions-item label="当前状态">
            <el-tag :type="detailInfo.autoUpdate === 'true' ? 'success' : 'warning'">{{ detailInfo.autoUpdate === 'true' ? '自动更新' : '手动更新' }}</el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="加密类型">
            <el-tag effect="dark">{{ detailInfo.encrytName }}</el-tag>
            <span style="margin-left:8px; font-size:12px; color:#999">({{ detailInfo.encrytType }})</span>
          </el-descriptions-item>
          <el-descriptions-item label="密钥用途">{{ detailInfo.keyUse }}</el-descriptions-item>
          <el-descriptions-item label="创建时间">{{ detailInfo.creTime }}</el-descriptions-item>
          <el-descriptions-item label="更新时间">{{ detailInfo.updTime }}</el-descriptions-item>
        </el-descriptions>
        <el-divider content-position="left">核心数据</el-divider>
        <div class="key-content-box">
          <template v-if="detailInfo.encrytName === 'SM2'">
            <div class="key-item">
              <span class="key-label">部分私钥 (Partial Key):</span>
              <div class="key-value-block">{{ detailInfo.parsedKey?.partialKey || '无数据' }}</div>
            </div>
            <div class="key-item">
              <span class="key-label">声明公钥 (Public Key Declaration):</span>
              <div class="key-value-block">{{ detailInfo.parsedKey?.finalPublicKey || '无数据' }}</div>
            </div>
          </template>
          <template v-else-if="detailInfo.encrytName === 'SSCL'">
            <div class="key-item">
              <span class="key-label">SS份额 (SS Share):</span>
              <div class="key-value-block">{{ detailInfo.parsedKey?.SSCLKey || '无数据' }}</div>
            </div>
            <div class="key-item">
              <span class="key-label">密钥所属域 (Domain):</span>
              <div class="key-value-block">{{ detailInfo.parsedKey?.SSCLDomian || detailInfo.keyDimain || '无数据' }}</div>
            </div>
          </template>
          <template v-else>
            <div class="key-item">
              <span class="key-label">密钥原始值 (Key Value):</span>
              <div class="key-value-block">{{ detailInfo.keyValue }}</div>
            </div>
          </template>
        </div>
      </div>
      <template #footer>
        <div class="dialog-footer">
          <el-button type="primary" @click="copyDetailInfo">一键复制信息</el-button>
          <el-button @click="detailOpen = false">关 闭</el-button>
        </div>
      </template>
    </el-dialog>
  </div>
</template>

<script setup name="KeyGenerate">
import { listKeymanage, getKeymanage, delKeymanage, addKeymanage, updateKeymanage } from "@/api/generate/keymanage"
import { listNonAdminUsers } from "@/api/system/user"
import useUserStore from '@/store/modules/user'

const { proxy } = getCurrentInstance()
const userStore = useUserStore()

const keymanageList = ref([])
const userList = ref([])
const open = ref(false)
const loading = ref(true)
const showSearch = ref(true)
const ids = ref([])
const single = ref(true)
const multiple = ref(true)
const total = ref(0)
const title = ref("")
const detailOpen = ref(false)
const detailInfo = ref({})

const data = reactive({
  form: {},
  encrytNameOptions: [],
  queryParams: {
    pageNum: 1,
    pageSize: 10,
    userId: null,
    userName: null,
    encrytType: null,
    encrytName: null,
    keyName: null,
    keyUse: null,
    keyValue: null,
    creTime: null,
    updTime: null,
    autoUpdate: null,
    status: null
  },
  rules: {
    userId: [{ required: true, message: "用户ID不能为空", trigger: "blur" }],
    userName: [{ required: true, message: "用户名不能为空", trigger: "blur" }],
    encrytType: [{ required: true, message: "加密算法类型不能为空", trigger: "change" }],
    encrytName: [{ required: true, message: "加密算法名称不能为空", trigger: "blur" }],
    keyName: [{ required: true, message: "密钥名称不能为空", trigger: "blur" }],
    keyUse: [{ required: true, message: "密钥用途不能为空", trigger: "blur" }]
  }
})

const { queryParams, encrytNameOptions, form, rules } = toRefs(data)

function getList() {
  loading.value = true
  listKeymanage(queryParams.value).then(response => {
    keymanageList.value = response.rows
    total.value = response.total
    loading.value = false
  })
}

function cancel() { open.value = false; reset() }

function reset() {
  form.value = {
    keyId: null, userId: null, userName: 'null', encrytType: null, encrytName: null,
    keyName: null, keyUse: null, keyValue: null, creTime: null, updTime: null,
    autoUpdate: 'false', status: 'null'
  }
  proxy.resetForm("keymanageRef")
}

function handleQuery() { queryParams.value.pageNum = 1; getList() }

function resetQuery() { proxy.resetForm("queryRef"); handleQuery() }

function handleSelectionChange(selection) {
  ids.value = selection.map(item => item.keyId)
  single.value = selection.length != 1
  multiple.value = !selection.length
}

function handleAdd() {
  reset()
  listNonAdminUsers().then(response => { userList.value = response.data || [] })
  open.value = true
  title.value = "添加密钥管理"
}

function handleViewDetails(row) {
  const info = { ...row }
  try { info.parsedKey = JSON.parse(row.keyValue || '{}') } catch (e) { info.parsedKey = {} }
  detailInfo.value = info
  detailOpen.value = true
}

function copyDetailInfo() {
  const info = detailInfo.value
  let textToCopy = `密钥详情导出\n----------------\n`
  textToCopy += `KeyID: ${info.keyId}\nName: ${info.keyName}\nUserID: ${info.userId}\nType: ${info.encrytName}\n`
  if (info.encrytName === 'SM2') {
    textToCopy += `Partial Key: ${info.parsedKey?.partialKey}\nPublic Key: ${info.parsedKey?.finalPublicKey}`
  } else if (info.encrytName === 'SSCL') {
    textToCopy += `Share: ${info.parsedKey?.SSCLKey}\nDomain: ${info.parsedKey?.SSCLDomian}`
  } else {
    textToCopy += `Key Value: ${info.keyValue}`
  }
  navigator.clipboard.writeText(textToCopy).then(() => { proxy.$modal.msgSuccess("信息已复制到剪贴板") }).catch(() => { proxy.$modal.msgError("复制失败，请手动复制") })
}

function submitForm() {
  proxy.$refs["keymanageRef"].validate(valid => {
    if (valid) {
      if (form.value.keyId != null) {
        if (form.value.encrytType == "无证书非对称加密") { alert("该功能需配合用户系统使用") }
        else {
          updateKeymanage(form.value).then(response => { proxy.$modal.msgSuccess("修改成功"); open.value = false; getList() })
        }
      } else {
        if (form.value.encrytType == "无证书非对称加密") { alert("该功能需配合用户系统使用") }
        else {
          addKeymanage(form.value).then(response => { proxy.$modal.msgSuccess("新增成功"); open.value = false; getList() })
        }
      }
    }
  })
}

function handleEncrytTypeChange(value) {
  if (value === '无证书非对称加密') { encrytNameOptions.value = [{ label: 'SM2', value: 'SM2' }, { label: 'SSCL', value: 'SSCL' }] }
  else if (value === '对称加密') { encrytNameOptions.value = [{ label: 'AES', value: 'AES' }] }
  else if (value === '非对称加密') { encrytNameOptions.value = [{ label: 'RSA', value: 'RSA' }, { label: 'ECC', value: 'ECC' }] }
  else if (value === '单向加密') { encrytNameOptions.value = [{ label: 'MD5', value: 'MD5' }, { label: 'BLAKE2', value: 'BLAKE2' }, { label: 'SHA-256', value: 'SHA-256' }, { label: 'SHA-512', value: 'SHA-512' }, { label: 'SHA-3', value: 'SHA-3' }] }
  else { encrytNameOptions.value = [] }
  form.value.encrytName = ''
}

getList()
</script>

<style scoped>
.detail-container { padding: 0 10px }
.key-content-box { background-color: #f8f9fa; border-radius: 4px; padding: 15px; margin-top: 10px; border: 1px solid #ebeef5 }
.key-item { margin-bottom: 15px }
.key-item:last-child { margin-bottom: 0 }
.key-label { display: block; font-weight: bold; color: #606266; margin-bottom: 5px; font-size: 14px }
.key-value-block { background-color: #282c34; color: #abb2bf; padding: 10px; border-radius: 4px; font-family: Consolas, Monaco, monospace; font-size: 13px; word-break: break-all; white-space: pre-wrap; line-height: 1.5; box-shadow: inset 0 0 6px rgba(0,0,0,0.1) }
:deep(.el-descriptions__label) { width: 120px; font-weight: bold }
</style>
