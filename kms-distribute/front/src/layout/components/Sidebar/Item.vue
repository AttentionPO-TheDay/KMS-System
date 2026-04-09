<template>
  <el-icon><component :is="icon" /></el-icon>
  <span>{{ title }}</span>
</template>

<script setup>
defineProps({
  icon: {
    type: String,
    default: ''
  },
  title: {
    type: String,
    default: ''
  }
})
</script>
