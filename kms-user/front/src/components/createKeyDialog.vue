<template>
    <el-dialog v-model="createDialogVisible" title="新建密钥" width="800">
   <el-form :model="form" label-width="auto" style="max-width: 600px;margin:0 auto;">
     <el-form-item label="密钥名称">
       <el-input v-model="form.name" />
     </el-form-item>
     <el-form-item label="描述信息">
       <el-input v-model="form.desc" type="textarea" />
     </el-form-item>
     <el-form-item label="密钥用途">
       <el-select v-model="form.region" placeholder="请选择密钥用途">
         <el-option label="对称加解密" value="symmetry" />
         <el-option label="非对称加解密" value="dissymmetric" />
       </el-select>
     </el-form-item>
     <el-form-item label="密钥材料来源">
       <el-radio-group v-model="form.resource">
         <el-radio value="kms">kms</el-radio>
         <el-radio value="external">外部</el-radio>
       </el-radio-group>
     </el-form-item>
     <el-form-item>
      <div style="position:absolute;right:0;">
       <el-button type="primary" @click="onSubmit">确定</el-button>
       <el-button @click="createDialogVisible = false">取消</el-button>
      </div>
     </el-form-item>
   </el-form>
 </el-dialog>
 </template>
 
 <script  setup>
 import { reactive,ref } from 'vue'
 
 const createDialogVisible = ref(false);
 const form = reactive({
   name: '',
   region: '',
   date1: '',
   date2: '',
   delivery: false,
   type: [],
   resource: '',
   desc: '',
 })
 defineExpose({
  createDialogVisible, // 如果你想让父组件能够访问这个变量
});
 const onSubmit = () => {
    createDialogVisible.value = false;

 }
 </script>
 