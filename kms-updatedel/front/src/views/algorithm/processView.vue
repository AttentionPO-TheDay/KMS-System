<template>
  <div class="process-container">
    <div class="page-title">
      <h1>密钥更新与回收运算全景</h1>
      <p class="subtitle">跟踪无证书环境下的密钥生命周期变迁(自动触发旧碎片销毁与新材料同步)</p>
    </div>

    <!-- 控制面板 -->
    <el-card shadow="never" class="glass-card control-panel">
      <el-form layout="inline" class="form-inline">
        <el-form-item label="待操作操作">
          <el-radio-group v-model="operationType">
            <el-radio-button label="update">模拟密钥更新(Rotation)</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-form-item>
          <el-button type="success" @click="startSimulation" :loading="isProcessing" class="btn-glow">
            <el-icon><Refresh /></el-icon> {{ isProcessing ? '执行中...' : '演练开启' }}
          </el-button>
        </el-form-item>
      </el-form>
      <div v-if="fetchError" class="mt-10" style="color: #F56C6C; font-size: 13px;">{{ fetchError }}</div>
    </el-card>

    <div class="main-flow mt-20" v-if="hasStarted">
      <el-steps :active="activeStep" finish-status="success" align-center class="custom-steps">
        <el-step title="步骤 1: 取回当前状态" description="确定待轮换的旧有密钥" />
        <el-step title="步骤 2: 用户生成新熵" description="本地随机化新 uA / 私隐切片" />
        <el-step title="步骤 3: 中心发放新介质" description="向 KGC 提交并接收新配对载荷" />
        <el-step title="步骤 4: 更新固化" description="算出新轮次私钥" />
      </el-steps>

      <div class="flow-stages mt-30">
        <!-- Step 1: Pre-Condition -->
        <transition name="fade-slide">
          <el-card v-show="activeStep >= 0" class="glass-card stage-card" style="border-left: 4px solid #909399">
            <template #header>
              <div class="card-header">
                <h3><el-icon><Collection /></el-icon> 前置：选取待轮换的目标密钥</h3>
                <el-tag size="small" type="info" effect="dark" v-if="activeStep === 0"><i class="el-icon-loading"></i> 解析中</el-tag>
                <el-tag size="small" type="success" effect="dark" v-else>已锁定配置</el-tag>
              </div>
            </template>
            <div class="payload-box" v-if="step1Data.oldKeyInfo">
              <div class="label">识别到用户下的一条有效密钥 (ID: {{ step1Data.oldKeyInfo.keyId }}) :</div>
              <div class="value">算法类型: {{ step1Data.oldKeyInfo.encrytName || '加载中' }}</div>
              <div class="label mt-10">旧有本地公共部分 (旧 uA):</div>
              <div class="value auth" style="color: #909399">{{ step1Data.oldKeyInfo.uA }}</div>
            </div>
          </el-card>
        </transition>

        <!-- Step 2: New Random -->
        <transition name="fade-slide">
          <el-card v-show="activeStep >= 1" class="glass-card stage-card mt-20" style="border-left: 4px solid #409EFF">
            <template #header>
              <div class="card-header">
                <h3><el-icon><Edit /></el-icon> 第一阶段：客户端销毁旧隐秘，生成新份额</h3>
                <el-tag size="small" type="primary" effect="dark" v-if="activeStep === 1"><i class="el-icon-loading"></i> 生成中</el-tag>
                <el-tag size="small" type="success" effect="dark" v-else>生成完成</el-tag>
              </div>
            </template>
            <div class="payload-box">
              <div class="label">本地新随机份额熵 (New Private Part):</div>
              <div class="value auth">{{ step2Data.newPrivateShare }}</div>
              <div class="label mt-10">映射生成的新公共切片 (New uA):</div>
              <div class="value">{{ step2Data.newUA }}</div>
            </div>
          </el-card>
        </transition>

        <!-- Step 3: KGC Communication -->
        <transition name="fade-slide">
          <el-card v-show="activeStep >= 2" class="glass-card stage-card mt-20" style="border-left: 4px solid #E6A23C">
            <template #header>
              <div class="card-header">
                <h3><el-icon><Upload /></el-icon> 第二阶段：KGC 更新协调并签发新物料</h3>
                <el-tag size="small" type="warning" effect="dark" v-if="activeStep === 2"><i class="el-icon-loading"></i> KGC运算中...</el-tag>
                <el-tag size="small" type="success" effect="dark" v-else>载荷到达</el-tag>
              </div>
            </template>
            <div class="payload-box">
              <div class="label">向中心提交轮换请求并附带新 uA 载荷：</div>
              <div class="code-block" v-if="step3Data.payload">
                <pre>{{ JSON.stringify(step3Data.payload, null, 2) }}</pre>
              </div>
              <div class="label mt-10">KGC 同步响应新配置，销毁中心侧旧切片，返回新切片：</div>
              <div class="code-block response-block" v-if="step3Data.responseObj">
                <pre>{{ JSON.stringify(step3Data.responseObj, null, 2) }}</pre>
              </div>
            </div>
          </el-card>
        </transition>

        <!-- Step 4: Combine -->
        <transition name="fade-slide">
          <el-card v-show="activeStep >= 3" class="glass-card stage-card mt-20" style="border-left: 4px solid #67C23A">
            <template #header>
              <div class="card-header">
                <h3><el-icon><Check /></el-icon> 第三阶段：新轮次公私钥本地生效</h3>
                <el-tag size="small" type="success" effect="dark" v-if="activeStep === 3"><i class="el-icon-loading"></i> 组装中...</el-tag>
                <el-tag size="small" type="success" effect="dark" v-else>密钥轮换完成！</el-tag>
              </div>
            </template>
            <div class="payload-box">
              <div class="desc">基于全新的中心分片与本地绝对隐秘分片，通过椭圆曲线群运算再次获取最新的绝密通道参量：</div>
              
              <div class="flex-box mt-15" v-if="step4Data.PrivateKey">
                <div class="item finalize-block final-priv">
                  <div class="title">🔐 新的最终绝对私钥 (Rotation Success)</div>
                  <div class="content break-all">{{ step4Data.PrivateKey }}</div>
                </div>
                <div class="item finalize-block final-pub">
                  <div class="title">🌍 新的最终公钥 (覆盖原配置)</div>
                  <div class="content break-all">{{ step4Data.PublicKey }}</div>
                </div>
              </div>
            </div>
          </el-card>
        </transition>
      </div>
    </div>
  </div>
</template>

<script setup name="ProcessView">
import { ref, reactive, onMounted } from 'vue'
import { listKeymanage, getComParam, updateKeymanage } from "@/api/keymanage/keymanage"
import { getUserProfile } from "@/api/system/user"
import { SM2 } from 'gm-crypto'
import { BigInteger } from "jsbn"
import { ec as EC } from 'elliptic'
import BN from 'bn.js'

const sm2EC = new EC('p256')

function leftPad(str, len) {
  let lenGap = len - str.length;
  if (lenGap <= 0) { return str; }
  return (new Array(lenGap + 1)).join('0') + str;
}

const operationType = ref('update')

const hasStarted = ref(false)
const activeStep = ref(-1)
const isProcessing = ref(false)
const fetchError = ref('')

const step1Data = reactive({ oldKeyInfo: null })
const step2Data = reactive({ newPrivateShare: '', newUA: '' })
const step3Data = reactive({ payload: null, responseObj: null })
const step4Data = reactive({ PrivateKey: '', PublicKey: '', DA: '' })

// 默认使用持久化的演示用户 test (user_id=3, 密码 admin123)
let sessionUserId = 3;
let sessionUserName = 'test';

onMounted(async () => {
  try {
    const res = await getUserProfile();
    if (res.data && res.data.userId) {
      sessionUserId = res.data.userId;
      sessionUserName = res.data.userName;
    }
  } catch (e) {
    // 保持默认 test 用户
    console.log('使用内置演示用户 test 进行更新过程展示')
  }
})

async function startSimulation() {
  hasStarted.value = true
  activeStep.value = 0
  isProcessing.value = true
  fetchError.value = ''
  
  // Clear
  step1Data.oldKeyInfo = null
  step2Data.newPrivateShare = ''
  step2Data.newUA = ''
  step3Data.payload = null
  step3Data.responseObj = null
  step4Data.PrivateKey = ''
  step4Data.PublicKey = ''

  try {
    // Step 1: Find a key
    const listRes = await listKeymanage({ userName: sessionUserName, pageSize: 1 });
    let targetKey = null
    const validRows = (listRes.rows || listRes.data || []).filter(k => k.status !== '3' && k.encrytType === '无证书非对称加密');
    if (validRows.length > 0) {
      targetKey = validRows[0]
    } else {
      // Mock one for UI demonstration if none found
      targetKey = {
        keyId: 'MOCK-1', userName: sessionUserName || 'demo',
        encrytType: '无证书非对称加密', encrytName: 'SM2', keyName: 'DemoKey',
        uA: '04a1b2c3...',
        keyValue: '{}'
      }
    }

    step1Data.oldKeyInfo = targetKey
    await sleep(1500)
    activeStep.value = 1

    // Step 2: New material
    const { publicKey, privateKey } = SM2.generateKeyPair()
    step2Data.newPrivateShare = privateKey
    step2Data.newUA = publicKey

    await sleep(1500)
    activeStep.value = 2

    // Step 3: API call Update
    const payload = Object.assign({}, targetKey)
    payload.uA = publicKey
    step3Data.payload = payload

    let responseData = targetKey;
    if (targetKey.keyId !== 'MOCK-1') {
      const uRes = await updateKeymanage(payload)
      responseData = uRes.data || payload
    } else {
      responseData.keyValue = JSON.stringify({ partialKey: 'deadbeef', finalPublicKey: 'beefdead' })
    }

    let parsedVal = responseData.keyValue;
    try { parsedVal = JSON.parse(responseData.keyValue) } catch(e){}
    
    step3Data.responseObj = {
      action: "Rotation Material Regenerated",
      newKGCVersion: "V" + Math.floor(Math.random() * 100),
      returnedMaterial: parsedVal
    }

    await sleep(2000)
    activeStep.value = 3

    // Step 4: Finalize locally
    if (targetKey.keyId !== 'MOCK-1') {
      await performGenDA(responseData, privateKey, publicKey)
    } else {
      step4Data.PrivateKey = "mock-private-key-generation-demo"
      step4Data.PublicKey = "mock-public-key-generation-demo"
    }

    await sleep(1000)
    activeStep.value = 4 // Completed

  } catch (err) {
    console.error(err)
    fetchError.value = "执行过程中遭遇异常: " + (err.message || err.msg || err);
  } finally {
    isProcessing.value = false
  }
}

function sleep(ms) { return new Promise(resolve => setTimeout(resolve, ms)) }

const N_SM2 = new BigInteger('FFFFFFFEFFFFFFFFFFFFFFFFFFFFFFFF7203DF6B21C6052B53BBF40939D54123', 16)

async function performGenDA(item, userPrivCode, userPubCode) {
  const { xIndex, yIndex, PPub } = await genUAContext(item.encrytType, item.encrytName)
  
  if (item.encrytName === "SM2") {
    try {
      const keyValueObj = JSON.parse(item.keyValue)
      const dA = (new BigInteger(keyValueObj.partialKey, 16).add(new BigInteger(userPrivCode, 16))).mod(N_SM2)
      step4Data.PrivateKey = leftPad(dA.toString(16), 64)
      step4Data.PublicKey = keyValueObj.finalPublicKey
    } catch (e) {
      step4Data.PrivateKey = "解析返回结果失败"
    }
  } else if (item.encrytName === "SSCL") {
    try {
      const share = JSON.parse(item.keyValue).SSCLKey
      const secret = getSSCLSecret(xIndex, yIndex, share.slice(2, 66), share.slice(66, 130), N_SM2)
      const dA = secret.multiply(new BigInteger(share.slice(2, 66), 16)).mod(N_SM2)
      const sk = new BigInteger(userPrivCode, 16).add(dA).mod(N_SM2)
      step4Data.PrivateKey = leftPad(sk.toString(16), 64)
      step4Data.PublicKey = sm2PointMultiply(PPub, sk.toString(16).padStart(64, '0').slice(-64))
    } catch (e) {
      step4Data.PrivateKey = "系统异常"
    }
  }
}

async function genUAContext(encrytType, encrytName) {
  try {
    const response = await getComParam({ encrytType, encrytName })
    let obj = response.data || response;
    let xIndex = null, yIndex = null
    try { xIndex = obj.xIndex ? JSON.parse(obj.xIndex) : null; yIndex = obj.yIndex ? JSON.parse(obj.yIndex) : null } catch(e) {}
    return { xIndex, yIndex, PPub: obj.PPub }
  } catch(e) { return { xIndex: null, yIndex: null, PPub: null } }
}

function getSSCLSecret(xIndex, yIndex, xHex, yHex, n) {
  const xPoints = xIndex.map(x => new BigInteger(x, 16)); xPoints.push(new BigInteger(xHex, 16))
  const yPoints = yIndex.map(y => new BigInteger(y, 16)); yPoints.push(new BigInteger(yHex, 16))
  const t = xIndex.length; let secret = new BigInteger("0")
  for (let i = 0; i <= t; i++) {
    let num = new BigInteger("1"), den = new BigInteger("1")
    for (let j = 0; j <= t; j++) {
      if (i !== j) {
        num = num.multiply(xPoints[j].negate()).mod(n)
        den = den.multiply(xPoints[i].subtract(xPoints[j]).mod(n)).mod(n)
      }
    }
    const term = yPoints[i].multiply(num.multiply(den.modInverse(n)).mod(n)).mod(n)
    secret = secret.add(term).mod(n)
  }
  return secret.compareTo(new BigInteger("0")) < 0 ? secret.add(n) : secret
}

function sm2PointMultiply(hexPoint, hexScalar) {
  const pt = sm2EC.curve.point(new BN(hexPoint.slice(2, 66), 16), new BN(hexPoint.slice(66, 130), 16))
  const res = pt.mul(new BN(hexScalar, 16))
  return `04${res.getX().toString('hex').padStart(64, '0')}${res.getY().toString('hex').padStart(64, '0')}`
}
</script>

<style scoped>
.process-container {
  padding: 24px; background-color: transparent; min-height: calc(100vh - 84px); color: #e5eaf3;
}

.page-title { margin-bottom: 25px; }
.page-title h1 { font-size: 26px; color: #fff; margin: 0 0 8px 0; font-weight: 600; }
.page-title .subtitle { color: rgba(255, 255, 255, 0.5); margin: 0; font-size: 14px; }

.mt-20 { margin-top: 20px; } .mt-30 { margin-top: 30px; } .mt-10 { margin-top: 10px; } .mt-15 { margin-top: 15px; }

.glass-card {
  background: rgba(255, 255, 255, 0.02); backdrop-filter: blur(24px);
  border: 1px solid rgba(255, 255, 255, 0.05); border-radius: 12px; transition: all 0.3s ease;
}
.glass-card:hover { border-color: rgba(255, 255, 255, 0.15); box-shadow: 0 8px 24px rgba(0, 0, 0, 0.2); }

.control-panel .form-inline { display: flex; gap: 20px; align-items: center; }
:deep(.el-form-item) { margin-bottom: 0; }

.btn-glow { box-shadow: 0 0 10px rgba(103, 194, 58, 0.4); }

.custom-steps { max-width: 900px; margin: 0 auto; }
:deep(.el-step__title) { font-weight: bold; color: rgba(255,255,255,0.8); }
:deep(.el-step__description) { color: rgba(255,255,255,0.4); }
:deep(.el-step__head.is-process) { color: #67C23A; border-color: #67C23A; }
:deep(.el-step__title.is-process) { color: #fff; text-shadow: 0 0 8px rgba(103, 194, 58, 0.5); }
:deep(.el-step__title.is-success) { color: #67C23A; }

.fade-slide-enter-active, .fade-slide-leave-active { transition: all 0.6s ease; }
.fade-slide-enter-from { opacity: 0; transform: translateY(20px); }

.stage-card { margin-bottom: 20px; }
.card-header { display: flex; justify-content: space-between; align-items: center; }
.card-header h3 { margin: 0; font-size: 16px; color: #fff; display: flex; align-items: center; gap: 8px; }

.payload-box { padding: 10px 5px; }
.label { font-size: 13px; color: #a3aab5; margin-bottom: 5px; }

.value {
  font-family: 'Consolas', 'Monaco', monospace; font-size: 13px; background: rgba(0,0,0,0.3);
  padding: 10px; border-radius: 6px; border: 1px solid rgba(255,255,255,0.1); word-break: break-all; color: #409EFF;
}
.value.auth { color: #F56C6C; }

.code-block pre {
  font-family: 'Consolas', monospace; font-size: 12px; background: #1e1e1e;
  padding: 10px; border-radius: 6px; overflow-x: auto; color: #d4d4d4; margin: 0; border: 1px solid #333;
}
.response-block pre { color: #E6A23C; border-color: rgba(230, 162, 60, 0.3); }

.flex-box { display: flex; gap: 20px; flex-wrap: wrap; }
.item.finalize-block { flex: 1; min-width: 300px; background: rgba(0,0,0,0.3); padding: 15px; border-radius: 8px; border-top: 3px solid #67C23A; }
.final-priv { border-color: #F56C6C !important; }

.finalize-block .title { font-weight: bold; font-size: 14px; margin-bottom: 10px; color: #fff; }
.finalize-block .content { font-family: monospace; font-size: 13px; color: #67C23A; line-height: 1.5; }
.final-priv .content { color: #F56C6C; }
.break-all { word-break: break-all; }
</style>
