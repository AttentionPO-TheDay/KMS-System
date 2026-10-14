<template>
  <router-view />
</template>

<script setup>
import useSettingsStore from '@/store/modules/settings'
import { handleThemeStyle } from '@/utils/theme'
import { startAutoUpdate } from '@/utils/node-auto-update'

let stopAutoUpdate
onUnmounted(() => stopAutoUpdate?.())

onMounted(() => {
  stopAutoUpdate = startAutoUpdate()
  nextTick(() => {
    // 初始化主题样式
    handleThemeStyle(useSettingsStore().theme)
  })
})
</script>
