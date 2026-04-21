<template>
  <div class="view-container fade-in">
    <section class="grid-layout">
      <SecuritySuite />
    </section>
  </div>
</template>

<script setup>
import SecuritySuite from '../components/SecuritySuite.vue'
</script>

<style scoped>
.grid-layout {
  display: grid;
  grid-template-columns: 1fr;
  gap: 24px;
}
</style>
