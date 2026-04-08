<template>
  <div>
    <el-upload
      :action="uploadUrl"
      :headers="headers"
      list-type="picture-card"
      :on-preview="handlePictureCardPreview"
      :on-remove="handleRemove"
      :disabled="disabled"
    >
      <el-icon><Plus /></el-icon>
    </el-upload>
    <el-dialog v-model="dialogVisible">
      <img :src="dialogImageUrl" alt="" style="width: 100%" />
    </el-dialog>
  </div>
</template>

<script>
export default {
  name: 'ImageUpload'
}
</script>
