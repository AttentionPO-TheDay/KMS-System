<template>
  <div class="view-container fade-in">
    <section class="grid-layout">
      <ProofVisualizer />
    </section>
  </div>
</template>

<script setup>
import ProofVisualizer from '../components/ProofVisualizer.vue'
</script>

<style scoped>
.grid-layout {
  display: grid;
  grid-template-columns: 1fr;
  gap: 24px;
}
</style>
