<template>
  <div @click="click">
    <svg-icon :icon-class="isFullscreen ? 'exit-fullscreen' : 'fullscreen'" />
  </div>
</template>

<script>
export default {
  name: 'Screenfull',
  data() { return { isFullscreen: false } },
  methods: {
    click() {
      if (!document.fullscreenElement) {
        document.documentElement.requestFullscreen()
        this.isFullscreen = true
      } else {
        document.exitFullscreen()
        this.isFullscreen = false
      }
    }
  }
}
</script>
