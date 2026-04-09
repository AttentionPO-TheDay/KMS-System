<template>
  <div class="algorithm-container">
    <div class="page-title">
      <h1>生成算法速览</h1>
      <p class="subtitle">SM2 与 SSCL 无证书算法密钥生成全流程</p>
    </div>

    <!-- Algorithm Switch -->
    <el-radio-group v-model="activeAlgo" class="algo-switch">
      <el-radio-button label="sm2">无证书 SM2 算法</el-radio-button>
      <el-radio-button label="sscl">无证书 SSCL 算法</el-radio-button>
    </el-radio-group>

    <div v-if="activeAlgo === 'sm2'" class="timeline-container">
      <el-timeline>
        <el-timeline-item center timestamp="第一步：用户端 (协参数生成)" placement="top" type="primary" size="large">
          <el-card class="glass-card">
            <h3>生成用户侧部分请求参量</h3>
            <p>1. 用户端本地生成安全的随机数作为隐秘熵：u<sub>A</sub> ∈<sub>R</sub> Z<sub>n</sub><sup>*</sup></p>
            <p>2. 在本地基于椭圆曲线计算锚点：U<sub>A</sub> = u<sub>A</sub> · G</p>
            <div class="dispatch-box">发送公钥切片及标识至 KGC 中心：把 U<sub>A</sub> 与用户标识 ID<sub>A</sub> 捆绑提交</div>
          </el-card>
        </el-timeline-item>

        <el-timeline-item center timestamp="第二步：KGC端 (密码中心运算)" placement="top" type="warning" size="large">
          <el-card class="glass-card">
            <h3>提取认证并生成部分公私钥</h3>
            <p>1. 提取标识生成主防伪哈希：H<sub>A</sub> = SM3(ENTL || ID<sub>A</sub> || params<sub>sys</sub> || P<sub>pub</sub>)</p>
            <p>2. KGC产生安全的单次随机熵：w ∈<sub>R</sub> Z<sub>n</sub><sup>*</sup></p>
            <p>3. 构建用户最终公钥：W<sub>A</sub> = (w · G) + U<sub>A</sub></p>
            <p>4. 生成公钥防抵赖哈希：λ = SM3(W<sub>Ax</sub> || W<sub>Ay</sub> || H<sub>A</sub>) mod n</p>
            <p>5. 结合主私钥(ms)计算KGC侧负责的半部私钥：T<sub>A</sub> = (w + λ · ms) mod n</p>
            <div class="dispatch-box">基于安全通道派发密钥物质至用户：{ W<sub>A</sub>, T<sub>A</sub> }</div>
          </el-card>
        </el-timeline-item>

        <el-timeline-item center timestamp="第三步：用户端 (私钥拼图)" placement="top" type="success" size="large">
          <el-card class="glass-card">
            <h3>组合并固化最终公私钥对</h3>
            <p>1. 验证接收到的 { W<sub>A</sub>, T<sub>A</sub> } 的完整性与一致性</p>
            <p>2. 本地执行无中心协议合并：最终实际私钥 S<sub>A</sub> = (T<sub>A</sub> + u<sub>A</sub>) mod n</p>
            <p>3. 最终对外暴露的公开密钥锁定为 W<sub>A</sub></p>
            <div class="dispatch-box result">最终获取完整的无证书公私钥对：公钥 W<sub>A</sub> , 私钥 S<sub>A</sub> (KGC不可知)</div>
          </el-card>
        </el-timeline-item>
      </el-timeline>
    </div>

    <div v-else class="timeline-container">
      <el-timeline>
        <el-timeline-item center timestamp="第一步：用户端 (协参数生成)" placement="top" type="primary" size="large">
          <el-card class="glass-card">
            <h3>生成用户侧部分请求参量</h3>
            <p>1. 用户端随机产生本地秘密因子：u<sub>A</sub> ∈<sub>R</sub> Z<sub>n</sub><sup>*</sup></p>
            <p>2. 根据椭圆曲线基点计算参数：U<sub>A</sub> = u<sub>A</sub> · G</p>
            <div class="dispatch-box">发送切片请求至 KGC 中心：上传 U<sub>A</sub> 与身份 ID<sub>A</sub></div>
          </el-card>
        </el-timeline-item>

        <el-timeline-item center timestamp="第二步：KGC端 (密码中心运算)" placement="top" type="warning" size="large">
          <el-card class="glass-card">
            <h3>基于门限的系统秘密分发</h3>
            <p>1. 解析生成映射哈希：M<sub>x</sub> = SM3(U<sub>Ax</sub> || U<sub>Ay</sub> || ID<sub>A</sub>) mod n</p>
            <p>2. 调用阈值为 t 的多项式求值引擎，该多项式 P(x) 满足 P(0) = ms · r mod n</p>
            <p class="indent">· 动态加载系数向量 coefficients</p>
            <p class="indent">· 计算多项式映射：M<sub>y</sub> = P(M<sub>x</sub>) mod n</p>
            <div class="dispatch-box">将多项式生成的影子切片派发给用户：{ M<sub>x</sub>, M<sub>y</sub> }</div>
          </el-card>
        </el-timeline-item>

        <el-timeline-item center timestamp="第三步：用户端 (私钥拼图)" placement="top" type="success" size="large">
          <el-card class="glass-card">
            <h3>拉格朗日组装与最终化</h3>
            <p>1. 使用秘密共享机制进行切片逆运算并结合自身 u<sub>A</sub></p>
            <p>2. 在无需依赖证书环境的条件下还原最终多因子门限私钥</p>
            <div class="dispatch-box result">完成 SSCL 联邦多参并入：建立多级阈值防篡改的安全载体</div>
          </el-card>
        </el-timeline-item>
      </el-timeline>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'

const activeAlgo = ref('sm2')
</script>

<style scoped>
.algorithm-container {
  padding: 24px;
  background-color: transparent;
  min-height: calc(100vh - 84px);
}

.page-title {
  margin-bottom: 30px;
}

.page-title h1 {
  font-size: 28px;
  color: #fff;
  margin: 0 0 8px 0;
  font-weight: 600;
  letter-spacing: 1px;
}

.page-title .subtitle {
  color: rgba(255, 255, 255, 0.5);
  margin: 0;
  font-size: 14px;
}

.algo-switch {
  margin-bottom: 40px;
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

.timeline-container {
  max-width: 900px;
}

.glass-card {
  background: rgba(255, 255, 255, 0.02);
  backdrop-filter: blur(24px);
  border: 1px solid rgba(255, 255, 255, 0.05);
  border-radius: 12px;
  color: rgba(255, 255, 255, 0.85);
  transition: all 0.3s ease;
}

.glass-card:hover {
  border-color: rgba(255, 255, 255, 0.15);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.2);
}

.glass-card h3 {
  margin-top: 0;
  color: #fff;
  border-bottom: 1px solid rgba(255, 255, 255, 0.1);
  padding-bottom: 12px;
  margin-bottom: 16px;
  font-size: 18px;
  display: flex;
  align-items: center;
}

.glass-card h3::before {
  content: '';
  display: inline-block;
  width: 4px;
  height: 16px;
  background: #0099ff;
  border-radius: 2px;
  margin-right: 10px;
}

.glass-card p {
  line-height: 2;
  margin: 10px 0;
  font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
  font-size: 15px;
  letter-spacing: 0.5px;
}

.glass-card .indent {
  padding-left: 20px;
  color: rgba(255, 255, 255, 0.6);
}

.dispatch-box {
  margin-top: 24px;
  padding: 14px 20px;
  background: rgba(0, 153, 255, 0.1);
  border: 1px dashed rgba(0, 153, 255, 0.4);
  border-radius: 8px;
  color: #8fd2ff;
  font-size: 15px;
  font-weight: 500;
  display: flex;
  align-items: center;
}

.dispatch-box::before {
  content: '▶';
  margin-right: 8px;
  font-size: 12px;
  color: #0099ff;
}

.dispatch-box.result {
  background: rgba(103, 194, 58, 0.1);
  border-color: rgba(103, 194, 58, 0.4);
  color: #b3e19d;
}

.dispatch-box.result::before {
  color: #67c23a;
}

:deep(.el-timeline-item__timestamp) {
  color: rgba(255, 255, 255, 0.8) !important;
  font-size: 16px !important;
  font-weight: 600;
  margin-bottom: 12px;
}

:deep(.el-card) {
  border: none;
}
</style>
