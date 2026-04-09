<template>
  <el-image v-if="src" :src="src" fit="contain" />
</template>

<script setup>
defineProps({
  src: {
    type: String,
    default: ''
  }
})
</script>
