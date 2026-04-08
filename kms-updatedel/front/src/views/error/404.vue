<template>
  <div class="wscn-http404-container">
    <div class="wscn-http404">
      <div class="pic-404">
        <img class="pic-404__parent" src="@/assets/images/404.png" alt="404">
      </div>
      <div class="text-404">
        <h1>404</h1>
        <p>抱歉，您访问的页面不存在</p>
        <el-button type="primary" @click="goHome">返回首页</el-button>
      </div>
    </div>
  </div>
</template>

<script setup>
function goHome() {
  router.push('/')
}
</script>

<style lang="scss" scoped>
.wscn-http404-container {
  transform: translate(-50%, -50%);
  position: absolute;
  top: 40%;
  left: 50%;
}

.text-404 {
  text-align: center;
}

h1 {
  font-size: 80px;
  color: #606266;
  margin: 20px 0;
}

p {
  font-size: 18px;
  color: #606266;
  margin-bottom: 20px;
}
</style>
