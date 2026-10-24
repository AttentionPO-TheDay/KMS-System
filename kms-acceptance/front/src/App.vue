<template>
  <main class="page-shell dark-theme">
    <div class="glow-bg"></div>
    <header class="top-nav">
      <div class="nav-brand">
        <span class="pulsing-dot"></span>
        <span class="brand-text">KMS ACCEPTANCE</span>
      </div>
      <nav class="nav-links">
        <router-link to="/load-test" class="nav-item">验收测试台</router-link>
        <router-link to="/lattice" class="nav-item" :class="{ 'router-link-active': $route.path.startsWith('/lattice') }">格预分配测试</router-link>
        <router-link to="/lifecycle" class="nav-item">验收密钥生命周期</router-link>
      </nav>
    </header>

    <p v-if="demoState.message || error" role="status">{{ demoState.message || error }}</p>
    <p v-if="demoState.busy" role="status">测试执行中，结束或停止后可切换身份或退出。</p>
    <fieldset class="main-content" :disabled="!demoState.available || demoState.stale || demoState.context?.principalType !== 'ADMIN'">
      <router-view v-slot="{ Component }">
        <transition name="page-fade" mode="out-in">
          <component :is="Component" />
        </transition>
      </router-view>
    </fieldset>
  </main>
</template>

<script setup>
import { onMounted, onUnmounted } from 'vue'
import { loadAll, loadRuns, loadSecurityRuns, loadAcceptanceEvidence, error } from './store'
import { demoState, refreshDemoContext } from './api/demo-context'

let timer
let refreshing = false
async function synchronize() {
  if (refreshing || demoState.stale) return
  refreshing = true
  try {
    await refreshDemoContext()
    if (demoState.available && demoState.context?.principalType === 'ADMIN') await loadAll()
  } catch (err) {
    error.value = err.message
  } finally {
    refreshing = false
  }
}
onMounted(async () => {
  await synchronize()
  timer = setInterval(async () => {
    if (demoState.busy && demoState.available && !demoState.stale) {
      try { await Promise.all([loadRuns(), loadSecurityRuns(), loadAcceptanceEvidence()]) } catch (err) { error.value = err.message }
    }
    await synchronize()
  }, 5000)
  window.addEventListener('focus', synchronize)
})
onUnmounted(() => {
  clearInterval(timer)
  window.removeEventListener('focus', synchronize)
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
  white-space: nowrap;
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
  border: 0;
  margin: 0;
  padding: 0;
  min-width: 0;
  position: relative;
  min-height: 500px;
}

@media (max-width: 640px) {
  .top-nav { flex-direction: column; align-items: flex-start; gap: 12px; padding: 24px 0; }
  .nav-links { flex-wrap: wrap; padding: 0; }
  .nav-item { padding: 12px; font-size: .8125rem; }
  .nav-brand { flex-shrink: 0; }
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
