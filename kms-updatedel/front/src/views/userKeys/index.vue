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
    
    <!--
      本页是「用户密钥池」的只读资产视图。
      按 D1 删除了「查看公共密钥列表」按钮（含公共密钥 Tab 与权限申请弹窗）；
      按"管理员不生成密钥"的原则删除了「密钥生成」按钮与表单弹窗，
      保留「更新」——管理端需要的是无证书密钥的更新与回收，不是生成。
    -->
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
          <el-table-column label="本次生成结果" align="center" width="120">
            <template #default="scope">
              <el-button v-if="scope.row.PrivateKey || scope.row.PublicKey" type="primary" link @click="showLocalKeyResult(scope.row)">查看</el-button>
              <span v-else style="color: #999;">-</span>
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
    </el-tabs>

    <el-dialog title="本地最终密钥结果 (请妥善保存)" v-model="resultOpen" width="760px" append-to-body destroy-on-close>
      <el-alert title="请立即复制并妥善保存您的私钥。此页面刷新后结果将无法找回！" type="warning" show-icon style="margin-bottom: 20px;" />
      
      <div v-if="localResult.encrytType === '无证书非对称加密'">
        <el-descriptions :column="1" border v-if="localResult.encrytName === 'SSCL'">
          <el-descriptions-item label="算法">SSCL</el-descriptions-item>
          <el-descriptions-item label="所属域">{{ localResult.keyDomain || 'A' }}</el-descriptions-item>
          <el-descriptions-item label="部分公钥 (User Public Share)">
            <div style="word-break: break-all; font-family: monospace;">{{ localResult.uA }}</div>
          </el-descriptions-item>
          <el-descriptions-item label="DA 参数 (Domain DA)">
            <div style="word-break: break-all; font-family: monospace;">{{ localResult.DA || '-' }}</div>
          </el-descriptions-item>
        </el-descriptions>
        <div class="key-item mt15">
          <span class="key-label">最终私钥 (Final Private Key):</span>
          <div class="key-value-block success-block">{{ localResult.PrivateKey || '-' }}</div>
        </div>
        <div class="key-item mt15">
          <span class="key-label">最终公钥 (Final Public Key):</span>
          <div class="key-value-block">{{ localResult.PublicKey || '-' }}</div>
        </div>
      </div>
      
      <template #footer>
        <el-button type="primary" @click="copyLocalKeyResult">一键复制结果</el-button>
        <el-button @click="resultOpen = false">关 闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup name="UserKeys">
import { listKeymanage, updateKeymanage, getComParam } from "@/api/generate/keymanage"
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
const loading = ref(true)
const total = ref(0)
const activeTab = ref('mykeys')

const resultOpen = ref(false)
const localResult = ref({})

const sm2 = new EC('p256')

const data = reactive({
  form: {},
  queryParams: {
    pageNum: 1, pageSize: 10, userId: null, userName: null, encrytType: null,
    encrytName: null, keyName: null, keyUse: null, keyValue: null,
    creTime: null, updTime: null, autoUpdate: null, status: null, uA: null
  }
})

const { queryParams, form } = toRefs(data)

let userId, userName

// Session中生成的全局部分公钥和私钥（与老系统行为一致）
// 在每次刷新页面时生成一对随机公私钥用于作为当前用户的部分秘钥份额
const { publicKey, privateKey } = SM2.generateKeyPair()

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
    keymanageList.value = response.rows.filter(key => key.status !== '3')
    total.value = keymanageList.value.length
    loading.value = false
  })
}

function handleSelectionChange(selection) {}

async function handleSubmittedSnapshot(snapshot) {
  const localItem = Object.assign({}, snapshot)
  if (!localItem.keyValue) return
  if (!localItem.userId) localItem.userId = userId
  if (!localItem.userName) localItem.userName = userName
  await performGenDA(localItem)
}

/** 生成用户的最终私钥逻辑 (还原自 legacy-kms 完善的算法) */
async function performGenDA(item) {
  if (item.encrytType !== '无证书非对称加密') return

  const { xIndex, yIndex, PPub } = await genUA(item.encrytType, item.encrytName)
  
  if (item.encrytName === "SM2") {
    const n = new BigInteger('FFFFFFFEFFFFFFFFFFFFFFFFFFFFFFFF7203DF6B21C6052B53BBF40939D54123', 16)
    try {
      const keyValueObj = JSON.parse(item.keyValue)
      const partialKey = keyValueObj.partialKey
      const finalPublicKey = keyValueObj.finalPublicKey
      const num1 = new BigInteger(partialKey, 16)
      const num2 = new BigInteger(privateKey, 16)
      const dA = (num1.add(num2)).mod(n)
      
      item.PublicKey = finalPublicKey
      item.uA = publicKey
      if (dA.compareTo(new BigInteger('1')) > 0 && dA.compareTo(n.subtract(new BigInteger('1'))) < 0) {
        item.PrivateKey = leftPad(dA.toString(16), 64)
      } else {
        proxy.$modal.msgError("SM2 生成失败: 私钥不在有限域内")
      }
    } catch (e) {
      console.error("SM2 解析异常:", e)
    }

  } else if (item.encrytName === "SSCL") {
    if (!xIndex || !yIndex || !PPub) {
      proxy.$modal.msgError("SSCL计算失败: 缺少公共参数 xIndex/yIndex/PPub")
      return
    }
    try {
      const n = new BigInteger('FFFFFFFEFFFFFFFFFFFFFFFFFFFFFFFF7203DF6B21C6052B53BBF40939D54123', 16)
      const keyValueObj = JSON.parse(item.keyValue)
      const share = keyValueObj.SSCLKey
      if (!share) throw new Error("SSCLKey为空")
      
      const xHex = share.slice(2, 66)
      const yHex = share.slice(66, 130)
      const m = new BigInteger(xHex, 16)
      
      const secret = getsecret(xIndex, yIndex, xHex, yHex, n)
      const dA = secret.multiply(m).mod(n)
      const num1 = new BigInteger(privateKey, 16)
      const sk = num1.add(dA).mod(n)
      
      item.PrivateKey = leftPad(sk.toString(16), 64)
      
      let dAHex = dA.toString(16).padStart(64, '0').slice(-64)
      item.DA = sm2PointMultiply(PPub, dAHex)
      
      let skHex = sk.toString(16).padStart(64, '0').slice(-64)
      item.PublicKey = sm2PointMultiply(PPub, skHex)
      item.uA = publicKey
    } catch (e) {
      console.error("SSCL计算异常:", e)
      proxy.$modal.msgError("SSCL计算异常: " + e.message)
    }
  }

  // 弹窗展示核心结果
  showLocalKeyResult(item)
}

/** 获取公共参数以辅助解密 */
function genUA(encrytType, encrytName) {
  return getComParam({ encrytType, encrytName }).then(response => {
    const PPub = response.PPub
    let xIndex = null, yIndex = null
    try {
      xIndex = response.xIndex ? JSON.parse(response.xIndex) : null
      yIndex = response.yIndex ? JSON.parse(response.yIndex) : null
    } catch(e) {}
    return { xIndex, yIndex, PPub }
  }).catch(() => { return { xIndex: null, yIndex: null, PPub: null } })
}

/** 拉格朗日插值法 SSCL 份额解密 */
function getsecret(xIndex, yIndex, xHex, yHex, n) {
  if (xIndex.length !== yIndex.length) throw new Error("xIndex和yIndex数组长度必须相等")
  const xPoints = xIndex.map(x => new BigInteger(x, 16))
  xPoints.push(new BigInteger(xHex, 16))
  const yPoints = yIndex.map(y => new BigInteger(y, 16))
  yPoints.push(new BigInteger(yHex, 16))
  
  const t = xIndex.length
  let secret = new BigInteger("0")
  for (let i = 0; i <= t; i++) {
    let numerator = new BigInteger("1")
    let denominator = new BigInteger("1")
    for (let j = 0; j <= t; j++) {
      if (i !== j) {
        const xj = xPoints[j]
        numerator = numerator.multiply(xj.negate()).mod(n)
        const xi = xPoints[i]
        const diff = xi.subtract(xj).mod(n)
        denominator = denominator.multiply(diff).mod(n)
      }
    }
    const invDenominator = denominator.modInverse(n)
    if (!invDenominator) throw new Error("无法计算模逆元")
    const li = numerator.multiply(invDenominator).mod(n)
    const term = yPoints[i].multiply(li).mod(n)
    secret = secret.add(term).mod(n)
  }
  if (secret.compareTo(new BigInteger("0")) < 0) {
    secret = secret.add(n)
  }
  return secret
}

function sm2PointMultiply(hexPoint, hexScalar) {
  if (!hexPoint.startsWith('04')) throw new Error('点格式错误，必须以04开头')
  const x = hexPoint.slice(2, 66)
  const y = hexPoint.slice(66, 130)
  const point = sm2.curve.point(new BN(x, 16), new BN(y, 16))
  const scalar = new BN(hexScalar, 16)
  const result = point.mul(scalar)
  return `04${result.getX().toString('hex').padStart(64, '0')}${result.getY().toString('hex').padStart(64, '0')}`
}

function showLocalKeyResult(item) {
  localResult.value = Object.assign({}, item)
  resultOpen.value = true
}

function canRotateCertlessKey(row) {
  return row.encrytType === '无证书非对称加密' && (row.encrytName === 'SM2' || row.encrytName === 'SSCL')
}

// 密钥更新，重新触发表单编辑提交流即可
function handleRotate(row) {
  proxy.$modal.confirm(`确认使用当前环境材料更新密钥 ${row.keyName} 吗？\n注意：这会下发新的密钥对`).then(() => {
    form.value = Object.assign({}, row)
    form.value.uA = publicKey // 使用新的公钥份额
    return updateKeymanage(form.value)
  }).then(async (response) => {
    proxy.$modal.msgSuccess('更新请求已发出')
    await handleSubmittedSnapshot(response.data || form.value)
    scheduleRefresh()
  }).catch(() => {})
}

function scheduleRefresh() {
  getList()
  window.setTimeout(() => {
    getList()
  }, 1200)
  window.setTimeout(() => {
    getList()
  }, 3500)
}

function copyLocalKeyResult() {
  const result = localResult.value
  let text = `Algorithm: ${result.encrytName || ''}\nPrivateKey: ${result.PrivateKey || ''}\nPublicKey: ${result.PublicKey || ''}\n`
  if (result.encrytName === 'SSCL') text += `DA: ${result.DA || ''}\nuA: ${result.uA || ''}`
  navigator.clipboard.writeText(text).then(() => {
    proxy.$modal.msgSuccess('结果已复制')
  }).catch(() => {
    proxy.$modal.msgError('复制失败，请手动复制')
  })
}

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
})
</script>

<style scoped>
::v-deep .el-dropdown { position: absolute; right: 0 }
.avatar-container { position: relative; display: flex; align-items: center }
.avatar-container .left-title { font-size: 24px; font-weight: 600 }
.avatar-container .avatar-wrapper { margin-top: 5px; position: relative }
.avatar-container .avatar-wrapper .user-avatar { cursor: pointer; width: 40px; height: 40px; border-radius: 10px }
.avatar-container .avatar-wrapper i { cursor: pointer; position: absolute; right: -20px; top: 25px; font-size: 12px }

.key-item { margin-bottom: 20px; }
.key-label { display: block; font-size: 14px; font-weight: bold; color: #a3aab5; margin-bottom: 8px; }
.key-value-block {
    background-color: #1e1e1e; color: #d4d4d4;
    padding: 12px; border-radius: 6px; font-family: monospace;
    word-wrap: break-word; font-size: 13px; line-height: 1.5;
    border: 1px solid #333;
}
.success-block { border-left: 4px solid #67c23a; }
.mt15 { margin-top: 15px; }
</style>
