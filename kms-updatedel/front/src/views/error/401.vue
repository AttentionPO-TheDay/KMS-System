<template>
  <div class="wscn-http404-container">
    <div class="wscn-http404">
      <div class="pic-401">
        <img class="pic-401__parent" src="@/assets/images/401.gif" alt="401">
      </div>
      <div class="text-401">
        <h1>401</h1>
        <p>抱歉，您没有访问该页面的权限</p>
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

.text-401 {
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
