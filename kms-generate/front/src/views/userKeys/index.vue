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
          <el-table-column label="本地结果" align="center" width="120">
            <template #default="scope">
              <el-button v-if="scope.row.localDerived" type="primary" link @click="showLocalKeyResult(scope.row.localDerived)">查看</el-button>
              <span v-else style="color: #999;">无</span>
            </template>
          </el-table-column>
          <el-table-column label="操作" align="center" width="140">
            <template #default="scope">
              <el-button v-if="canRotateCertlessKey(scope.row)" type="primary" link @click="handleRotate(scope.row)">更新</el-button>
            </template>
          </el-table-column>
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

    <el-dialog title="本地最终密钥结果" v-model="resultOpen" width="760px" append-to-body destroy-on-close>
      <el-descriptions :column="1" border>
        <el-descriptions-item label="密钥ID">{{ localResult.keyId || '-' }}</el-descriptions-item>
        <el-descriptions-item label="算法">{{ localResult.encrytName || '-' }}</el-descriptions-item>
        <el-descriptions-item label="本地最终私钥">
          <div style="word-break: break-all; font-family: monospace;">{{ localResult.privateKey || '-' }}</div>
        </el-descriptions-item>
        <el-descriptions-item label="本地最终公钥">
          <div style="word-break: break-all; font-family: monospace;">{{ localResult.publicKey || '-' }}</div>
        </el-descriptions-item>
        <el-descriptions-item label="用户部分公钥 uA">
          <div style="word-break: break-all; font-family: monospace;">{{ localResult.uA || '-' }}</div>
        </el-descriptions-item>
        <el-descriptions-item label="本地私钥份额">
          <div style="word-break: break-all; font-family: monospace;">{{ localResult.userPartialPrivateKey || '-' }}</div>
        </el-descriptions-item>
        <el-descriptions-item label="服务端返回 keyValue">
          <div style="word-break: break-all; font-family: monospace;">{{ localResult.keyValue || '-' }}</div>
        </el-descriptions-item>
      </el-descriptions>
      <el-divider content-position="left">更新对比</el-divider>
      <el-descriptions :column="1" border>
        <el-descriptions-item label="上一版最终私钥">
          <div style="word-break: break-all; font-family: monospace;">{{ localResult.previousPrivateKey || '-' }}</div>
        </el-descriptions-item>
        <el-descriptions-item label="当前最终私钥">
          <div style="word-break: break-all; font-family: monospace;">{{ localResult.privateKey || '-' }}</div>
        </el-descriptions-item>
        <el-descriptions-item label="上一版最终公钥">
          <div style="word-break: break-all; font-family: monospace;">{{ localResult.previousPublicKey || '-' }}</div>
        </el-descriptions-item>
        <el-descriptions-item label="当前最终公钥">
          <div style="word-break: break-all; font-family: monospace;">{{ localResult.publicKey || '-' }}</div>
        </el-descriptions-item>
        <el-descriptions-item label="是否发生更新">
          <el-tag :type="localResult.hasRotation ? 'success' : 'info'">{{ localResult.hasRotation ? '是' : '否' }}</el-tag>
        </el-descriptions-item>
      </el-descriptions>
      <template #footer>
        <el-button type="primary" @click="copyLocalKeyResult">复制结果</el-button>
        <el-button @click="resultOpen = false">关 闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup name="UserKeys">
import { listKeymanage, addKeymanage, updateKeymanage, getComParam } from "@/api/generate/keymanage"
import { getUserProfile } from "@/api/system/user"
import { SM2 } from 'gm-crypto'
import { BigInteger } from "jsbn"
import { leftPad } from "@/views/utils.js"
import { ec as EC } from 'elliptic'
import BN from 'bn.js'
import useUserStore from '@/store/modules/user'

const { proxy } = getCurrentInstance()
const userStore = useUserStore()

const keymanageList = ref([])
const open = ref(false)
const loading = ref(true)
const total = ref(0)
const title = ref("")
const activeTab = ref('mykeys')
const resultOpen = ref(false)
const localResult = ref({})

const publicKeysList = ref([])
const publicKeysLoading = ref(false)
const publicKeysTotal = ref(0)
const publicKeysQuery = ref({ pageNum: 1, pageSize: 10, userName: null })
const sm2 = new EC('p256')
const CERTLESS_CACHE_KEY = 'kms_generate_local_certless_keys'
const SM2_N = new BigInteger('FFFFFFFEFFFFFFFFFFFFFFFFFFFFFFFF7203DF6B21C6052B53BBF40939D54123', 16)

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

function handleCommand(command) {
  if (command === "logout") {
    proxy.$confirm('确定注销并退出系统吗？', '提示', { confirmButtonText: '确定', cancelButtonText: '取消', type: 'warning' }).then(() => {
      userStore.logOut().then(() => { location.href = `${import.meta.env.BASE_URL}index` })
    }).catch(() => {})
  }
}

function getList() {
  loading.value = true
  listKeymanage(queryParams.value).then(response => {
    const cache = loadLocalCertlessCache()
    keymanageList.value = response.rows
      .filter(key => key.status !== '3')
      .map(key => ({ ...key, localDerived: cache[String(key.keyId)] || null }))
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
      const keyPair = shouldDeriveLocally(form.value) ? SM2.generateKeyPair() : null
      if (keyPair) {
        form.value.uA = keyPair.publicKey
      }
      if (form.value.keyId != null) {
        updateKeymanage(form.value).then(response => { proxy.$modal.msgSuccess("修改成功"); open.value = false; getList() })
      } else {
        addKeymanage(form.value).then(async response => {
          const createdKey = response.data || null
          if (keyPair && createdKey) {
            await deriveAndStoreLocalKey(createdKey, keyPair.privateKey)
          }
          proxy.$modal.msgSuccess("新增成功"); open.value = false; await getList()
        }).catch(error => {
          if (error?.message) {
            proxy.$modal.msgError(error.message)
          }
        })
      }
    }
  })
}

function shouldDeriveLocally(currentForm) {
  return currentForm.encrytType === '无证书非对称加密' && (currentForm.encrytName === 'SM2' || currentForm.encrytName === 'SSCL')
}

async function deriveAndStoreLocalKey(keyRecord, localPrivateKey) {
  const previous = loadLocalCertlessCache()[String(keyRecord.keyId)] || null
  let derived = null
  if (keyRecord.encrytName === 'SM2') {
    derived = deriveSm2LocalKey(keyRecord, localPrivateKey)
  } else if (keyRecord.encrytName === 'SSCL') {
    const commonParams = await getComParam({ encrytType: keyRecord.encrytType, encrytName: keyRecord.encrytName })
    derived = deriveSsclLocalKey(keyRecord, localPrivateKey, commonParams)
  }

  if (!derived) {
    throw new Error('本地最终密钥计算失败')
  }

  const result = {
    keyId: keyRecord.keyId,
    encrytName: keyRecord.encrytName,
    userPartialPrivateKey: leftPad(localPrivateKey, 64),
    privateKey: derived.privateKey,
    publicKey: derived.publicKey,
    previousPrivateKey: previous?.privateKey || null,
    previousPublicKey: previous?.publicKey || null,
    hasRotation: Boolean(previous && (previous.privateKey !== derived.privateKey || previous.publicKey !== derived.publicKey)),
    uA: keyRecord.uA,
    keyValue: keyRecord.keyValue
  }
  persistLocalCertlessResult(result)
  showLocalKeyResult(result)
}

function deriveSm2LocalKey(keyRecord, localPrivateKey) {
  const keyValue = parseKeyValue(keyRecord.keyValue)
  const partialKey = keyValue.partialKey
  const finalPublicKey = keyValue.finalPublicKey
  if (!partialKey || !finalPublicKey) {
    throw new Error('SM2 服务端返回缺少 partialKey 或 finalPublicKey')
  }

  const serverPartial = new BigInteger(partialKey, 16)
  const userPartial = new BigInteger(localPrivateKey, 16)
  const finalPrivate = serverPartial.add(userPartial).mod(SM2_N)
  if (finalPrivate.compareTo(BigInteger.ONE) < 0 || finalPrivate.compareTo(SM2_N) >= 0) {
    throw new Error('SM2 最终私钥超出有效范围')
  }

  return {
    privateKey: leftPad(finalPrivate.toString(16), 64),
    publicKey: finalPublicKey
  }
}

function deriveSsclLocalKey(keyRecord, localPrivateKey, commonParams) {
  const keyValue = parseKeyValue(keyRecord.keyValue)
  const share = keyValue.SSCLKey
  if (!share) {
    throw new Error('SSCL 服务端返回缺少 SSCLKey')
  }

  const xIndex = parseHexArray(commonParams?.xIndex)
  const yIndex = parseHexArray(commonParams?.yIndex)
  const pPub = commonParams?.PPub
  if (!xIndex.length || !yIndex.length || !pPub) {
    throw new Error('SSCL 公共参数不完整')
  }

  const mHex = share.slice(2, 66)
  const yHex = share.slice(66, 130)
  const m = new BigInteger(mHex, 16)
  const secret = interpolateSecret(xIndex, yIndex, mHex, yHex, SM2_N)
  const dA = secret.multiply(m).mod(SM2_N)
  const userPartial = new BigInteger(localPrivateKey, 16)
  const finalPrivate = userPartial.add(dA).mod(SM2_N)
  if (finalPrivate.compareTo(BigInteger.ONE) < 0 || finalPrivate.compareTo(SM2_N) >= 0) {
    throw new Error('SSCL 最终私钥超出有效范围')
  }

  return {
    privateKey: leftPad(finalPrivate.toString(16), 64),
    publicKey: sm2PointMultiply(pPub, leftPad(finalPrivate.toString(16), 64))
  }
}

function parseKeyValue(rawValue) {
  try {
    return JSON.parse(rawValue || '{}')
  } catch (error) {
    throw new Error('服务端返回的 keyValue 不是合法 JSON')
  }
}

function parseHexArray(rawValue) {
  if (!rawValue) {
    return []
  }
  if (Array.isArray(rawValue)) {
    return rawValue
  }
  try {
    return JSON.parse(rawValue)
  } catch (error) {
    throw new Error('公共参数数组解析失败')
  }
}

function interpolateSecret(xIndex, yIndex, xHex, yHex, modulus) {
  if (xIndex.length !== yIndex.length) {
    throw new Error('xIndex 与 yIndex 长度不一致')
  }

  const xPoints = xIndex.map(item => new BigInteger(item, 16))
  xPoints.push(new BigInteger(xHex, 16))
  const yPoints = yIndex.map(item => new BigInteger(item, 16))
  yPoints.push(new BigInteger(yHex, 16))

  let secret = BigInteger.ZERO
  for (let i = 0; i < xPoints.length; i++) {
    let numerator = BigInteger.ONE
    let denominator = BigInteger.ONE
    for (let j = 0; j < xPoints.length; j++) {
      if (i === j) {
        continue
      }
      numerator = numerator.multiply(xPoints[j].negate()).mod(modulus)
      denominator = denominator.multiply(xPoints[i].subtract(xPoints[j]).mod(modulus)).mod(modulus)
    }
    const coefficient = numerator.multiply(denominator.modInverse(modulus)).mod(modulus)
    secret = secret.add(yPoints[i].multiply(coefficient)).mod(modulus)
  }

  return secret.signum() < 0 ? secret.add(modulus) : secret
}

function sm2PointMultiply(hexPoint, hexScalar) {
  if (!hexPoint || !hexPoint.startsWith('04')) {
    throw new Error('点格式错误，必须以 04 开头')
  }
  const x = hexPoint.slice(2, 66)
  const y = hexPoint.slice(66, 130)
  const point = sm2.curve.point(new BN(x, 16), new BN(y, 16))
  const result = point.mul(new BN(hexScalar, 16))
  return `04${result.getX().toString('hex').padStart(64, '0')}${result.getY().toString('hex').padStart(64, '0')}`
}

function loadLocalCertlessCache() {
  try {
    return JSON.parse(localStorage.getItem(CERTLESS_CACHE_KEY) || '{}')
  } catch (error) {
    return {}
  }
}

function persistLocalCertlessResult(result) {
  const cache = loadLocalCertlessCache()
  cache[String(result.keyId)] = result
  localStorage.setItem(CERTLESS_CACHE_KEY, JSON.stringify(cache))
}

function showLocalKeyResult(result) {
  localResult.value = result
  resultOpen.value = true
}

function canRotateCertlessKey(row) {
  return row.encrytType === '无证书非对称加密' && (row.encrytName === 'SM2' || row.encrytName === 'SSCL')
}

function handleRotate(row) {
  const localEntry = loadLocalCertlessCache()[String(row.keyId)]
  if (!localEntry?.userPartialPrivateKey || !localEntry?.uA) {
    proxy.$modal.msgError('缺少本地私钥份额，无法执行更新')
    return
  }

  proxy.$modal.confirm(`确认更新密钥 ${row.keyId} 吗？`).then(() => {
    const payload = {
      keyId: row.keyId,
      userId: row.userId,
      userName: row.userName,
      encrytType: row.encrytType,
      encrytName: row.encrytName,
      keyName: row.keyName,
      keyUse: row.keyUse,
      keyDomain: row.keyDomain,
      uA: localEntry.uA
    }
    return updateKeymanage(payload)
  }).then(async response => {
    const updatedKey = response.data || null
    if (!updatedKey) {
      throw new Error('更新接口未返回新的密钥材料')
    }
    await deriveAndStoreLocalKey(updatedKey, localEntry.userPartialPrivateKey)
    proxy.$modal.msgSuccess('更新成功')
    await getList()
  }).catch(error => {
    if (error && error !== 'cancel' && error?.message) {
      proxy.$modal.msgError(error.message)
    }
  })
}

function copyLocalKeyResult() {
  const result = localResult.value
  const text = [
    `KeyID: ${result.keyId || ''}`,
    `Algorithm: ${result.encrytName || ''}`,
    `UserPartialPrivateKey: ${result.userPartialPrivateKey || ''}`,
    `PreviousPrivateKey: ${result.previousPrivateKey || ''}`,
    `PrivateKey: ${result.privateKey || ''}`,
    `PreviousPublicKey: ${result.previousPublicKey || ''}`,
    `PublicKey: ${result.publicKey || ''}`,
    `HasRotation: ${result.hasRotation ? 'true' : 'false'}`,
    `uA: ${result.uA || ''}`,
    `keyValue: ${result.keyValue || ''}`
  ].join('\n')
  navigator.clipboard.writeText(text).then(() => {
    proxy.$modal.msgSuccess('结果已复制')
  }).catch(() => {
    proxy.$modal.msgError('复制失败，请手动复制')
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
