<template>
  <div>
    <el-upload
      :action="uploadUrl"
      :headers="headers"
      :multiple="multiple"
      :limit="limit"
      :before-upload="beforeUpload"
      :on-success="handleSuccess"
      :on-error="handleError"
      :on-remove="handleRemove"
      :file-list="fileList"
      :disabled="disabled"
      :show-file-list="showFileList"
      :accept="accept"
      drag
    >
      <el-icon class="el-icon--upload"><upload-filled /></el-icon>
      <div class="el-upload__text">将文件拖到此处，或<em>点击上传</em></div>
    </el-upload>
  </div>
</template>

<script>
export default {
  name: 'FileUpload'
}
</script>
