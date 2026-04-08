<template>
  <el-image
    :src="src"
    :style="style"
    :width="width"
    :height="height"
    :preview-src-list="[src]"
    :preview-teleported="true"
  />
</template>

<script>
export default {
  name: 'ImagePreview'
}
</script>
