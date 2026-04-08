<template>
  <div class="scroll-container" ref="scrollContainer">
    <slot />
  </div>
</template>

<script>
export default {
  name: 'ScrollPane',
  emits: ['scroll'],
  methods: {
    handleScroll(e) {
      this.$emit('scroll', e)
    }
  }
}
</script>

<style scoped>
.scroll-container { overflow-x: hidden; }
</style>
