<template>
  <section class="app-main">
    <router-view v-slot="{ Component, route }">
      <transition name="fade-transform" mode="out-in">
        <keep-alive :include="cachedViews">
          <component :is="Component" :key="route.path" />
        </keep-alive>
      </transition>
    </router-view>
  </section>
</template>

<script>
export default {
  name: 'AppMain',
  computed: {
    cachedViews() {
      return []
    },
    key() {
      return this.$route.path
    }
  }
}
</script>

<style lang="scss" scoped>
.app-main {
  min-height: 100%;
  width: 100%;
  position: relative;
  overflow: hidden;
}

.fixed-width {
  padding: 10px 10px 0;
}

.fade-transform-leave-active,
.fade-transform-enter-active {
  transition: all .28s;
}

.fade-transform-enter-from {
  opacity: 0;
  transform: translateX(-100%);
}

.fade-transform-leave-to {
  opacity: 0;
  transform: translateX(100%);
}

.fade-transform-leave-active {
  position: absolute;
}
</style>
