<template>
  <section class="hero-metrics">
    <div class="hero-content">
      <div class="brand">
        <span class="pulsing-dot"></span>
        <p class="eyebrow">ACCEPTANCE ENV</p>
      </div>
      <h1 class="gradient-text">KMS Test System</h1>
      <p class="hero-copy">
        独立前后端的高级测试终端。用于执行 <code>wrk</code> 极限压测，掌控系统吞吐指标，以及自动化安全演练。
      </p>
    </div>
    
    <div class="hero-cards">
      <article class="stat-card glass-panel" style="--accent-hue: 160">
        <div class="stat-icon">🎯</div>
        <div class="stat-info">
          <span>压测场景总数</span>
          <strong>{{ scenarios.length }}</strong>
        </div>
      </article>
      <article class="stat-card glass-panel" style="--accent-hue: 210">
        <div class="stat-icon">⚡</div>
        <div class="stat-info">
          <span>历史压测轮次</span>
          <strong>{{ runs.length }}</strong>
        </div>
      </article>
      <article class="stat-card glass-panel" style="--accent-hue: 280">
        <div class="stat-icon">🛡️</div>
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
.pulsing-dot {
  width: 8px;
  height: 8px;
  background-color: #00f2fe;
  border-radius: 50%;
  box-shadow: 0 0 10px #00f2fe, 0 0 20px #00f2fe;
  animation: pulse 2s infinite;
}
.eyebrow {
  color: #00f2fe;
  letter-spacing: 0.2em;
  font-size: 11px;
  font-weight: 700;
  margin: 0;
}
.gradient-text {
  font-size: clamp(36px, 5vw, 56px);
  font-weight: 800;
  margin: 0 0 16px 0;
  background: linear-gradient(135deg, #fff 0%, #9fb3c8 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  line-height: 1.1;
}
.hero-copy {
  color: #8b9eb3;
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
.stat-icon {
  font-size: 32px;
  background: hsl(var(--accent-hue) 80% 50% / 0.1);
  width: 60px;
  height: 60px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 16px;
}
.stat-info {
  display: flex;
  flex-direction: column;
}
.stat-info span {
  font-size: 12px;
  color: #8b9eb3;
  text-transform: uppercase;
  letter-spacing: 1px;
}
.stat-info strong {
  font-size: 32px;
  font-weight: 700;
  color: #fff;
  line-height: 1.2;
}

@keyframes pulse {
  0% { box-shadow: 0 0 0 0 rgba(0, 242, 254, 0.4); }
  70% { box-shadow: 0 0 0 10px rgba(0, 242, 254, 0); }
  100% { box-shadow: 0 0 0 0 rgba(0, 242, 254, 0); }
}
@media (max-width: 1024px) {
  .hero-metrics { grid-template-columns: 1fr; }
}
</style>
