<template>
  <div class="view-container fade-in">
    <HeroMetrics />
    <section class="grid-layout top-tier">
      <ScenarioRunner />
      <HistoryLog />
    </section>
  </div>
</template>

<script setup>
import HeroMetrics from '../components/HeroMetrics.vue'
import ScenarioRunner from '../components/ScenarioRunner.vue'
import HistoryLog from '../components/HistoryLog.vue'
</script>

<style scoped>
.grid-layout {
  display: grid;
  grid-template-columns: 1fr;
  gap: 24px;
}
@media (min-width: 1400px) {
  .top-tier {
    grid-template-columns: 1fr 1fr;
  }
}
</style>
