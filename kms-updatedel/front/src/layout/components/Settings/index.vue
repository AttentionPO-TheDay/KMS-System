<template>
  <div>
    <el-switch v-model="theme" active-value="dark" inactive-value="light" @change="themeChange" />
  </div>
</template>

<script setup>
const theme = ref('light')

function themeChange(val) {
  useSettingsStore().setTheme(val)
  handleThemeStyle()
}
</script>
