<template>
  <el-scrollbar id="scroll-container" class="scroll-container" :vertical="false">
    <slot />
  </el-scrollbar>
</template>

<script setup>
const scroll = ref(null)

function handleScroll() {
  // noop
}
</script>

<style lang="scss" scoped>
.scroll-container {
  white-space: nowrap;
  position: relative;
  overflow: hidden;
  width: 100%;
}
</style>
