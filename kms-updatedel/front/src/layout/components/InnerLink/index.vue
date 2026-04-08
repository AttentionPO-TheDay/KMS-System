<template>
  <iframe :src="src" class="inner-link-frame" frameborder="0" />
</template>

<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'

const route = useRoute()

const src = computed(() => route.meta?.link || route.query?.url || 'about:blank')
</script>

<style scoped>
.inner-link-frame {
  width: 100%;
  min-height: calc(100vh - 120px);
}
</style>
