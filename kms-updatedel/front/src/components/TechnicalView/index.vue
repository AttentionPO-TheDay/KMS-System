<template>
  <el-collapse class="technical-view">
    <el-collapse-item name="technical" title="技术图解">
      <template v-if="kind === 'preallocation'">
        <div class="technical-label">基于格的密钥预分配</div>
        <ol class="technical-flow" aria-label="密钥预分配流程">
          <li v-for="step in ['通信授权', '本地生成', 'Kyber 封装', 'Falcon 签名', '保护包入池', '会话取用']" :key="step">{{ step }}</li>
        </ol>
        <div class="technical-label">计算结构</div>
        <dl class="technical-terms">
          <dt>并行抽样短向量</dt><dd>独立抽样任务 · 并行计算</dd>
          <dt>离线生成格陷门</dt><dd>预计算阶段 · 格参数准备</dd>
          <dt>快速委派格基向量</dt><dd>主格基 · 节点委派 · 参数绑定</dd>
        </dl>
      </template>
      <template v-else-if="kind === 'update'">
        <div class="technical-label">密钥版本更新</div>
        <ol class="technical-flow" aria-label="密钥更新流程">
          <li v-for="step in ['本地新版本', '封存与自检', '公钥登记', '版本切换', '一致性检查']" :key="step">{{ step }}</li>
        </ol>
        <div class="technical-label">树型结构与并行编程</div>
        <div class="technical-tree" role="img" aria-label="树型组织图：根批次分为两个子组，每个子组含独立任务">
          <div class="tree-root">根批次</div>
          <div class="tree-branches">
            <div v-for="group in ['A', 'B']" :key="group" class="tree-group">
              <span>子组 {{ group }}</span><div class="tree-leaves"><span>独立任务</span><span>独立任务</span></div>
            </div>
          </div>
        </div>
        <dl class="technical-terms">
          <dt>多线程 / 并行更新</dt><dd>独立任务并行 · 同一密钥按版本排序</dd>
          <dt>分布式一致性检查</dt><dd>版本 · 公钥摘要 · 生产记录</dd>
          <dt>半诚实安全模型</dt><dd>按协议执行 · 保护参与方秘密</dd>
          <dt>可证安全目标</dt><dd>机密性 · 完整性 · 版本绑定</dd>
        </dl>
      </template>
      <template v-else>
        <div class="technical-label">密钥分发保护</div>
        <ol class="technical-flow" aria-label="密钥分发流程">
          <li v-for="step in ['选择对端', '通信授权', '密钥版本绑定', '封装与签名', '验签与解封']" :key="step">{{ step }}</li>
        </ol>
        <div class="technical-label">安全技术要点</div>
        <dl class="technical-terms">
          <dt>抗量子计算攻击</dt><dd>格密码 · Kyber 密钥封装 · Falcon 签名</dd>
          <dt>安全数据匿名传输</dt><dd>身份隐私 · 元数据最小化</dd>
          <dt>差分隐私数据保护</dt><dd>统计数据 · 隐私预算 ε / δ · 噪声机制</dd>
          <dt>抗侧信道攻击</dt><dd>恒定时间 · 掩码 · 敏感材料隔离</dd>
        </dl>
      </template>
    </el-collapse-item>
  </el-collapse>
</template>

<script setup>
// Pure explanatory graphics. No API, timer, crypto operation or execution status.
defineProps({ kind: { type: String, required: true } })
</script>

<style scoped>
.technical-view { margin: 16px 0; }
.technical-label { font-size: 13px; font-weight: 600; margin: 12px 0; color: var(--kms-text-primary); }
.technical-flow { display: flex; flex-wrap: wrap; gap: 8px; padding: 0; list-style: none; counter-reset: steps; }
.technical-flow li { counter-increment: steps; padding: 8px 12px; border: 1px solid var(--el-border-color); border-radius: 4px; }
.technical-flow li::before { content: counter(steps) ' / '; color: var(--kms-text-secondary); font-variant-numeric: tabular-nums; }
.technical-terms { display: grid; grid-template-columns: minmax(140px, 200px) 1fr; font-size: 13px; margin: 0; }
.technical-terms dt, .technical-terms dd { border-bottom: 1px solid var(--el-border-color-lighter); padding: 10px 0; margin: 0; }
.technical-terms dd { color: var(--kms-text-secondary); }
.technical-tree { max-width: 520px; text-align: center; margin: 16px 0; }
.tree-root { display: inline-block; padding: 6px 24px; border: 1px solid var(--el-border-color); border-radius: 4px; }
.tree-branches { display: flex; gap: 24px; margin-top: 12px; }
.tree-group { flex: 1; padding-top: 10px; border-top: 1px solid var(--el-border-color); }
.tree-leaves { display: flex; gap: 8px; margin-top: 10px; }
.tree-leaves span { flex: 1; padding: 6px; background: var(--el-fill-color-light); border-radius: 4px; font-size: 12px; }
@media (max-width: 600px) { .technical-terms { grid-template-columns: 1fr; } .technical-terms dt { border-bottom: 0; padding-bottom: 0; } .technical-terms dd { padding-top: 4px; } }
</style>
