<template>
  <div class="app-container">
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
    <el-row :gutter="10" class="mb8">
      <el-col :span="1.5">
        <el-button type="primary" plain icon="Plus" @click="handleAdd" style="padding: 6px 12px; margin-top: 15px;">密钥生成</el-button>
      </el-col>
      <el-col :span="1.5">
        <el-button type="info" plain icon="View" @click="handleViewPublicKeys" style="padding: 6px 12px; margin-top: 15px;">查看公共密钥列表</el-button>
      </el-col>
    </el-row>

    <el-tabs v-model="activeTab" class="user-tabs" style="margin-top: 20px;">
      <el-tab-pane label="我的密钥" name="mykeys">
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
        </el-table>
        <pagination v-show="total>0" :total="total" v-model:page="queryParams.pageNum" v-model:limit="queryParams.pageSize" @pagination="getList" />
      </el-tab-pane>

      <el-tab-pane label="公共密钥" name="publickeys" v-if="userStore.roleLevel <= 1">
        <el-form :inline="true" style="margin-bottom: 15px;">
          <el-form-item label="用户名">
            <el-input v-model="publicKeysQuery.userName" placeholder="请输入用户名" clearable style="width: 200px;" />
          </el-form-item>
          <el-form-item>
            <el-button type="primary" icon="Search" @click="loadPublicKeys">搜索</el-button>
          </el-form-item>
        </el-form>
        <el-table v-loading="publicKeysLoading" :data="publicKeysList">
          <el-table-column label="密钥ID" align="center" prop="keyId" width="80" />
          <el-table-column label="用户名" align="center" prop="userName" width="120" />
          <el-table-column label="加密类型" align="center" prop="encrytType" width="120" />
          <el-table-column label="加密算法" align="center" prop="encrytName" width="120" />
          <el-table-column label="密钥名称" align="center" prop="keyName" width="150" />
          <el-table-column label="公钥值" align="center" prop="keyValue" :show-overflow-tooltip="true" min-width="200" />
          <el-table-column label="创建时间" align="center" prop="creTime" width="160">
            <template #default="scope"><span>{{ parseTime(scope.row.creTime) }}</span></template>
          </el-table-column>
        </el-table>
        <pagination v-show="publicKeysTotal > 0" :total="publicKeysTotal" v-model:page="publicKeysQuery.pageNum" v-model:limit="publicKeysQuery.pageSize" @pagination="loadPublicKeys" />
      </el-tab-pane>
    </el-tabs>

    <el-dialog :title="title" v-model="open" width="500px" append-to-body>
      <el-form ref="keymanageRef" :model="form" :rules="rules" label-width="80px">
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
          <el-input v-model="form.keyDomain" placeholder="请输入密钥所属域" />
        </el-form-item>
      </el-form>
      <template #footer>
        <div class="dialog-footer">
          <el-button type="primary" @click="submitForm">确 定</el-button>
          <el-button @click="cancel">取 消</el-button>
        </div>
      </template>
    </el-dialog>
  </div>
</template>

<script setup name="UserKeys">
import { listKeymanage, addKeymanage, getComParam } from "@/api/generate/keymanage"
import { getUserProfile } from "@/api/system/user"
import { SM2 } from 'gm-crypto'
import { BigInteger } from "jsbn"
import { leftPad } from "@/views/utils.js"
import useUserStore from '@/store/modules/user'

const { proxy } = getCurrentInstance()
const userStore = useUserStore()

const keymanageList = ref([])
const open = ref(false)
const loading = ref(true)
const total = ref(0)
const title = ref("")
const activeTab = ref('mykeys')

const publicKeysList = ref([])
const publicKeysLoading = ref(false)
const publicKeysTotal = ref(0)
const publicKeysQuery = ref({ pageNum: 1, pageSize: 10, userName: null })

const data = reactive({
  form: {},
  encrytNameOptions: [],
  queryParams: {
    pageNum: 1, pageSize: 10, userId: null, userName: null, encrytType: null,
    encrytName: null, keyName: null, keyUse: null, keyValue: null,
    creTime: null, updTime: null, autoUpdate: null, status: null, uA: null
  },
  rules: {
    encrytType: [{ required: true, message: "加密算法类型不能为空", trigger: "change" }],
    encrytName: [{ required: true, message: "加密算法名称不能为空", trigger: "blur" }],
    keyName: [{ required: true, message: "密钥名称不能为空", trigger: "blur" }],
    keyUse: [{ required: true, message: "密钥用途不能为空", trigger: "blur" }]
  }
})

const { queryParams, encrytNameOptions, form, rules } = toRefs(data)
const { publicKey, privateKey } = SM2.generateKeyPair()

function handleCommand(command) {
  if (command === "logout") {
    proxy.$confirm('确定注销并退出系统吗？', '提示', { confirmButtonText: '确定', cancelButtonText: '取消', type: 'warning' }).then(() => {
      userStore.logOut().then(() => { location.href = '/index' })
    }).catch(() => {})
  }
}

function getList() {
  loading.value = true
  listKeymanage(queryParams.value).then(response => {
    keymanageList.value = response.rows.filter(key => key.status !== '3')
    total.value = keymanageList.value.length
    loading.value = false
  })
}

function cancel() { open.value = false; reset() }

function reset() {
  form.value = {
    keyId: null, userId: queryParams.value.userId, userName: queryParams.value.userName,
    encrytType: null, encrytName: null, keyName: null, keyUse: null, keyValue: null,
    creTime: null, updTime: null, autoUpdate: 'false', status: 'Valid', uA: 'null', keyDomain: 'A'
  }
  proxy.resetForm("keymanageRef")
}

function handleSelectionChange(selection) {}

function handleAdd() { reset(); open.value = true; title.value = "添加密钥管理" }

async function submitForm() {
  proxy.$refs["keymanageRef"].validate(valid => {
    if (valid) {
      form.value.uA = publicKey
      if (form.value.keyId != null) {
        updateKeymanage(form.value).then(response => { proxy.$modal.msgSuccess("修改成功"); open.value = false; getList() })
      } else {
        addKeymanage(form.value).then(async response => {
          proxy.$modal.msgSuccess("新增成功"); open.value = false; await getList()
        })
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

function handleViewPublicKeys() {
  if (userStore.roleLevel > 1) {
    proxy.$modal.msgWarning("您没有权限访问公共密钥列表")
  } else {
    activeTab.value = 'publickeys'
  }
}

function loadPublicKeys() {
  publicKeysLoading.value = true
  listKeymanage(publicKeysQuery.value).then(response => {
    publicKeysList.value = response.rows
    publicKeysTotal.value = response.total
    publicKeysLoading.value = false
  })
}

let userId, userName
function getUser() {
  return getUserProfile().then(response => {
    userId = response.data.userId
    userName = response.data.userName
    return { userId, userName }
  })
}

getUser().then(() => {
  if (userId && userName) {
    queryParams.value.userId = userId
    queryParams.value.userName = userName
    getList()
  }
}).catch(error => { console.error('获取用户信息时出错:', error) })
</script>

<style scoped>
::v-deep .el-dropdown { position: absolute; right: 0 }
.avatar-container { position: relative; display: flex; align-items: center }
.avatar-container .left-title { font-size: 24px; font-weight: 600 }
.avatar-container .avatar-wrapper { margin-top: 5px; position: relative }
.avatar-container .avatar-wrapper .user-avatar { cursor: pointer; width: 40px; height: 40px; border-radius: 10px }
.avatar-container .avatar-wrapper i { cursor: pointer; position: absolute; right: -20px; top: 25px; font-size: 12px }
</style>
