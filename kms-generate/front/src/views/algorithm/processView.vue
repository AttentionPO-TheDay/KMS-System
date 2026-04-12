<template>
  <div class="process-container">
    <div class="page-title">
      <h1>生成计算过程交互展示</h1>
      <p class="subtitle">追踪无证书非对称算法生成中的密文交换与还原流转</p>
    </div>

    <!-- 控制面板 -->
    <el-card shadow="never" class="glass-card control-panel">
      <el-form layout="inline" class="form-inline">
        <el-form-item label="算法类型">
          <el-radio-group v-model="form.encrytName">
            <el-radio-button label="SM2">无证书 SM2 算法</el-radio-button>
            <el-radio-button label="SSCL">无证书 SSCL 算法</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="测试密钥标签">
          <el-input v-model="form.keyName" placeholder="如：TestKey-1" style="width: 200px" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="initSimulation" class="btn-glow">
            <el-icon><VideoPlay /></el-icon> 开始演练流
          </el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <div class="main-flow mt-20" v-if="hasStarted">
      <el-steps :active="activeStep" finish-status="success" align-center class="custom-steps">
        <el-step title="步骤 1: 用户侧协参数生成" description="本地生熵并向KGC提交参量" />
        <el-step title="步骤 2: 发起真实请求" description="KGC密码中心计算影子/门限分片" />
        <el-step title="步骤 3: 本地恢复结果" description="恢复并固化最终密钥材料" />
        <el-step title="演示完成" description="系统已入库并生效" />
      </el-steps>

      <div class="flow-stages mt-30">
        <!-- Step 1: User Request Param -->
        <transition name="fade-slide">
          <el-card class="glass-card stage-card" style="border-left: 4px solid #409EFF">
            <template #header>
              <div class="card-header">
                <h3><el-icon><User /></el-icon> 本地端 - 随机参数与请求载荷构造</h3>
                <el-tag size="small" type="primary" effect="dark" v-if="activeStep === 0">待执行</el-tag>
                <el-tag size="small" type="success" effect="dark" v-else>已完成</el-tag>
              </div>
            </template>
            <div class="payload-box">
              <div v-if="activeStep === 0" style="margin-bottom: 20px;">
                <el-button type="primary" size="small" @click="runStep1" :loading="isProcessing">第一步：执行并生成本地参数</el-button>
              </div>

              <div class="desc" style="color: #a3aab5; margin-bottom: 10px;">
                本地临时私钥份额（仅参与后续本地合成，不作为最终结果单独展示）：
                <span class="inline-code inline-secret">{{ step1Data.privateShare || '点击按钮执行后显示...' }}</span>
              </div>

              <div class="label mt-10">本地生成的公共切片公钥 (uA):</div>
              <div class="value">{{ step1Data.uA || '点击按钮执行后显示...' }}</div>
              
              <div class="label mt-10">构造将发往服务端 KGC 的注册载荷:</div>
              <div class="code-block">
                <pre v-if="step1Data.payload">{{ JSON.stringify(step1Data.payload, null, 2) }}</pre>
                <pre v-else style="color: #666">等待生成载荷...</pre>
              </div>
            </div>
          </el-card>
        </transition>

        <!-- Step 2: KGC processing & Response -->
        <transition name="fade-slide">
          <el-card class="glass-card stage-card mt-20" style="border-left: 4px solid #E6A23C">
            <template #header>
              <div class="card-header">
                <h3><el-icon><Cpu /></el-icon> 中心端 - 向 KGC 系统发起交互</h3>
                <el-tag size="small" type="info" effect="dark" v-if="activeStep < 1">等待前置步骤</el-tag>
                <el-tag size="small" type="warning" effect="dark" v-else-if="activeStep === 1">待执行网络请求</el-tag>
                <el-tag size="small" type="success" effect="dark" v-else>通信完成</el-tag>
              </div>
            </template>
            <div class="payload-box">
              <div v-if="activeStep === 1" style="margin-bottom: 20px;">
                <el-button type="warning" size="small" @click="runStep2" :loading="isProcessing">第二步：向系统提交并获取远程分片片段</el-button>
              </div>
              <p style="color:rgba(255,255,255,0.7); font-size:13px; margin-bottom:10px;">由于计算过程在可信受控服务端完成，此处捕获展现由 KGC 回传给该用户的碎片报文情况：</p>
              
              <div class="label mt-10">网络抓包 - KGC 真实返回的数据项：</div>
              <div class="code-block response-block">
                <pre v-if="step2Data.responseObj">{{ JSON.stringify(step2Data.responseObj, null, 2) }}</pre>
                <pre v-else style="color: #666">等待前置操作触发请求...</pre>
              </div>

              <div v-if="step2Data.responseObj && step2Data.responseObj.returnedMaterial && (step2Data.responseObj.returnedMaterial.kgcRandomW || step2Data.responseObj.returnedMaterial.kgcMx)" class="math-steps-box mt-15" style="background: rgba(230,162,60,0.1); padding: 15px; border-radius: 8px; border: 1px dashed rgba(230,162,60,0.4);">
                <div class="label" style="color: #E6A23C; font-weight: bold; margin-bottom: 8px;">🔍 KGC 计算黑盒揭秘 (内部中间变量):</div>
                <div v-if="step2Data.responseObj.returnedMaterial.kgcRandomW">
                  <div style="font-family: monospace; font-size: 12px; color: #d4d4d4; margin-bottom: 5px; word-break: break-all;">
                    > [SM2] KGC侧临时生成的随机数 (w): {{ step2Data.responseObj.returnedMaterial.kgcRandomW }}
                  </div>
                  <div style="font-family: monospace; font-size: 12px; color: #d4d4d4; margin-bottom: 5px; word-break: break-all;">
                    > [SM2] KGC侧结合用户信息算出的摘要 (lambda): {{ step2Data.responseObj.returnedMaterial.kgcLambda }}
                  </div>
                </div>
                <div v-if="step2Data.responseObj.returnedMaterial.kgcMx">
                  <div style="font-family: monospace; font-size: 12px; color: #d4d4d4; margin-bottom: 5px; word-break: break-all;">
                    > [SSCL] KGC侧代入多项式的因式 (M_x): {{ step2Data.responseObj.returnedMaterial.kgcMx }}
                  </div>
                </div>
              </div>
            </div>
          </el-card>
        </transition>

        <!-- Step 3: Local Combine -->
        <transition name="fade-slide">
          <el-card class="glass-card stage-card mt-20" style="border-left: 4px solid #67C23A">
            <template #header>
              <div class="card-header">
                <h3><el-icon><Key /></el-icon> {{ form.encrytName === 'SSCL' ? '用户端 - 本地恢复最终结果' : '用户端 - 最终组合与固化' }}</h3>
                <el-tag size="small" type="info" effect="dark" v-if="activeStep < 2">等待前置步骤</el-tag>
                <el-tag size="small" type="success" effect="dark" v-else-if="activeStep === 2">待计算生成</el-tag>
                <el-tag size="small" type="success" effect="dark" v-else>拼装成功</el-tag>
              </div>
            </template>
            <div class="payload-box">
              <div v-if="activeStep === 2" style="margin-bottom: 20px;">
                <el-button type="success" size="small" @click="runStep3" :loading="isProcessing">{{ form.encrytName === 'SSCL' ? '第三步：本地恢复 SSCL 最终结果' : '第三步：本地利用数学法则完成最终算密' }}</el-button>
              </div>

              <div class="desc" style="color: #a3aab5; margin-bottom: 10px;" v-if="form.encrytName==='SSCL'">操作说明：读取 KGC 返回的 SSCLKey，结合公共参数 xIndex / yIndex 做拉格朗日插值恢复门限秘密，再与本地私钥合成最终私钥、公钥和 DA。</div>
              <div class="desc" style="color: #a3aab5; margin-bottom: 10px;" v-else>操作说明：将 KGC 半密私片段 与 用户的临时私片段 根据大素数有限群 {N_SM2} 做加法求模运算...</div>
              
              <!-- 中间计算过程展示 -->
              <div class="math-steps-box mt-10" style="background: rgba(103,194,58,0.1); padding: 15px; border-radius: 8px; border: 1px dashed rgba(103,194,58,0.4);">
                <div class="label" style="color: #67C23A; font-weight: bold; margin-bottom: 8px;">🔍 揭秘内部计算过程:</div>
                <div v-if="step3Data.mathSteps && step3Data.mathSteps.length > 0">
                  <div v-for="(step, i) in step3Data.mathSteps" :key="i" style="font-family: monospace; font-size: 12px; color: #d4d4d4; margin-bottom: 5px; word-break: break-all;">
                    > {{ step }}
                  </div>
                </div>
                <div v-else style="font-family: monospace; font-size: 12px; color: #666; margin-bottom: 5px;">
                  等待触发计算...
                </div>
              </div>

              <div v-if="form.encrytName==='SSCL'" class="mt-15">
                <div class="label">说明：第二步展示的是 KGC 返回的门限份额；以下内容为本地恢复得到的最终私钥、公钥和所属域。</div>
              </div>

              <div class="flex-box mt-15">
                <div class="item finalize-block final-priv">
                  <div class="title">🔐 最终私钥</div>
                  <div class="content break-all">{{ step3Data.PrivateKey || '计算中...' }}</div>
                </div>
                <div class="item finalize-block final-pub">
                  <div class="title">🌍 {{ form.encrytName === 'SSCL' ? '最终公钥' : '最终暴露公钥 (发信验证用)' }}</div>
                  <div class="content break-all">{{ step3Data.PublicKey || '计算中...' }}</div>
                </div>
              </div>
              <div v-if="form.encrytName==='SSCL'" class="mt-15">
                <div class="label">所属域：</div>
                <div class="value">{{ step3Data.keyDomain || step2Data.snapshotValue?.keyDomain || 'A' }}</div>
              </div>
            </div>
          </el-card>
        </transition>
      </div>
      <div v-if="fetchError" class="mt-20" style="color: #F56C6C; font-size: 13px; text-align: center;">{{ fetchError }}</div>
    </div>
  </div>
</template>

<script setup name="ProcessView">
import { ref, reactive, onMounted } from 'vue'
import { getComParam, addKeymanage } from "@/api/generate/keymanage"
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

const form = reactive({
  encrytName: 'SM2',
  keyName: 'Vis-Test-Gen'
})

const hasStarted = ref(false)
const activeStep = ref(-1)
const isProcessing = ref(false)

const step1Data = reactive({ privateShare: '', uA: '', payload: null })
const step2Data = reactive({ responseObj: null, snapshotValue: null })
const fetchError = ref('')
const step3Data = reactive({ PrivateKey: '', PublicKey: '', DA: '', uA: '', keyDomain: '', mathSteps: [] })

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
    console.log('使用内置演示用户 test 进行计算过程展示')
  }
})

// 初始化并展示骨架框架
function initSimulation() {
  hasStarted.value = true
  activeStep.value = 0
  isProcessing.value = false
  fetchError.value = ''
  
  step1Data.privateShare = ''
  step1Data.uA = ''
  step1Data.payload = null
  step2Data.responseObj = null
  step2Data.snapshotValue = null
  step3Data.PrivateKey = ''
  step3Data.PublicKey = ''
  step3Data.DA = ''
  step3Data.uA = ''
  step3Data.keyDomain = ''
  step3Data.mathSteps = []
}

function runStep1() {
  const { publicKey, privateKey } = SM2.generateKeyPair()
  step1Data.privateShare = privateKey
  step1Data.uA = publicKey

  const payload = {
    userId: sessionUserId,
    userName: sessionUserName || 'system',
    encrytType: '无证书非对称加密',
    encrytName: form.encrytName,
    keyName: form.keyName + '-' + Math.floor(Math.random() * 1000),
    keyUse: '演示计算',
    keyDomain: form.encrytName === 'SSCL' ? 'A' : undefined,
    autoUpdate: 'false',
    status: 'Valid',
    uA: publicKey
  }
  step1Data.payload = payload
  activeStep.value = 1
}

async function runStep2() {
  isProcessing.value = true
  fetchError.value = ''
  try {
    const response = await addKeymanage(step1Data.payload)
    const snapshot = response.data || step1Data.payload
    
    let visualValue = snapshot.keyValue;
    try {
      visualValue = JSON.parse(snapshot.keyValue)
    } catch(err) {}

    step2Data.responseObj = {
        keyId: snapshot.keyId,
        encrytName: snapshot.encrytName,
        returnedMaterial: visualValue
    }
    step2Data.snapshotValue = snapshot
    activeStep.value = 2
  } catch (err) {
    console.error(err)
    fetchError.value = "服务端请求遭遇异常: " + (err.message || err.msg || err);
  } finally {
    isProcessing.value = false
  }
}

async function runStep3() {
  isProcessing.value = true
  try {
    await performGenDA(step2Data.snapshotValue, step1Data.privateShare, step1Data.uA)
    activeStep.value = 4 // Completed
  } catch(e) {
    console.error(e)
    fetchError.value = "本地计算遭遇异常"
  } finally {
    isProcessing.value = false
  }
}

const N_SM2 = new BigInteger('FFFFFFFEFFFFFFFFFFFFFFFFFFFFFFFF7203DF6B21C6052B53BBF40939D54123', 16)

async function performGenDA(item, userPrivCode, userPubCode) {
  const { xIndex, yIndex, PPub } = await genUAContext(item.encrytType, item.encrytName)
  step3Data.PrivateKey = ''
  step3Data.PublicKey = ''
  step3Data.DA = ''
  step3Data.uA = userPubCode || ''
  step3Data.keyDomain = item.keyDomain || ''
  step3Data.mathSteps = []

  if (item.encrytName === "SM2") {
    try {
      const keyValueObj = JSON.parse(item.keyValue)
      const partialKey = keyValueObj.partialKey
      const finalPublicKey = keyValueObj.finalPublicKey
      step3Data.mathSteps.push(`提取 KGC 返回的服务端计算分片 T_A: ${partialKey}`)
      step3Data.mathSteps.push(`提取 本地生成的随机熵分片 u_A (num2): ${userPrivCode}`)

      const num1 = new BigInteger(partialKey, 16)
      const num2 = new BigInteger(userPrivCode, 16)
      step3Data.mathSteps.push(`模加运算: dA = (T_A + u_A) mod N_SM2`)
      const dA = (num1.add(num2)).mod(N_SM2)
      step3Data.mathSteps.push(`得出 dA(hex) 结果`)
      
      if (dA.compareTo(new BigInteger('1')) > 0 && dA.compareTo(N_SM2.subtract(new BigInteger('1'))) < 0) {
        step3Data.PrivateKey = leftPad(dA.toString(16), 64)
        step3Data.PublicKey = finalPublicKey
      } else {
        step3Data.PrivateKey = "生成失败: 私钥不在有限域内"
      }
    } catch (e) {
      step3Data.PrivateKey = "解析KGC返回载荷异常!"
    }
  } else if (item.encrytName === "SSCL") {
    try {
      const keyValueObj = JSON.parse(item.keyValue)
      const share = keyValueObj.SSCLKey
      step3Data.keyDomain = keyValueObj.SSCLDomain || keyValueObj.SSCLDomian || item.keyDomain || 'A'
      step3Data.mathSteps.push(`提取 KGC 返回的多项式门限响应分片: ${share}`)
      step3Data.mathSteps.push(`读取本地保留的用户部分公钥 uA: ${userPubCode}`)

      const xHex = share.slice(2, 66)
      const yHex = share.slice(66, 130)
      const m = new BigInteger(xHex, 16)
      step3Data.mathSteps.push(`解析分片维度: X_coord: ${xHex}, Y_coord: ${yHex}`)
      
      const secret = getSSCLSecret(xIndex, yIndex, xHex, yHex, N_SM2)
      step3Data.mathSteps.push(`门限重建: 通过拉格朗日插值获得中心侧门限隐秘值 S_KGC`)

      const dA = secret.multiply(m).mod(N_SM2)
      step3Data.mathSteps.push(`代入转换: dA = S_KGC * M_x mod N_SM2`)

      const num1 = new BigInteger(userPrivCode, 16)
      const sk = num1.add(dA).mod(N_SM2)
      step3Data.mathSteps.push(`最终私钥合成: sk = (num1 + dA) mod N_SM2`)

      step3Data.PrivateKey = leftPad(sk.toString(16), 64)

      let dAHex = dA.toString(16).padStart(64, '0').slice(-64)
      step3Data.DA = sm2PointMultiply(PPub, dAHex)
      let skHex = sk.toString(16).padStart(64, '0').slice(-64)
      step3Data.PublicKey = sm2PointMultiply(PPub, skHex)
      step3Data.mathSteps.push(`椭圆曲线映射: DA = PPub * dA，PublicKey = PPub * sk`)
    } catch (e) {
      step3Data.PrivateKey = "SSCL计算异常:" + e.message
      step3Data.PublicKey = ''
      step3Data.DA = ''
    }
  }
}

async function genUAContext(encrytType, encrytName) {
  try {
    const response = await getComParam({ encrytType, encrytName })
    let obj = response.data || response;
    const PPub = obj.PPub
    let xIndex = null, yIndex = null
    try {
      xIndex = obj.xIndex ? JSON.parse(obj.xIndex) : null
      yIndex = obj.yIndex ? JSON.parse(obj.yIndex) : null
    } catch(e) {}
    return { xIndex, yIndex, PPub }
  } catch(e) {
    return { xIndex: null, yIndex: null, PPub: null }
  }
}

function getSSCLSecret(xIndex, yIndex, xHex, yHex, n) {
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
  const x = hexPoint.slice(2, 66)
  const y = hexPoint.slice(66, 130)
  const point = sm2EC.curve.point(new BN(x, 16), new BN(y, 16))
  const scalar = new BN(hexScalar, 16)
  const result = point.mul(scalar)
  return `04${result.getX().toString('hex').padStart(64, '0')}${result.getY().toString('hex').padStart(64, '0')}`
}
</script>

<style scoped>
.process-container {
  padding: 24px;
  background-color: transparent;
  min-height: calc(100vh - 84px);
  color: #e5eaf3;
}
.page-title { margin-bottom: 25px; }
.page-title h1 { font-size: 26px; color: #fff; margin: 0 0 8px 0; font-weight: 600; }
.page-title .subtitle { color: rgba(255, 255, 255, 0.5); margin: 0; font-size: 14px; }
.mt-20 { margin-top: 20px; }
.mt-30 { margin-top: 30px; }
.mt-10 { margin-top: 10px; }
.mt-15 { margin-top: 15px; }
.glass-card {
  background: rgba(255, 255, 255, 0.02);
  backdrop-filter: blur(24px);
  border: 1px solid rgba(255, 255, 255, 0.05);
  border-radius: 12px;
  transition: all 0.3s ease;
}
.glass-card:hover {
  border-color: rgba(255, 255, 255, 0.15);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.2);
}
.control-panel .form-inline { display: flex; gap: 20px; align-items: center; }
:deep(.el-form-item) { margin-bottom: 0; }
.btn-glow { box-shadow: 0 0 10px rgba(64, 158, 255, 0.4); }
.custom-steps { max-width: 900px; margin: 0 auto; }
:deep(.el-step__title) { font-weight: bold; color: rgba(255,255,255,0.8); }
:deep(.el-step__description) { color: rgba(255,255,255,0.4); }
:deep(.el-step__head.is-process) { color: #409EFF; border-color: #409EFF; }
:deep(.el-step__title.is-process) { color: #fff; text-shadow: 0 0 8px rgba(64,158,255,0.5); }
:deep(.el-step__title.is-success) { color: #67C23A; }
.fade-slide-enter-active, .fade-slide-leave-active { transition: all 0.6s ease; }
.fade-slide-enter-from { opacity: 0; transform: translateY(20px); }
.stage-card { margin-bottom: 20px; }
.card-header { display: flex; justify-content: space-between; align-items: center; }
.card-header h3 { margin: 0; font-size: 16px; color: #fff; display: flex; align-items: center; gap: 8px; }
.payload-box { padding: 10px 5px; }
.label { font-size: 13px; color: #a3aab5; margin-bottom: 5px; }
.value {
  font-family: 'Consolas', 'Monaco', monospace;
  font-size: 13px; background: rgba(0,0,0,0.3); padding: 10px; border-radius: 6px;
  border: 1px solid rgba(255,255,255,0.1); word-break: break-all; color: #409EFF;
}
.value.auth { color: #F56C6C; }
.inline-code {
  display: inline-block;
  margin-left: 8px;
  padding: 2px 8px;
  border-radius: 4px;
  font-family: 'Consolas', 'Monaco', monospace;
  font-size: 12px;
  background: rgba(0,0,0,0.28);
  border: 1px solid rgba(255,255,255,0.08);
  word-break: break-all;
}
.inline-secret {
  color: #F56C6C;
}
.code-block pre {
  font-family: 'Consolas', monospace; font-size: 12px; background: #1e1e1e;
  padding: 10px; border-radius: 6px; overflow-x: auto; color: #d4d4d4; margin: 0; border: 1px solid #333;
}
.response-block pre { color: #E6A23C; border-color: rgba(230, 162, 60, 0.3); }
.flex-box { display: flex; gap: 20px; flex-wrap: wrap; }
.item.finalize-block {
  flex: 1; min-width: 300px; background: rgba(0,0,0,0.3); padding: 15px; border-radius: 8px; border-top: 3px solid #67C23A;
}
.final-priv { border-color: #F56C6C !important; }
.finalize-block .title { font-weight: bold; font-size: 14px; margin-bottom: 10px; color: #fff; }
.finalize-block .content { font-family: monospace; font-size: 13px; color: #67C23A; line-height: 1.5; }
.final-priv .content { color: #F56C6C; }
.break-all { word-break: break-all; }
</style>
