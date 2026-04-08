<template>
  <main class="app-main">
    <slot />
  </main>
</template>

<script setup>
useSettingsStore()
</script>

<style lang="scss" scoped>
.app-main {
  min-height: 100vh;
  width: 100%;
  position: relative;
  overflow: hidden;
}

.fixed-app-main {
  min-height: 100vh;
  overflow: auto;
}
</style>
