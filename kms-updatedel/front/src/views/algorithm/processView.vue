<template>
  <div class="process-container">
    <div class="page-title">
      <h1>密钥更新与回收运算全景</h1>
      <p class="subtitle">跟踪无证书环境下的密钥生命周期变迁(自动触发旧碎片销毁与新材料同步)</p>
    </div>

    <!-- 控制面板 -->
    <el-card shadow="never" class="glass-card control-panel">
      <el-form layout="inline" class="form-inline">
        <el-form-item label="待执行操作">
          <el-radio-group v-model="operationType">
            <el-radio-button label="update">模拟密钥更新(Rotation)</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-form-item>
          <el-button type="success" @click="initSimulation" class="btn-glow">
            <el-icon><Refresh /></el-icon> 演练开启
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
          <el-card class="glass-card stage-card" style="border-left: 4px solid #909399">
            <template #header>
              <div class="card-header">
                <h3><el-icon><Collection /></el-icon> 前置：选取待轮换的目标密钥</h3>
                <el-tag size="small" type="info" effect="dark" v-if="activeStep === 0">待执行</el-tag>
                <el-tag size="small" type="success" effect="dark" v-else>已锁定配置</el-tag>
              </div>
            </template>
            <div class="payload-box">
              <div v-if="activeStep === 0" style="margin-bottom: 20px; display: flex; gap: 10px;">
                <el-button type="info" size="small" @click="runStep1" :loading="isProcessing">第一步：自数据库捞取模拟更新的旧密钥配置</el-button>
                <el-button type="primary" size="small" @click="mockGenVisible = true">快捷操作：一步步生成全新的前置模拟密钥</el-button>
              </div>

              <div class="label">识别到用户下的一条有效旧密钥 (Target Key) :</div>
              <div class="value">
                <span v-if="step1Data.oldKeyInfo">ID: {{ step1Data.oldKeyInfo.keyId }} | 算法: {{ step1Data.oldKeyInfo.encrytName }}</span>
                <span v-else style="color:#666;">运行获取后展示...</span>
              </div>
              <div class="label mt-10">需要被废除的老旧公共特征值 (旧 uA):</div>
              <div class="value auth" style="color: #909399">
                {{ step1Data.oldKeyInfo ? step1Data.oldKeyInfo.uA : '运行获取后展示...' }}
              </div>
            </div>
          </el-card>
        </transition>

        <!-- Generate Simulation Dialog -->
        <el-dialog v-model="mockGenVisible" title="一步步生成全新前置模拟密钥" width="700px" custom-class="glass-card" :close-on-click-modal="false" @close="resetMockGen">
          <el-steps :active="mockGenStep" align-center style="margin-bottom: 20px;">
            <el-step title="造参数"></el-step>
            <el-step title="联中心"></el-step>
            <el-step title="落数据"></el-step>
          </el-steps>
          
          <div v-if="mockGenStep === 0" style="text-align: center; padding: 20px;">
            <p style="color: #a3aab5; font-size: 13px; margin-bottom: 15px;">在本地环境模拟生成份额熵 uA 和私钥 num2。</p>
            <el-button type="primary" @click="runMockGenStep1" :loading="isMockProcessing">执行：本地生熵</el-button>
          </div>
          
          <div v-else-if="mockGenStep === 1" style="text-align: center; padding: 20px;">
            <p style="color: #a3aab5; font-size: 13px; margin-bottom: 15px;">提取出的 uA：{{ mockGenData.uA }}<br><br>将此 uA 封入参数包，向服务器发起真实的生成注册请求。</p>
            <el-button type="warning" @click="runMockGenStep2" :loading="isMockProcessing">执行：请求 KGC 协同</el-button>
          </div>
          
          <div v-else-if="mockGenStep === 2" style="text-align: center; padding: 20px;">
            <p style="color: #67c23a; font-size: 13px; margin-bottom: 15px;">中心计算完毕，密钥主体物料已返回并入库验证通过！<br><br>中心分段签名内容: {{ mockGenData.returnedMaterialPreview }}</p>
            <el-button type="success" @click="runMockGenStep3">选定该密钥进入更新流</el-button>
          </div>
        </el-dialog>

        <!-- Step 2: New Random -->
        <transition name="fade-slide">
          <el-card class="glass-card stage-card mt-20" style="border-left: 4px solid #409EFF">
            <template #header>
              <div class="card-header">
                <h3><el-icon><Edit /></el-icon> 第一阶段：客户端销毁旧隐秘，生成新份额</h3>
                <el-tag size="small" type="info" effect="dark" v-if="activeStep < 1">等待前置步骤</el-tag>
                <el-tag size="small" type="primary" effect="dark" v-else-if="activeStep === 1">待执行</el-tag>
                <el-tag size="small" type="success" effect="dark" v-else>生成完成</el-tag>
              </div>
            </template>
            <div class="payload-box">
              <div v-if="activeStep === 1" style="margin-bottom: 20px;">
                <el-button type="primary" size="small" @click="runStep2" :loading="isProcessing">第二步：执行本地参数随机轮转策略</el-button>
              </div>

              <div class="label">本地新随机份额熵 (New Private Part):</div>
              <div class="value auth">{{ step2Data.newPrivateShare || '等待生成...' }}</div>
              <div class="label mt-10">映射生成的新公共切片 (New uA):</div>
              <div class="value">{{ step2Data.newUA || '等待生成...' }}</div>
            </div>
          </el-card>
        </transition>

        <!-- Step 3: KGC Communication -->
        <transition name="fade-slide">
          <el-card class="glass-card stage-card mt-20" style="border-left: 4px solid #E6A23C">
            <template #header>
              <div class="card-header">
                <h3><el-icon><Upload /></el-icon> 第二阶段：KGC 更新协调并签发新物料</h3>
                <el-tag size="small" type="info" effect="dark" v-if="activeStep < 2">等待前置步骤</el-tag>
                <el-tag size="small" type="warning" effect="dark" v-else-if="activeStep === 2">待更新请求</el-tag>
                <el-tag size="small" type="success" effect="dark" v-else>载荷到达</el-tag>
              </div>
            </template>
            <div class="payload-box">
              <div v-if="activeStep === 2" style="margin-bottom: 20px;">
                <el-button type="warning" size="small" @click="runStep3" :loading="isProcessing">第三步：向服务端发起联名更新及版本替换请求</el-button>
              </div>

              <div class="label">向中心提交轮换请求并附带新 uA 载荷：</div>
              <div class="code-block">
                <pre v-if="step3Data.payload">{{ JSON.stringify(step3Data.payload, null, 2) }}</pre>
                <pre v-else style="color:#666">等待构建...</pre>
              </div>
              <div class="label mt-10">KGC 同步响应新配置，销毁中心侧旧切片，返回新切片：</div>
              <div class="code-block response-block">
                <pre v-if="step3Data.responseObj">{{ JSON.stringify(step3Data.responseObj, null, 2) }}</pre>
                <pre v-else style="color:#666">等待更新确认...</pre>
              </div>

              <div v-if="step3Data.responseObj && step3Data.responseObj.returnedMaterial && (step3Data.responseObj.returnedMaterial.kgcRandomW || step3Data.responseObj.returnedMaterial.kgcMx)" class="math-steps-box mt-15" style="background: rgba(230,162,60,0.1); padding: 15px; border-radius: 8px; border: 1px dashed rgba(230,162,60,0.4);">
                <div class="label" style="color: #E6A23C; font-weight: bold; margin-bottom: 8px;">🔍 KGC 计算黑盒揭秘 (内部中间变量):</div>
                <div v-if="step3Data.responseObj.returnedMaterial.kgcRandomW">
                  <div style="font-family: monospace; font-size: 12px; color: #d4d4d4; margin-bottom: 5px; word-break: break-all;">
                    > [SM2] KGC侧临时生成的新轮次随机构件 (w): {{ step3Data.responseObj.returnedMaterial.kgcRandomW }}
                  </div>
                  <div style="font-family: monospace; font-size: 12px; color: #d4d4d4; margin-bottom: 5px; word-break: break-all;">
                    > [SM2] KGC侧结合新信息算出的摘要验证 (lambda): {{ step3Data.responseObj.returnedMaterial.kgcLambda }}
                  </div>
                </div>
                <div v-if="step3Data.responseObj.returnedMaterial.kgcMx">
                  <div style="font-family: monospace; font-size: 12px; color: #d4d4d4; margin-bottom: 5px; word-break: break-all;">
                    > [SSCL] KGC侧更新的多项式求值变量 (M_x): {{ step3Data.responseObj.returnedMaterial.kgcMx }}
                  </div>
                </div>
              </div>
            </div>
          </el-card>
        </transition>

        <!-- Step 4: Combine -->
        <transition name="fade-slide">
          <el-card class="glass-card stage-card mt-20" style="border-left: 4px solid #67C23A">
            <template #header>
              <div class="card-header">
                <h3><el-icon><Check /></el-icon> 第三阶段：新轮次公私钥本地生效</h3>
                <el-tag size="small" type="info" effect="dark" v-if="activeStep < 3">等待前置步骤</el-tag>
                <el-tag size="small" type="success" effect="dark" v-else-if="activeStep === 3">待计算</el-tag>
                <el-tag size="small" type="success" effect="dark" v-else>密钥轮换完成！</el-tag>
              </div>
            </template>
            <div class="payload-box">
              <div v-if="activeStep === 3" style="margin-bottom: 20px;">
                <el-button type="success" size="small" @click="runStep4" :loading="isProcessing">第四步：本地数学固化获取 Version+1 绝密凭据</el-button>
              </div>

              <div class="desc" style="color: #a3aab5; margin-bottom: 10px;">基于全新的中心分片与本地绝对隐秘分片，通过椭圆曲线群运算再次获取最新的绝密通道参量：</div>

              <!-- 中间计算过程展示 -->
              <div class="math-steps-box mt-10" style="background: rgba(103,194,58,0.1); padding: 15px; border-radius: 8px; border: 1px dashed rgba(103,194,58,0.4);">
                <div class="label" style="color: #67C23A; font-weight: bold; margin-bottom: 8px;">🔍 揭秘内部计算过程:</div>
                <div v-if="step4Data.mathSteps && step4Data.mathSteps.length > 0">
                  <div v-for="(step, i) in step4Data.mathSteps" :key="i" style="font-family: monospace; font-size: 12px; color: #d4d4d4; margin-bottom: 5px; word-break: break-all;">
                    > {{ step }}
                  </div>
                </div>
                <div v-else style="font-family: monospace; font-size: 12px; color: #666; margin-bottom: 5px;">
                  等待触发计算...
                </div>
              </div>
              
              <div class="flex-box mt-15">
                <div class="item finalize-block final-priv">
                  <div class="title">🔐 新的最终绝对私钥 (Rotation Success)</div>
                  <div class="content break-all">{{ step4Data.PrivateKey || '计算中...' }}</div>
                </div>
                <div class="item finalize-block final-pub">
                  <div class="title">🌍 新的最终公钥 (覆盖原配置)</div>
                  <div class="content break-all">{{ step4Data.PublicKey || '计算中...' }}</div>
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
import { listKeymanage, getComParam, updateKeymanage, addKeymanage } from "@/api/keymanage/keymanage"
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

const form = reactive({ encrytName: 'SM2' }) // Added fallback for dialog
const operationType = ref('update')

const hasStarted = ref(false)
const activeStep = ref(-1)
const isProcessing = ref(false)
const fetchError = ref('')

// Dialog state
const mockGenVisible = ref(false)
const mockGenStep = ref(0)
const isMockProcessing = ref(false)
const mockGenData = reactive({ privateShare: '', uA: '', returnedMaterialPreview: '', fullKeyInfo: null })

const step1Data = reactive({ oldKeyInfo: null })
const step2Data = reactive({ newPrivateShare: '', newUA: '' })
const step3Data = reactive({ payload: null, responseObj: null, snapshotValue: null })
const step4Data = reactive({ PrivateKey: '', PublicKey: '', DA: '', mathSteps: [] })

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
    console.log('使用内置演示用户 test 进行更新过程展示')
  }
})

function initSimulation() {
  hasStarted.value = true
  activeStep.value = 0
  isProcessing.value = false
  fetchError.value = ''
  
  // Clear
  step1Data.oldKeyInfo = null
  step2Data.newPrivateShare = ''
  step2Data.newUA = ''
  step3Data.payload = null
  step3Data.responseObj = null
  step3Data.snapshotValue = null
  step4Data.PrivateKey = ''
  step4Data.PublicKey = ''
  step4Data.mathSteps = []
}

// Dialog Logic
function resetMockGen() {
  mockGenStep.value = 0;
  mockGenData.privateShare = '';
  mockGenData.uA = '';
  mockGenData.returnedMaterialPreview = '';
  mockGenData.fullKeyInfo = null;
}

function runMockGenStep1() {
  isMockProcessing.value = true;
  setTimeout(() => {
    const { publicKey, privateKey } = SM2.generateKeyPair()
    mockGenData.privateShare = privateKey
    mockGenData.uA = publicKey
    mockGenStep.value = 1;
    isMockProcessing.value = false;
  }, 800)
}

async function runMockGenStep2() {
  isMockProcessing.value = true;
  try {
    const payload = {
      userId: sessionUserId, userName: sessionUserName || 'system',
      encrytType: '无证书非对称加密', encrytName: 'SM2',
      keyName: 'Vis-Test-Demo-' + Math.floor(Math.random() * 1000),
      keyUse: '前置构建', autoUpdate: 'false', status: 'Valid',
      uA: mockGenData.uA
    };
    const response = await addKeymanage(payload);
    const snapshot = response.data || payload;
    mockGenData.fullKeyInfo = snapshot;
    let visualValue = snapshot.keyValue;
    try { visualValue = JSON.parse(snapshot.keyValue) } catch(e){}
    mockGenData.returnedMaterialPreview = typeof visualValue === 'object' ? visualValue.partialKey : visualValue;
    mockGenStep.value = 2;
  } catch (err) {
    alert("自动生成测试密钥失败: " + err);
  } finally {
    isMockProcessing.value = false;
  }
}

function runMockGenStep3() {
  // Transfer to Step 1 context
  step1Data.oldKeyInfo = mockGenData.fullKeyInfo;
  activeStep.value = 1;
  mockGenVisible.value = false;
}

async function runStep1() {
  isProcessing.value = true
  fetchError.value = ''
  try {
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
    activeStep.value = 1
  } catch (e) {
    fetchError.value = "检索旧密钥失败: " + e.message
  } finally {
    isProcessing.value = false
  }
}

function runStep2() {
  const { publicKey, privateKey } = SM2.generateKeyPair()
  step2Data.newPrivateShare = privateKey
  step2Data.newUA = publicKey
  activeStep.value = 2
}

async function runStep3() {
  isProcessing.value = true
  fetchError.value = ''
  try {
    const targetKey = step1Data.oldKeyInfo
    const payload = Object.assign({}, targetKey)
    payload.uA = step2Data.newUA
    step3Data.payload = payload

    let responseData = Object.assign({}, targetKey);
    if (targetKey.keyId !== 'MOCK-1') {
      const uRes = await updateKeymanage(payload)
      responseData = uRes.data || payload
    } else {
      let mockKeyVal = JSON.stringify({ partialKey: 'deadbeef', finalPublicKey: 'beefdead' })
      step4Data.mathSteps = ['(MockData) 模拟服务端返回部分私钥: deadbeef']
      responseData.keyValue = mockKeyVal
    }

    let parsedVal = responseData.keyValue;
    try { parsedVal = JSON.parse(responseData.keyValue) } catch(e){}
    
    step3Data.responseObj = {
      action: "Rotation Material Regenerated",
      newKGCVersion: "V" + Math.floor(Math.random() * 100),
      returnedMaterial: parsedVal
    }
    step3Data.snapshotValue = responseData
    activeStep.value = 3
  } catch (err) {
    console.error(err)
    fetchError.value = "向服务器提交更新遭遇异常: " + (err.message || err.msg || err);
  } finally {
    isProcessing.value = false
  }
}

async function runStep4() {
  isProcessing.value = true
  try {
    const targetKey = step1Data.oldKeyInfo
    if (targetKey.keyId !== 'MOCK-1') {
      await performGenDA(step3Data.snapshotValue, step2Data.newPrivateShare, step2Data.newUA)
    } else {
      step4Data.mathSteps.push('(MockData) 本地私密生成熵: ' + step2Data.newPrivateShare)
      step4Data.PrivateKey = "mock-private-key-generation-demo"
      step4Data.PublicKey = "mock-public-key-generation-demo"
    }

    activeStep.value = 4 // Completed
  } catch(e) {
    console.error(e)
    fetchError.value = "计算过程发生破坏抛出异常"
  } finally {
    isProcessing.value = false
  }
}

const N_SM2 = new BigInteger('FFFFFFFEFFFFFFFFFFFFFFFFFFFFFFFF7203DF6B21C6052B53BBF40939D54123', 16)

async function performGenDA(item, userPrivCode, userPubCode) {
  const { xIndex, yIndex, PPub } = await genUAContext(item.encrytType, item.encrytName)
  step4Data.mathSteps = []
  
  if (item.encrytName === "SM2") {
    try {
      const keyValueObj = JSON.parse(item.keyValue)
      step4Data.mathSteps.push(`提取 更新后的KGC服务端分片 T_A: ${keyValueObj.partialKey}`)
      step4Data.mathSteps.push(`提取 本地更新的随机熵分片 u_A: ${userPrivCode}`)
      
      const num1 = new BigInteger(keyValueObj.partialKey, 16)
      const num2 = new BigInteger(userPrivCode, 16)
      step4Data.mathSteps.push(`执行模加: dA = (T_A + u_A) mod N_SM2`)
      const dA = (num1.add(num2)).mod(N_SM2)
      
      step4Data.PrivateKey = leftPad(dA.toString(16), 64)
      step4Data.PublicKey = keyValueObj.finalPublicKey
    } catch (e) {
      step4Data.PrivateKey = "解析返回结果失败"
    }
  } else if (item.encrytName === "SSCL") {
    try {
      const share = JSON.parse(item.keyValue).SSCLKey
      step4Data.mathSteps.push(`提取 更新后的多项式门限响应分片: ${share}`)
      
      const xHex = share.slice(2, 66)
      const yHex = share.slice(66, 130)
      step4Data.mathSteps.push(`拉格朗日门限重建核心秘密 (基于新的Y坐标)`)
      const secret = getSSCLSecret(xIndex, yIndex, xHex, yHex, N_SM2)
      
      const dA = secret.multiply(new BigInteger(xHex, 16)).mod(N_SM2)
      step4Data.mathSteps.push(`代入转换: dA = S_KGC * M_x mod N_SM2`)
      
      const sk = new BigInteger(userPrivCode, 16).add(dA).mod(N_SM2)
      step4Data.mathSteps.push(`计算最新轮次绝对私钥: S_A(new) = (num1 + dA) mod N_SM2`)
      
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
