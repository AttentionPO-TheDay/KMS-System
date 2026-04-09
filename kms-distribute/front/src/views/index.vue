<template>
  <div class="index-container">
    <h1>密钥分发系统</h1>
    <p>管理与查询密钥分发记录</p>
    <div class="links">
      <el-card class="link-card">
        <template #header>
          <span>分发记录查询</span>
        </template>
        <el-button type="primary" @click="$router.push('/distribute/record')">进入</el-button>
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
