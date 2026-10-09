<template>
  <main class="entry-page">
    <el-card class="entry-card" shadow="never">
      <h1>密钥管理系统</h1>
      <h2>独立运行</h2>
      <p>管理员使用账号与密码；节点使用激活凭证或本机设备免密登录。所有权限以服务端身份为准。</p>
      <div class="entry-actions">
        <el-button type="primary" @click="router.push('/standalone/admin/login')">管理员登录</el-button>
        <el-button @click="router.push('/standalone/node/login')">节点登录</el-button>
      </div>
      <el-divider />
      <p class="hint">受控演示是独立的本机入口，默认关闭，不继承此处登录身份或私钥。仅限测试数据库与本机回环网关。</p>
      <a href="http://127.0.0.1:8088/demo">打开本机受控演示入口（需先启用）</a>
    </el-card>
  </main>
</template>

<script setup>
const router = useRouter()
</script>

<style scoped>
.entry-page { min-height: 100vh; display: grid; place-items: center; padding: 24px; background: var(--kms-surface-2); }
.entry-card { max-width: 600px; }
h1 { font-size: 24px; }
h2 { font-size: 18px; }
p { line-height: 1.8; }
.entry-actions { display: flex; gap: 12px; margin: 24px 0; }
.hint { color: var(--el-text-color-secondary); font-size: 13px; }
</style>
