<template>
  <main class="page-shell dark-theme">
    <div class="glow-bg"></div>
    <HeroMetrics />
    <section class="grid-layout top-tier">
      <ScenarioRunner />
      <HistoryLog />
    </section>
    <section class="grid-layout">
      <ProofVisualizer />
    </section>
    <section class="grid-layout">
      <SecuritySuite />
    </section>
  </main>
</template>

<script setup>
import { onMounted } from 'vue'
import { loadAll } from './store'
import HeroMetrics from './components/HeroMetrics.vue'
import ScenarioRunner from './components/ScenarioRunner.vue'
import HistoryLog from './components/HistoryLog.vue'
import ProofVisualizer from './components/ProofVisualizer.vue'
import SecuritySuite from './components/SecuritySuite.vue'

onMounted(async () => {
  await loadAll()
})
</script>

<style scoped>
.page-shell {
  max-width: 1600px;
  margin: 0 auto;
  padding: 40px 24px 80px;
  position: relative;
  z-index: 1;
}
.glow-bg {
  position: fixed;
  top: -20vh;
  left: -10vw;
  width: 60vw;
  height: 60vh;
  background: radial-gradient(circle, rgba(0,242,254,0.08) 0%, rgba(0,0,0,0) 70%);
  z-index: -1;
  pointer-events: none;
}
.grid-layout {
  display: grid;
  grid-template-columns: 1fr;
  gap: 24px;
  margin-bottom: 24px;
}
@media (min-width: 1400px) {
  .top-tier {
    grid-template-columns: 1fr 1fr;
  }
}
</style>
