<template>
  <main class="page-shell dark-theme">
    <div class="glow-bg"></div>
    <header class="top-nav">
      <div class="nav-brand">
        <span class="pulsing-dot"></span>
        <span class="brand-text">KMS ACCEPTANCE</span>
      </div>
      <nav class="nav-links">
        <router-link to="/load-test" class="nav-item">压测与回收</router-link>
        <router-link to="/security" class="nav-item">安全演练</router-link>
        <router-link to="/others" class="nav-item">机制测试（其他）</router-link>
      </nav>
    </header>

    <div class="main-content">
      <router-view v-slot="{ Component }">
        <transition name="page-fade" mode="out-in">
          <component :is="Component" />
        </transition>
      </router-view>
    </div>
  </main>
</template>

<script setup>
import { onMounted } from 'vue'
import { loadAll } from './store'

onMounted(async () => {
  try {
    await loadAll()
  } catch (err) {
    console.error(err)
  }
})
</script>

<style scoped>
.page-shell {
  max-width: 1600px;
  margin: 0 auto;
  padding: 0 24px 80px;
  position: relative;
  z-index: 1;
}
/* 装饰性光晕：原为暗色主题下的霓虹辉光。
   浅色风格下改为极淡的径向渐变，避免形成生硬的纯色块。 */
.glow-bg {
  position: fixed;
  top: -20vh;
  left: -10vw;
  width: 60vw;
  height: 60vh;
  background: radial-gradient(circle at 30% 30%, rgba(22, 119, 255, 0.06) 0%, rgba(22, 119, 255, 0) 70%);
  z-index: -1;
  pointer-events: none;
}

.top-nav {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 30px 0 40px;
}

.nav-brand {
  display: flex;
  align-items: center;
  gap: 12px;
}

.pulsing-dot {
  width: 8px;
  height: 8px;
  background-color: var(--kms-brand-fill);
  border-radius: 50%;
  box-shadow: 0 0 10px var(--kms-brand), 0 0 20px var(--kms-brand);
  animation: pulse 2s infinite;
}

.brand-text {
  color: var(--kms-brand-text);
  letter-spacing: 0.2em;
  font-size: 13px;
  font-weight: 800;
}

.nav-links {
  display: flex;
  gap: 8px;
  padding: 6px;
  border-radius: 40px;
}

.nav-item {
  color: var(--kms-text-secondary);
  text-decoration: none;
  padding: 10px 24px;
  border-radius: 30px;
  font-size: 14px;
  font-weight: 600;
  transition: all 0.3s ease;
}

.nav-item:hover {
  color: var(--kms-text-primary);
  background: var(--kms-surface-3);
}

.router-link-active {
  background: var(--kms-brand-subtle);
  color: var(--kms-brand-text);
  box-shadow: 0 4px 12px var(--kms-brand-subtle);
  border: 1px solid var(--kms-brand-border);
}

.main-content {
  position: relative;
  min-height: 500px;
}

.page-fade-enter-active,
.page-fade-leave-active {
  transition: opacity 0.3s ease, transform 0.3s ease;
}
.page-fade-enter-from {
  opacity: 0;
  transform: translateY(10px);
}
.page-fade-leave-to {
  opacity: 0;
  transform: translateY(-10px);
}

@keyframes pulse {
  0% { box-shadow: 0 0 0 0 var(--kms-brand-border); }
  70% { box-shadow: 0 0 0 10px transparent; }
  100% { box-shadow: 0 0 0 0 transparent; }
}
</style>
