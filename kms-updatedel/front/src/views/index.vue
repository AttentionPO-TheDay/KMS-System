<template>
  <div class="index-container">
    <h1>生命周期系统</h1>
    <p>密钥更新与回收管理系统</p>
    <div class="links">
      <el-card class="link-card">
        <template #header>
          <span>密钥更新</span>
        </template>
        <el-button type="primary" @click="$router.push('/lifecycle/keyupdate')">进入</el-button>
      </el-card>
      <el-card class="link-card">
        <template #header>
          <span>密钥回收</span>
        </template>
        <el-button type="danger" @click="$router.push('/lifecycle/keydelete')">进入</el-button>
      </el-card>
      <el-card class="link-card">
        <template #header>
          <span>自动更新</span>
        </template>
        <el-button type="success" @click="$router.push('/lifecycle/keyautoupdate')">进入</el-button>
      </el-card>
      <el-card class="link-card">
        <template #header>
          <span>权限审批</span>
        </template>
        <el-button type="warning" @click="$router.push('/permission/request/index')">进入</el-button>
      </el-card>
    </div>
  </div>
</template>

<script setup>
</script>

<style scoped>
.index-container {
  padding: 32px;
  text-align: center;
}

h1 {
  font-size: 32px;
  color: #303133;
  margin-bottom: 16px;
}

p {
  font-size: 18px;
  color: #606266;
  margin-bottom: 32px;
}

.links {
  display: flex;
  justify-content: center;
  gap: 20px;
  flex-wrap: wrap;
}

.link-card {
  width: 200px;
  text-align: center;
}
</style>
