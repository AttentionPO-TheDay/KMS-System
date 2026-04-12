<template>
  <div class="algorithm-demo-container">
    <div class="page-title">
      <h1>算法图解与演示</h1>
      <p class="subtitle">无证书非对称算法密钥生成流转 - 理论速览与实战演练一一对应</p>
    </div>

    <!-- 顶部统一控制台 -->
    <div class="top-controls">
      <div class="left-controls" style="display: flex; gap: 40px; align-items: center;">
        <el-radio-group v-model="form.encrytName" class="algo-switch" @change="initSimulation">
          <el-radio-button label="SM2">无证书 SM2 算法</el-radio-button>
          <el-radio-button label="SSCL">无证书 SSCL 算法</el-radio-button>
          <el-radio-button label="INTRO">功能实现简述</el-radio-button>
        </el-radio-group>
        
        <div class="test-controls" v-if="form.encrytName !== 'INTRO'">
          <span class="label">测试密钥标签:</span>
          <el-input v-model="form.keyName" placeholder="如：TestKey-1" style="width: 200px" />
        </div>
      </div>
    </div>
    
    <!-- 全局进度条 (置顶) -->
    <el-steps v-if="form.encrytName !== 'INTRO'" :active="activeStep" finish-status="success" align-center class="custom-steps" style="margin-bottom: 30px;">
      <el-step title="第一步" description="本地部分公私钥生成" />
      <el-step title="第二步" description="真实请求" />
      <el-step title="第三步" description="本地恢复" />
      <el-step title="演示完成" />
    </el-steps>

    <!-- 一一对应布局 -->
    <div class="step-by-step-layout" v-if="form.encrytName !== 'INTRO'">
    
      <!-- Step 1 Row -->
      <transition name="fade-slide">
      <div class="step-row" v-show="activeStep >= 0">
        <div class="theory-col">
          <el-card class="glass-card theory-card" :class="{'active-card': activeStep === 0, 'completed-card': activeStep > 0}">
             <div class="card-header">
               <h3 class="theory-title">第一步理论：用户端 (本地部分公私钥生成)</h3>
             </div>
             <div class="theory-content" v-if="form.encrytName === 'SM2'">
                <p>1. 用户端本地生成安全的随机数作为本地部分私钥：u<sub>A</sub> ∈<sub>R</sub> Z<sub>n</sub><sup>*</sup></p>
                <p>2. 在本地基于椭圆曲线计算本地部分公钥：U<sub>A</sub> = u<sub>A</sub> · G</p>
             </div>
             <div class="theory-content" v-else>
                <p>1. 用户端随机产生本地秘密因子：u<sub>A</sub> ∈<sub>R</sub> Z<sub>n</sub><sup>*</sup></p>
                <p>2. 根据椭圆曲线基点计算参数：U<sub>A</sub> = u<sub>A</sub> · G</p>
             </div>
             <div class="dispatch-box">发送公钥切片及标识至 KGC 中心：把 U<sub>A</sub> 与用户标识 ID<sub>A</sub> 捆绑提交</div>
          </el-card>
        </div>
        
        <div class="practice-col">
          <el-card class="glass-card practice-card" :class="{'active-card': activeStep === 0}">
            <div class="card-header">
              <h3><el-icon><User /></el-icon> 客户端实操 - 随机参数与请求载荷构造</h3>
              <el-tag size="small" type="primary" effect="dark" v-if="activeStep === 0">待执行</el-tag>
              <el-tag size="small" type="success" effect="dark" v-else>已完成</el-tag>
            </div>
            <div class="payload-box">
              <div v-if="activeStep === 0" style="margin-bottom: 20px;">
                <el-button type="primary" size="small" @click="runStep1" :loading="isProcessing">第一步：执行并生成本地参数</el-button>
              </div>

              <div class="desc" style="color: #a3aab5; margin-bottom: 10px;">
                本地临时部分私钥（不上传）：
                <span class="inline-code inline-secret">{{ step1Data.privateShare || '等待执行...' }}</span>
              </div>

              <div class="label mt-10">本地生成的切片公钥 (uA):</div>
              <div class="value">{{ step1Data.uA || '等待执行...' }}</div>
              
              <div class="label mt-10" v-if="step1Data.payload">构造将发往服务端 KGC 的载荷:</div>
              <div class="code-block" v-if="step1Data.payload">
                <pre>{{ JSON.stringify(step1Data.payload, null, 2) }}</pre>
              </div>
            </div>
          </el-card>
        </div>
      </div>
      </transition>

      <!-- Step 2 Row -->
      <transition name="fade-slide">
      <div class="step-row" v-if="activeStep >= 1">
        <div class="theory-col">
          <el-card class="glass-card theory-card" :class="{'active-card': activeStep === 1, 'completed-card': activeStep > 1}">
             <div class="card-header">
               <h3 class="theory-title">第二步理论：KGC端 (密码中心运算)</h3>
             </div>
             <div class="theory-content" v-if="form.encrytName === 'SM2'">
                <p>1. 提取标识生成哈希：H<sub>A</sub> = SM3(ENTL || ID<sub>A</sub> || params<sub>sys</sub> || P<sub>pub</sub>)</p>
                <p>2. KGC产生安全的单次随机熵：w ∈<sub>R</sub> Z<sub>n</sub><sup>*</sup></p>
                <p>3. 构建用户部分公钥：W<sub>A</sub> = (w · G) + U<sub>A</sub></p>
                <p>4. 生成公钥哈希：λ = SM3(W<sub>Ax</sub> || W<sub>Ay</sub> || H<sub>A</sub>) mod n</p>
                <p>5. 结合主私钥计算用户部分私钥：T<sub>A</sub> = (w + λ · ms) mod n</p>
             </div>
             <div class="theory-content" v-else>
                <p>1. 解析生成映射哈希：M<sub>x</sub> = SM3(U<sub>Ax</sub> || U<sub>Ay</sub> || ID<sub>A</sub>) mod n</p>
                <p>2. 调用阈值为 t 的多项式求值引擎，该多项式 P(x) 满足 P(0) = ms · r mod n</p>
                <p class="indent">· 动态加载系数向量 coefficients</p>
                <p class="indent">· 计算多项式映射：M<sub>y</sub> = P(M<sub>x</sub>) mod n</p>
             </div>
             <div class="dispatch-box">基于安全通道派发部分公私钥{ WA, TA }至用户</div>
          </el-card>
        </div>
        
        <div class="practice-col">
          <el-card class="glass-card practice-card" :class="{'active-card': activeStep === 1}">
            <div class="card-header">
              <h3><el-icon><Cpu /></el-icon> 服务端实操 - 向 KGC 系统发起交互</h3>
              <el-tag size="small" type="warning" effect="dark" v-if="activeStep === 1">待执行</el-tag>
              <el-tag size="small" type="success" effect="dark" v-else>已完成</el-tag>
            </div>
            <div class="payload-box">
              <div v-if="activeStep === 1" style="margin-bottom: 20px;">
                <el-button type="warning" size="small" @click="runStep2" :loading="isProcessing">第二步：向系统提交并获取服务端分片</el-button>
              </div>
              
              <div v-if="step2Data.responseObj">
                <p style="color:rgba(255,255,255,0.7); font-size:13px; margin-bottom:10px;">网络抓包 - KGC 回传给该用户的碎片报文：</p>
                <div class="code-block response-block">
                  <pre>{{ JSON.stringify(step2Data.responseObj, null, 2) }}</pre>
                </div>

                <div v-if="step2Data.responseObj.returnedMaterial && (step2Data.responseObj.returnedMaterial.kgcRandomW || step2Data.responseObj.returnedMaterial.kgcMx)" class="math-steps-box mt-15" style="background: rgba(230,162,60,0.1); padding: 15px; border-radius: 8px; border: 1px dashed rgba(230,162,60,0.4);">
                  <div class="label" style="color: #E6A23C; font-weight: bold; margin-bottom: 8px;">🔍 KGC 计算黑盒揭秘 (内部中间变量):</div>
                  <div v-if="step2Data.responseObj.returnedMaterial.kgcRandomW">
                    <div class="math-line">> [SM2] KGC临时生成的随机数 (w): {{ step2Data.responseObj.returnedMaterial.kgcRandomW }}</div>
                    <div class="math-line">> [SM2] KGC结合用户信息算出的摘要 (lambda): {{ step2Data.responseObj.returnedMaterial.kgcLambda }}</div>
                  </div>
                  <div v-if="step2Data.responseObj.returnedMaterial.kgcMx">
                    <div class="math-line">> [SSCL] KGC代入多项式的因式 (M_x): {{ step2Data.responseObj.returnedMaterial.kgcMx }}</div>
                  </div>
                </div>
              </div>
            </div>
          </el-card>
        </div>
      </div>
      </transition>

      <!-- Step 3 Row -->
      <transition name="fade-slide">
      <div class="step-row" v-if="activeStep >= 2">
        <div class="theory-col">
          <el-card class="glass-card theory-card" :class="{'active-card': activeStep === 2, 'completed-card': activeStep > 2}">
             <div class="card-header">
               <h3 class="theory-title">第三步理论：用户端 (部分私钥合并)</h3>
             </div>
             <div class="theory-content" v-if="form.encrytName === 'SM2'">
                <p>1. 验证接收到的 { W<sub>A</sub>, T<sub>A</sub> } 的完整性与一致性</p>
                <p>2. 本地执行无中心协议合并：最终实际私钥 S<sub>A</sub> = (T<sub>A</sub> + u<sub>A</sub>) mod n</p>
                <p>3. 最终对外暴露的公开密钥锁定为 W<sub>A</sub></p>
             </div>
             <div class="theory-content" v-else>
                <p>1. 使用秘密共享机制进行切片逆运算</p>
                <p>2. 在无证书环境下还原最终多因子门限私钥</p>
             </div>
             <div class="dispatch-box result">最终获取完整的无证书公私钥对</div>
          </el-card>
        </div>
        
        <div class="practice-col">
          <el-card class="glass-card practice-card" :class="{'active-card': activeStep === 2}">
            <div class="card-header">
              <h3><el-icon><Key /></el-icon> {{ form.encrytName === 'SSCL' ? '用户端实操 - 本地恢复结果' : '用户端实操 - 最终公私钥生成' }}</h3>
              <el-tag size="small" type="success" effect="dark" v-if="activeStep === 2">待计算</el-tag>
              <el-tag size="small" type="success" effect="dark" v-else>拼装成功</el-tag>
            </div>
            <div class="payload-box">
              <div v-if="activeStep === 2" style="margin-bottom: 20px;">
                <el-button type="success" size="small" @click="runStep3" :loading="isProcessing">{{ form.encrytName === 'SSCL' ? '第三步：本地利用拉格朗日恢复' : '第三步：本地利用数学法则算密' }}</el-button>
              </div>

              <div v-if="step3Data.mathSteps.length > 0">
                <div class="math-steps-box mt-10" style="background: rgba(103,194,58,0.1); padding: 15px; border-radius: 8px; border: 1px dashed rgba(103,194,58,0.4);">
                  <div class="label" style="color: #67C23A; font-weight: bold; margin-bottom: 8px;">🔍 揭秘内部计算过程:</div>
                  <div class="math-line" v-for="(step, i) in step3Data.mathSteps" :key="i">> {{ step }}</div>
                </div>
                
                <div class="flex-box mt-15">
                  <div class="item finalize-block final-priv">
                    <div class="title">🔐 最终私钥</div>
                    <div class="content break-all">{{ step3Data.PrivateKey }}</div>
                  </div>
                  <div class="item finalize-block final-pub">
                    <div class="title">🌍 {{ form.encrytName === 'SSCL' ? '最终公钥' : '最终暴露公钥' }}</div>
                    <div class="content break-all">{{ step3Data.PublicKey }}</div>
                  </div>
                </div>
                <div v-if="form.encrytName==='SSCL'" class="mt-15">
                  <div class="label">所属域：<span style="color:#fff">{{ step3Data.keyDomain || step2Data.snapshotValue?.keyDomain || 'A' }}</span></div>
                </div>
              </div>
            </div>
          </el-card>
        </div>
      </div>
      </transition>
      
      <div v-if="fetchError" class="mt-20 desc" style="color: #F56C6C; text-align: center;">{{ fetchError }}</div>
      
    </div>


    <!-- 功能实现简述 布局 -->
    <transition name="fade-slide">
      <div class="principle-cards intro-panel" v-if="form.encrytName === 'INTRO'">
        <!-- Card 1 -->
        <div class="principle-card">
          <div class="card-title"><span class="icon">🔗</span> 多节点密钥协商</div>
          <div class="visual-box">
            <div class="center-node domain-a">生成中心 A</div>
            <div class="user-nodes">
              <div class="user-node u1">💻</div>
              <div class="user-node u2">🖥️</div>
              <div class="user-node u3">📱</div>
            </div>
            <div class="sync-lines-1">
              <div class="line l1"></div>
              <div class="line l2"></div>
              <div class="line l3"></div>
            </div>
          </div>
          <p class="muted card-desc-bottom">简介：同一生成中心掩护下，域内多终端节点共同完成高强度、无证书的密钥协商过程。</p>
        </div>

        <!-- Card 2 -->
        <div class="principle-card">
          <div class="card-title"><span class="icon">🌐</span> 分布式密钥生成</div>
          <div class="visual-box distributed-box">
            <div class="domain-cluster">
              <div class="center-node domain-a sm">域 A</div>
              <div class="orbit"></div>
              <div class="user-dot a1">💻</div>
              <div class="user-dot a2">📱</div>
            </div>
            <div class="domain-cluster">
              <div class="center-node domain-b sm">域 B</div>
              <div class="orbit"></div>
              <div class="user-dot b1">🖥️</div>
              <div class="user-dot b2">💻</div>
            </div>
          </div>
          <p class="muted card-desc-bottom">简介：全网分布式部署，各中心主密钥逻辑隔离。分散的业务终端被安全区隔在独立的密码域中。</p>
        </div>

        <!-- Card 3 -->
        <div class="principle-card">
          <div class="card-title"><span class="icon">🕵️</span> 组间匿名传输</div>
          <div class="visual-box crossing-box">
            <div class="domain-side">
              <div class="domain-label">域 A (发送)</div>
              <div class="user-dot source">💻</div>
            </div>
            
            <div class="transmission-path">
              <div class="obfuscator">混淆代理</div>
              <div class="packet"></div>
              <div class="packet-anonymous">❓</div>
            </div>

            <div class="domain-side">
              <div class="domain-label">域 B (接收)</div>
              <div class="shield">🛡️</div>
            </div>
          </div>
          <p class="muted card-desc-bottom">简介：跨域交互时进行特征剥离与密码学混淆，实现“只知发往某域、不知对应何人”的极致隐私保护。</p>
        </div>
      </div>
    </transition>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { getComParam, addKeymanage } from "@/api/generate/keymanage"
import { getUserProfile } from "@/api/system/user"
import { Monitor, User, Cpu, Key } from '@element-plus/icons-vue'
import { SM2 } from 'gm-crypto'
import { BigInteger } from "jsbn"
import { ec as EC } from 'elliptic'
import BN from 'bn.js'

defineOptions({ name: 'AlgorithmIntegratedView' })

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

// 初始化即停留在步骤 0，移除独立的“开启演练流”按钮
const activeStep = ref(0)
const isProcessing = ref(false)

const step1Data = reactive({ privateShare: '', uA: '', payload: null })
const step2Data = reactive({ responseObj: null, snapshotValue: null })
const fetchError = ref('')
const step3Data = reactive({ PrivateKey: '', PublicKey: '', DA: '', uA: '', keyDomain: '', mathSteps: [] })

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

function initSimulation() {
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
.algorithm-demo-container {
  padding: 24px;
  background-color: transparent;
  min-height: calc(100vh - 84px);
  color: #e5eaf3;
}
.page-title { margin-bottom: 25px; }
.page-title h1 { font-size: 26px; color: #fff; margin: 0 0 8px 0; font-weight: 600; }
.page-title .subtitle { color: rgba(255, 255, 255, 0.5); margin: 0; font-size: 14px; }

/* 顶部控制栏 */
.top-controls {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 30px;
  background: rgba(255, 255, 255, 0.02);
  padding: 15px 24px;
  border-radius: 12px;
  border: 1px solid rgba(255, 255, 255, 0.05);
}

.test-controls {
  display: flex;
  align-items: center;
  gap: 15px;
}

:deep(.el-radio-button__inner) {
  background: rgba(255, 255, 255, 0.05);
  border-color: rgba(255, 255, 255, 0.1);
  color: rgba(255, 255, 255, 0.7);
}
:deep(.el-radio-button__original-radio:checked + .el-radio-button__inner) {
  background-color: #0099ff;
  border-color: #0099ff;
  color: #fff;
  box-shadow: -1px 0 0 0 #0099ff;
}

/* 一一对应布局 */
.step-by-step-layout {
  display: flex;
  flex-direction: column;
  gap: 30px;
}

.step-row {
  display: flex;
  gap: 20px;
  align-items: stretch;
}

.theory-col {
  flex: 0 0 40%;
}

.practice-col {
  flex: 1;
}

/* 理论呈现卡片 */
.glass-card {
  background: rgba(255, 255, 255, 0.02);
  backdrop-filter: blur(24px);
  border: 1px solid rgba(255, 255, 255, 0.05);
  border-radius: 12px;
  color: rgba(255, 255, 255, 0.85);
  transition: all 0.3s ease;
  height: 100%;
}

.glass-card.active-card {
  border-color: #409EFF;
  box-shadow: 0 0 15px rgba(64, 158, 255, 0.3);
  transform: translateY(-2px);
}

.glass-card.completed-card {
  opacity: 0.8;
}

.theory-title {
  margin-top: 0;
  color: #0099ff;
  padding-bottom: 12px;
  margin-bottom: 0px;
  font-size: 16px;
  display: flex;
  align-items: center;
}

.theory-content p {
  line-height: 1.8;
  margin: 12px 0;
  font-family: 'Consolas', 'Monaco', monospace;
  font-size: 13px;
  letter-spacing: 0.5px;
}

.theory-content .indent { padding-left: 20px; color: rgba(255, 255, 255, 0.6); }

.dispatch-box {
  margin-top: 20px;
  padding: 10px 15px;
  background: rgba(0, 153, 255, 0.1);
  border: 1px dashed rgba(0, 153, 255, 0.4);
  border-radius: 6px;
  color: #8fd2ff;
  font-size: 13px;
  font-weight: 500;
}
.dispatch-box.result {
  background: rgba(103, 194, 58, 0.1);
  border-color: rgba(103, 194, 58, 0.4);
  color: #b3e19d;
}

/* 交互舞台属性 */
.custom-steps { max-width: 900px; margin: 0 auto; }
:deep(.el-step__title) { font-weight: bold; color: rgba(255,255,255,0.8); }
:deep(.el-step__description) { color: rgba(255,255,255,0.4); }
:deep(.el-step__head.is-process) { color: #409EFF; border-color: #409EFF; }
:deep(.el-step__title.is-process) { color: #fff; text-shadow: 0 0 8px rgba(64,158,255,0.5); }
:deep(.el-step__title.is-success) { color: #67C23A; }

.fade-slide-enter-active, .fade-slide-leave-active { transition: all 0.5s ease; }
.fade-slide-enter-from { opacity: 0; transform: translateY(15px); }

.card-header { display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid rgba(255, 255, 255, 0.1); padding-bottom:12px; margin-bottom:12px; }
.card-header h3 { margin: 0; font-size: 15px; color: #fff; display: flex; align-items: center; gap: 8px; }
.payload-box { padding: 5px; }

.label { font-size: 13px; color: #a3aab5; margin-bottom: 5px; margin-top: 10px; }
.desc { font-size: 13px; line-height: 1.5; }
.value {
  font-family: 'Consolas', monospace;
  font-size: 12px; background: rgba(0,0,0,0.3); padding: 8px; border-radius: 6px;
  border: 1px solid rgba(255,255,255,0.1); word-break: break-all; color: #409EFF;
}

.inline-code {
  display: inline-block; margin-left: 8px; padding: 2px 8px; border-radius: 4px;
  font-family: 'Consolas', monospace; font-size: 12px; background: rgba(0,0,0,0.28);
  border: 1px solid rgba(255,255,255,0.08); word-break: break-all;
}
.inline-secret { color: #F56C6C; }

.code-block pre {
  font-family: 'Consolas', monospace; font-size: 12px; background: #1e1e1e;
  padding: 10px; border-radius: 6px; color: #d4d4d4; margin: 0; border: 1px solid #333;
  white-space: pre-wrap; word-break: break-all;
}
.response-block pre { color: #E6A23C; border-color: rgba(230, 162, 60, 0.3); }

.math-line { font-family: monospace; font-size: 12px; color: #d4d4d4; margin-bottom: 5px; word-break: break-all; }

.flex-box { display: flex; gap: 15px; flex-wrap: wrap; }
.item.finalize-block {
  flex: 1; min-width: 250px; background: rgba(0,0,0,0.3); padding: 15px; border-radius: 8px; border-top: 3px solid #67C23A;
}
.final-priv { border-color: #F56C6C !important; }
.finalize-block .title { font-weight: bold; font-size: 13px; margin-bottom: 10px; color: #fff; }
.finalize-block .content { font-family: monospace; font-size: 12px; color: #67C23A; line-height: 1.5; }
.final-priv .content { color: #F56C6C; }
.break-all { word-break: break-all; }

/* ----------------------------------
   Feature Principles Styles 
   ----------------------------------*/
.intro-panel {
  padding: 20px;
  background: rgba(255, 255, 255, 0.02);
  border-radius: 16px;
  border: 1px solid rgba(255, 255, 255, 0.05);
}

.principle-cards {
  display: flex;
  gap: 20px;
  align-items: stretch;
}

.principle-card {
  flex: 1;
  display: flex;
  flex-direction: column;
  background: rgba(0, 0, 0, 0.15);
  border-radius: 12px;
  padding: 16px;
  border: 1px solid rgba(255, 255, 255, 0.05);
}

.card-title {
  font-size: 16px;
  font-weight: 500;
  color: #fff;
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 16px;
}

.card-desc-bottom {
  font-size: 13px;
  margin-top: 20px;
  line-height: 1.6;
  color: rgba(255, 255, 255, 0.65);
  text-align: justify;
}

.visual-box {
  flex-grow: 1;
  min-height: 160px;
  background: rgba(0, 0, 0, 0.2);
  border-radius: 12px;
  border: 1px solid rgba(0, 153, 255, 0.1);
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  padding: 10px;
}

/* Common Node Elements */
.center-node {
  padding: 10px 20px;
  border-radius: 16px;
  color: #fff !important;
  font-weight: bold;
  z-index: 2;
  text-align: center;
}
.center-node.sm {
  padding: 6px 12px;
  font-size: 12px;
  border-radius: 10px;
}
.domain-a { 
  background: linear-gradient(135deg, #00e5ff, #0077ff); 
  box-shadow: 0 0 16px rgba(0, 229, 255, 0.5); 
}
.domain-b { 
  background: linear-gradient(135deg, #a855f7, #6366f1); 
  box-shadow: 0 0 16px rgba(168, 85, 247, 0.5); 
}

/* Animation 1: Multi-node Key Agreement */
.user-nodes {
  position: absolute;
  width: 100%;
  height: 100%;
  display: flex;
  justify-content: center;
  align-items: center;
}
.user-node {
  position: absolute;
  font-size: 24px;
  z-index: 3;
}
.u1 { transform: translate(-70px, -50px); }
.u2 { transform: translate(70px, -50px); }
.u3 { transform: translate(0, 70px); }

.sync-lines-1 .line {
  position: absolute;
  background: linear-gradient(90deg, transparent, #00e5ff, transparent);
  height: 2px;
  width: 50px;
  top: 50%;
  left: 50%;
  transform-origin: left center;
  opacity: 0.6;
}
.line.l1 { transform: translate(-50%, -50%) rotate(-143deg) translateX(30px); animation: pulse-line 1.5s infinite; }
.line.l2 { transform: translate(-50%, -50%) rotate(-37deg) translateX(30px); animation: pulse-line 1.5s infinite 0.2s; }
.line.l3 { transform: translate(-50%, -50%) rotate(90deg) translateX(30px); animation: pulse-line 1.5s infinite 0.4s; }

@keyframes pulse-line {
  0% { transform: translate(-50%, -50%) var(--r) translateX(40px) scaleX(0.5); opacity: 0; }
  50% { opacity: 1; }
  100% { transform: translate(-50%, -50%) var(--r) translateX(20px) scaleX(1); opacity: 0; }
}
.l1 { --r: rotate(-143deg); }
.l2 { --r: rotate(-37deg); }
.l3 { --r: rotate(90deg); }

/* Animation 2: Distributed Concept */
.distributed-box {
  flex-direction: row;
  justify-content: space-around;
  gap: 10px;
}
.domain-cluster {
  position: relative;
  display: flex;
  justify-content: center;
  align-items: center;
  width: 90px;
  height: 90px;
}
.orbit {
  position: absolute;
  width: 90px;
  height: 90px;
  border-radius: 50%;
  border: 1px dashed rgba(255, 255, 255, 0.2);
  animation: spin 10s linear infinite;
}
.user-dot {
  position: absolute;
  font-size: 16px;
}
.a1 { transform: rotate(0deg) translateX(45px) rotate(0deg); }
.a2 { transform: rotate(180deg) translateX(45px) rotate(-180deg); }
.b1 { transform: rotate(90deg) translateX(45px) rotate(-90deg); }
.b2 { transform: rotate(270deg) translateX(45px) rotate(-270deg); }
@keyframes spin { 100% { transform: rotate(360deg); } }

/* Animation 3: Cross-domain Anonymous */
.crossing-box {
  justify-content: space-between;
}
.domain-side {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  z-index: 2;
}
.domain-label {
  font-size: 12px;
  color: #bae6fd;
  border: 1px solid rgba(186, 230, 253, 0.2);
  padding: 4px 8px;
  border-radius: 8px;
  background: rgba(0, 0, 0, 0.3);
}
.source {
  font-size: 28px;
}
.shield {
  font-size: 28px;
  filter: drop-shadow(0 0 10px #6366f1);
}
.transmission-path {
  position: absolute;
  left: 28%;
  right: 28%;
  height: 2px;
  background: rgba(255, 255, 255, 0.1);
  display: flex;
  align-items: center;
  justify-content: center;
}
.obfuscator {
  position: absolute;
  padding: 4px 10px;
  background: rgba(255, 255, 255, 0.1);
  backdrop-filter: blur(8px);
  border: 1px solid rgba(255, 255, 255, 0.2);
  border-radius: 8px;
  font-size: 12px;
  color: #fff;
  z-index: 3;
}
.packet, .packet-anonymous {
  position: absolute;
  left: 0;
  top: -8px;
  width: 16px;
  height: 16px;
  display: flex;
  align-items: center;
  justify-content: center;
}
.packet::after {
  content: '';
  width: 8px;
  height: 8px;
  background: #00e5ff;
  border-radius: 50%;
  box-shadow: 0 0 10px #00e5ff;
}
.packet {
  animation: travel-first 3s infinite linear;
}
.packet-anonymous {
  animation: travel-second 3s infinite linear;
  opacity: 0;
  font-size: 14px;
}
@keyframes travel-first {
  0% { left: 0; opacity: 1; }
  45% { left: 45%; opacity: 1; }
  50% { left: 50%; opacity: 0; }
  100% { left: 50%; opacity: 0; }
}
@keyframes travel-second {
  0% { left: 50%; opacity: 0; }
  50% { left: 50%; opacity: 0; }
  55% { left: 55%; opacity: 1; }
  100% { left: 100%; opacity: 1; }
}
</style>
