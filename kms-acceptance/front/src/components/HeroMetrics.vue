<template>
  <section class="hero-metrics">
    <div class="hero-content">
      <div class="brand">
        <span class="pulsing-dot"></span>
        <p class="eyebrow">ACCEPTANCE ENV</p>
      </div>
      <h1 class="gradient-text">测试系统</h1>
      <p class="hero-copy">
        独立前后端的测试系统，用于执行 <code>wrk</code> 压测、汇总 TPS 指标，并支撑联调验证与回收率判定。
      </p>
    </div>
    
    <div class="hero-cards">
      <article class="stat-card" style="--accent-hue: 160">
        <div class="stat-icon" aria-hidden="true"></div>
        <div class="stat-info">
          <span>压测场景总数</span>
          <strong>{{ scenarios.length }}</strong>
        </div>
      </article>
      <article class="stat-card" style="--accent-hue: 210">
        <div class="stat-icon" aria-hidden="true"></div>
        <div class="stat-info">
          <span>历史压测轮次</span>
          <strong>{{ runs.length }}</strong>
        </div>
      </article>
      <article class="stat-card" style="--accent-hue: 280">
        <div class="stat-icon" aria-hidden="true"></div>
        <div class="stat-info">
          <span>用例通过率</span>
          <strong>{{ passRate }}%</strong>
        </div>
      </article>
    </div>
  </section>
</template>

<script setup>
import { computed } from 'vue'
import { scenarios, runs, passCount } from '../store'

const passRate = computed(() => {
  if (runs.value.length === 0) return 0
  return Math.round((passCount.value / runs.value.length) * 100)
})
</script>

<style scoped>
.hero-metrics {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 40px;
  margin-bottom: 40px;
  align-items: center;
}
.brand {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 16px;
}
/* 状态指示点：原实现带双层霓虹发光（0 0 10px + 0 0 20px），
   属于暗色科技风残留，浅色企业级风格下改为克制的实心点。 */
.pulsing-dot {
  width: 8px;
  height: 8px;
  background-color: var(--kms-brand-fill);
  border-radius: 50%;
  flex-shrink: 0;
}
.eyebrow {
  color: var(--kms-brand-text);
  letter-spacing: 0.2em;
  font-size: 11px;
  font-weight: 700;
  margin: 0;
}
/* 原标题使用渐变文字（background-clip: text + text-fill-color: transparent）。
   浅色风格下取消渐变，必须同时移除 text-fill-color，否则文字会完全不可见。 */
/* 主标题：原为 clamp(36px,5vw,56px) + font-weight 800 的展示型大标题，
   在后台工具中过于张扬（单屏被标题占据过多），收敛为常规页面标题尺度。 */
.gradient-text {
  font-size: clamp(24px, 2.6vw, 32px);
  font-weight: var(--kms-font-weight-semibold);
  letter-spacing: var(--kms-letter-spacing-tight);
  margin: 0 0 var(--kms-space-3) 0;
  color: var(--kms-text-primary);
  line-height: var(--kms-line-height-tight);
}
.hero-copy {
  color: var(--kms-text-tertiary);
  line-height: 1.8;
  font-size: 16px;
  max-width: 500px;
}

.hero-cards {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 20px;
}
.hero-cards .stat-card:first-child {
  grid-column: span 2;
}
.stat-card {
  display: flex;
  align-items: center;
  gap: 20px;
  padding: 24px;
}
/* 指标图标位。
   原实现为 `background: hsl(var(--accent-hue) 80% 50% / 0.1)`，
   但 --accent-hue 在整个工程中从未定义 → 无效 CSS，背景始终未渲染，
   此前靠 emoji 字符撑起视觉。emoji 移除后改为令牌配色 + CSS 绘制的标记。 */
.stat-icon {
  position: relative;
  background: var(--kms-brand-subtle);
  width: 48px;
  height: 48px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--kms-radius);
  flex-shrink: 0;
}
.stat-icon::before {
  content: '';
  width: 14px;
  height: 14px;
  border-radius: 3px;
  border: 2px solid var(--kms-brand-text);
}
.stat-info {
  display: flex;
  flex-direction: column;
}
.stat-info span {
  font-size: 12px;
  color: var(--kms-text-tertiary);
  text-transform: uppercase;
  letter-spacing: 1px;
}
.stat-info strong {
  font-size: 32px;
  font-weight: 700;
  color: var(--kms-text-primary);
  line-height: 1.2;
}

@keyframes pulse {
  0% { box-shadow: 0 0 0 0 var(--kms-brand-border); }
  70% { box-shadow: 0 0 0 10px transparent; }
  100% { box-shadow: 0 0 0 0 transparent; }
}
@media (max-width: 1024px) {
  .hero-metrics { grid-template-columns: 1fr; }
}
</style>
