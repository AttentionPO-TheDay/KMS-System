<template>
  <div class="algorithm-container">
    <div class="page-title">
      <h1>更新与回收算法速览</h1>
      <p class="subtitle">无证书双轨演进模型 (SM2 / SSCL) 的密钥轮换与生命周期终止机制</p>
    </div>

    <!-- Algorithm Switch -->
    <el-radio-group v-model="activeAlgo" class="algo-switch">
      <el-radio-button label="sm2">无证书 SM2 更新/回收</el-radio-button>
      <el-radio-button label="sscl">无证书 SSCL 更新/回收</el-radio-button>
    </el-radio-group>

    <template v-if="activeAlgo === 'sm2'">
      <el-row :gutter="24">
        <!-- SM2 全量更新 -->
        <el-col :span="12">
          <div class="glass-card mode-card">
            <h3 class="title-full">全量化密钥更新 (Full-quantity)</h3>
            <div class="mode-desc">双边防伪参数重置，彻底阻断历史妥协风险。</div>
            <div class="step-list">
              <div class="step-item">
                <div class="step-label">用户配合 (User)</div>
                <div class="step-math">
                  u<sub>A</sub><sup>(new)</sup> ∈<sub>R</sub> Z<sub>n</sub><sup>*</sup><br />
                  U<sub>A</sub><sup>(new)</sup> = u<sub>A</sub><sup>(new)</sup> · G
                </div>
              </div>
              <div class="step-item">
                <div class="step-label">KGC 重算 (KGC)</div>
                <div class="step-math">
                  H<sub>A</sub> = SM3(ENTL || ID<sub>A</sub> || params || P<sub>pub</sub>)<br />
                  W<sub>A</sub><sup>(new)</sup> = (w<sup>(new)</sup> · G) + U<sub>A</sub><sup>(new)</sup><br />
                  λ<sup>(new)</sup> = SM3(W<sub>Ax</sub><sup>(new)</sup> || W<sub>Ay</sub><sup>(new)</sup> || H<sub>A</sub>) mod n<br />
                  T<sub>A</sub><sup>(new)</sup> = (w<sup>(new)</sup> + λ<sup>(new)</sup> · ms) mod n
                </div>
              </div>
            </div>
            <div class="dispatch-box">用户端接收部分公私钥：{ W<sub>A</sub><sup>(new)</sup>, T<sub>A</sub><sup>(new)</sup> }</div>
          </div>
        </el-col>

        <!-- SM2 轻量更新 -->
        <el-col :span="12">
          <div class="glass-card mode-card">
            <h3 class="title-light">轻量化密钥更新 (Semi-quantity)</h3>
            <div class="mode-desc">KGC 单边注入新随机熵，无须用户端进行强交互。</div>
            <div class="step-list">
              <div class="step-item">
                <div class="step-label">单边派发 (KGC)</div>
                <div class="step-math">
                  w<sub>new</sub> ∈<sub>R</sub> Z<sub>n</sub><sup>*</sup><br />
                  W<sub>A</sub><sup>(i+1)</sup> = (w<sub>new</sub> · G) + U<sub>A</sub><sup>(old)</sup> <i>(复用防抵赖参数)</i><br />
                  λ<sup>(i+1)</sup> = SM3(W<sub>Ax</sub><sup>(i+1)</sup> || W<sub>Ay</sub><sup>(i+1)</sup> || H<sub>A</sub>) mod n<br />
                  T<sub>A</sub><sup>(i+1)</sup> = (w<sub>new</sub> + λ<sup>(i+1)</sup> · ms) mod n
                </div>
              </div>
              <div class="step-item">
                <div class="step-label">无感同步 (User)</div>
                <div class="step-math">
                  <i>静默接收服务端下发的新周期因子</i><br />
                  S<sub>A</sub><sup>(i+1)</sup> = (T<sub>A</sub><sup>(i+1)</sup> + u<sub>A</sub><sup>(old)</sup>) mod n
                </div>
              </div>
            </div>
            <div class="dispatch-box light">用户端接收部分公私钥：{ W<sub>A</sub><sup>(i+1)</sup>, T<sub>A</sub><sup>(i+1)</sup> }</div>
          </div>
        </el-col>
      </el-row>
    </template>

    <template v-else>
      <el-row :gutter="24">
        <!-- SSCL 全量更新 -->
        <el-col :span="12">
          <div class="glass-card mode-card">
            <h3 class="title-full">全量化密钥更新 (Full-quantity)</h3>
            <div class="mode-desc">门限多项式系数与随机盲化因子完全重建。</div>
            <div class="step-list">
              <div class="step-item">
                <div class="step-label">用户重载 (User)</div>
                <div class="step-math">
                  U<sub>A</sub><sup>(new)</sup> = u<sub>A</sub><sup>(new)</sup> · G<br />
                  M<sub>x</sub><sup>(new)</sup> = SM3(U<sub>Ax</sub><sup>(new)</sup> || U<sub>Ay</sub><sup>(new)</sup> || ID<sub>A</sub>) mod n
                </div>
              </div>
              <div class="step-item">
                <div class="step-label">多项式切割 (KGC)</div>
                <div class="step-math">
                  r<sup>(new)</sup> ∈<sub>R</sub> Z<sub>n</sub><sup>*</sup> <i>(全新门限扰动)</i><br />
                  c<sub>0</sub><sup>(new)</sup> = (ms · r<sup>(new)</sup>) mod n<br />
                  P<sub>new</sub>(x) = c<sub>0</sub><sup>(new)</sup> + Σ c<sub>i</sub> · x<sup>i</sup> mod n<br />
                  M<sub>y</sub><sup>(new)</sup> = P<sub>new</sub>(M<sub>x</sub><sup>(new)</sup>) mod n
                </div>
              </div>
            </div>
            <div class="dispatch-box">用户端接收部分公私钥：{ M<sub>x</sub><sup>(new)</sup>, M<sub>y</sub><sup>(new)</sup> }</div>
          </div>
        </el-col>

        <!-- SSCL 轻量更新 -->
        <el-col :span="12">
          <div class="glass-card mode-card">
            <h3 class="title-light">轻量化密钥更新 (Semi-quantity)</h3>
            <div class="mode-desc">固定结构锚点下的静默多项式常数变轨。</div>
            <div class="step-list">
              <div class="step-item">
                <div class="step-label">切片翻转 (KGC)</div>
                <div class="step-math">
                  r<sub>new</sub> ∈<sub>R</sub> Z<sub>n</sub><sup>*</sup> <i>(新截距盲化因子)</i><br />
                  c<sub>0</sub><sup>(i+1)</sup> = (ms · r<sub>new</sub>) mod n<br />
                  P<sub>new</sub>(x) = c<sub>0</sub><sup>(i+1)</sup> + Σ c<sub>j</sub><sup>(new)</sup> · x<sup>j</sup> mod n<br />
                  M<sub>y</sub><sup>(i+1)</sup> = P<sub>new</sub>(M<sub>x</sub><sup>(old)</sup>) mod n
                </div>
              </div>
              <div class="step-item">
                <div class="step-label">隐式汇聚 (User)</div>
                <div class="step-math">
                  <i>复用本地的 M<sub>x</sub><sup>(old)</sup> 不做额外运算开销。</i><br />
                  无缝接入新门限轮次并生成映射。
                </div>
              </div>
            </div>
            <div class="dispatch-box light">用户端接收部分公私钥：{ M<sub>x</sub><sup>(old)</sup>, M<sub>y</sub><sup>(i+1)</sup> }</div>
          </div>
        </el-col>
      </el-row>
    </template>

    <!-- 回收公约机制 -->
    <div class="glass-card revoke-card">
      <h3 class="revoke-title">无证书联邦注销与生命周期终止 (Revocation)</h3>
      <div class="revoke-flow">
        <div class="revoke-step">
          <div class="r-icon">🚫</div>
          <div class="r-text">
            <strong>1. 权限锚点剔除 (KGC-Side)</strong>
            <span>在 KGC 中心层级物理阻断关联 ID 的部分密钥派生权限，拒绝全部协同计算签名。</span>
          </div>
        </div>
        <div class="revoke-step divider">➔</div>
        <div class="revoke-step">
          <div class="r-icon">⛓️</div>
          <div class="r-text">
            <strong>2. 联邦链上止付 (Consensus)</strong>
            <span>针对无证书体制发出全局状态机废止广播，上链写入非溯源 CRL 与全网共识。</span>
          </div>
        </div>
        <div class="revoke-step divider">➔</div>
        <div class="revoke-step">
          <div class="r-icon">🛡️</div>
          <div class="r-text">
            <strong>3. 本地静默化 (User-Side)</strong>
            <span>本地已生成的 u<sub>A</sub> 无法与 KGC 完成协同，实现防篡改和绝对阻断控制。</span>
          </div>
        </div>
      </div>
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
  color: var(--kms-text-primary);
}

.page-title {
  margin-bottom: 30px;
}

.page-title h1 {
  font-size: 28px;
  color: var(--kms-text-primary);
  margin: 0 0 8px 0;
  font-weight: 600;
  letter-spacing: 1px;
}

.page-title .subtitle {
  color: var(--kms-text-tertiary);
  margin: 0;
  font-size: 14px;
}

.algo-switch {
  margin-bottom: 30px;
}

:deep(.el-radio-button__inner) {
  background: var(--kms-surface-3);
  border-color: var(--kms-border);
  color: var(--kms-text-secondary);
}

:deep(.el-radio-button__original-radio:checked + .el-radio-button__inner) {
  background-color: var(--kms-brand-fill);
  border-color: var(--kms-brand);
  color: var(--kms-text-primary);
  box-shadow: -1px 0 0 0 var(--kms-brand);
}

.glass-card {
  background: var(--kms-surface-1);
  backdrop-filter: blur(24px);
  border: 1px solid var(--kms-surface-3);
  border-radius: 12px;
  padding: 24px;
  margin-bottom: 24px;
  transition: all 0.3s ease;
}

.glass-card:hover {
  border-color: var(--kms-border-strong);
  box-shadow: 0 8px 24px var(--kms-shadow);
}

.mode-card h3 {
  margin-top: 0;
  padding-bottom: 12px;
  margin-bottom: 10px;
  font-size: 18px;
  display: flex;
  align-items: center;
  border-bottom: 1px solid var(--kms-surface-3);
}

.mode-card h3.title-full::before {
  content: '';
  display: inline-block;
  width: 4px;
  height: 16px;
  background: var(--kms-danger);
  border-radius: 2px;
  margin-right: 10px;
}

.mode-card h3.title-light::before {
  content: '';
  display: inline-block;
  width: 4px;
  height: 16px;
  background: var(--kms-success);
  border-radius: 2px;
  margin-right: 10px;
}

.mode-desc {
  font-size: 13px;
  color: var(--kms-text-tertiary);
  margin-bottom: 20px;
}

.step-list {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.step-item {
  display: flex;
  flex-direction: column;
}

.step-label {
  font-size: 13px;
  font-weight: bold;
  color: var(--kms-text-tertiary);
  margin-bottom: 8px;
  display: inline-block;
  padding: 2px 8px;
  background: var(--kms-surface-3);
  border-radius: 4px;
  align-self: flex-start;
}

.step-math {
  font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
  font-size: 14px;
  line-height: 1.8;
  color: var(--kms-text-secondary);
  background: var(--kms-shadow);
  padding: 12px 16px;
  border-radius: 6px;
  border-left: 3px solid var(--kms-brand-border);
}

.step-math i {
  color: var(--kms-text-tertiary);
  font-style: normal;
  font-size: 13px;
}

.dispatch-box {
  margin-top: 24px;
  padding: 14px;
  background: var(--kms-danger-subtle);
  border: 1px dashed var(--kms-danger-border);
  border-radius: 8px;
  color: var(--kms-danger-strong);
  font-size: 15px;
  font-weight: 500;
  text-align: center;
}

.dispatch-box.light {
  background: var(--kms-success-subtle);
  border-color: var(--kms-success-border);
  color: var(--kms-success-strong);
}

/* 回收部分 */
.revoke-card {
  margin-top: 10px;
  background: linear-gradient(135deg, var(--kms-surface-1), var(--kms-surface-2));
  border: 1px solid var(--kms-danger-border);
}

.revoke-title {
  margin-top: 0;
  color: var(--kms-danger-strong);
  font-size: 18px;
  margin-bottom: 20px;
  display: flex;
  align-items: center;
}

.revoke-title::before {
  content: '';
  display: inline-block;
  width: 4px;
  height: 16px;
  background: var(--kms-danger);
  border-radius: 2px;
  margin-right: 10px;
}

.revoke-flow {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.revoke-step {
  display: flex;
  align-items: flex-start;
  flex: 1;
  padding: 0 10px;
}

.r-icon {
  font-size: 28px;
  margin-right: 15px;
  margin-top: 3px;
}

.r-text {
  display: flex;
  flex-direction: column;
}

.r-text strong {
  font-size: 15px;
  color: var(--kms-text-primary);
  margin-bottom: 6px;
}

.r-text span {
  font-size: 13px;
  color: var(--kms-text-tertiary);
  line-height: 1.5;
}

.revoke-step.divider {
  flex: 0 0 40px;
  justify-content: center;
  font-size: 24px;
  color: var(--kms-border);
}
</style>
