<template>
  <div class="shell">
    <aside class="sidebar">
      <div class="brand">
        <p class="eyebrow">Unified UI</p>
        <h1>kms-user</h1>
        <p>统一用户界面，聚合生成、更新与回收、分发能力。</p>
      </div>
      <section class="auth-panel">
        <h2>统一登录</h2>
        <p v-if="authState.profile" class="muted">
          当前用户：<strong>{{ authState.profile.userName }}</strong>
          <span> · 等级 {{ authState.profile.roleLevel }}</span>
        </p>
        <div v-if="authState.profile" class="system-status">
          <p><strong>系统联通状态</strong></p>
          <ul>
            <li>
              生成系统：
              <span :class="authState.systemAccess.generate.ok ? 'status-ok' : 'status-bad'">
                {{ authState.systemAccess.generate.message }}
              </span>
            </li>
            <li>
              更新与回收系统：
              <span :class="authState.systemAccess.lifecycle.ok ? 'status-ok' : 'status-bad'">
                {{ authState.systemAccess.lifecycle.message }}
              </span>
            </li>
            <li>
              分发系统：
              <span :class="authState.systemAccess.distribute.ok ? 'status-ok' : 'status-bad'">
                {{ authState.systemAccess.distribute.message }}
              </span>
            </li>
          </ul>
        </div>
        <template v-if="!authState.profile">
          <label class="auth-field">
            <span>用户名</span>
            <input v-model="loginForm.username" type="text" autocomplete="username" />
          </label>
          <label class="auth-field">
            <span>密码</span>
            <input v-model="loginForm.password" type="password" autocomplete="current-password" />
          </label>
          <label v-if="captcha.enabled" class="auth-field">
            <span>验证码</span>
            <div class="captcha-row">
              <input v-model="loginForm.code" type="text" autocomplete="off" />
              <img
                v-if="captcha.img"
                :src="captcha.img"
                alt="captcha"
                class="captcha-image"
                @click="loadCaptcha"
              />
            </div>
          </label>
          <div class="auth-actions">
            <button @click="submitLogin" :disabled="authState.loading">
              {{ authState.loading ? '登录中...' : '登录' }}
            </button>
            <button class="ghost-button" @click="loadCaptcha" :disabled="authState.loading">刷新验证码</button>
          </div>
        </template>
        <div v-else class="auth-actions">
          <button class="ghost-button" @click="refreshCurrentProfile">刷新资料</button>
          <button class="danger-button" @click="logoutCurrentUser">退出</button>
        </div>
        <p v-if="authState.lastError" class="error-text">{{ authState.lastError }}</p>
      </section>
      <nav class="nav">
        <RouterLink to="/workbench">工作台</RouterLink>
        <RouterLink to="/generate">生成系统</RouterLink>
        <RouterLink to="/updatedel">更新与回收系统</RouterLink>
        <RouterLink to="/distribute">分发系统</RouterLink>
        <RouterLink to="/permissions">权限申请</RouterLink>
      </nav>
      <section class="meta">
        <h2>API Prefix</h2>
        <ul>
          <li><code>{{ generateApi }}</code></li>
          <li><code>{{ lifecycleApi }}</code></li>
          <li><code>{{ distributeApi }}</code></li>
        </ul>
      </section>
    </aside>
    <main class="content">
      <RouterView />
    </main>
  </div>
</template>

<script setup>
import { onMounted, reactive } from 'vue'
import { apiBases } from '@/config/api-bases'
import { authState, fetchCaptcha, login, logout, refreshProfile } from '@/services/auth'

const { generateApi, lifecycleApi, distributeApi } = apiBases

const loginForm = reactive({
  username: '',
  password: '',
  code: '',
  uuid: ''
})

const captcha = reactive({
  enabled: false,
  img: ''
})

onMounted(async () => {
  try {
    await refreshProfile()
  } catch {
    // keep login panel available
  }

  if (!authState.profile) {
    await loadCaptcha()
  }
})

async function loadCaptcha() {
  try {
    const data = await fetchCaptcha()
    captcha.enabled = Boolean(data?.captchaEnabled)
    loginForm.uuid = data?.uuid || ''
    loginForm.code = ''
    captcha.img = data?.img ? `data:image/jpg;base64,${data.img}` : ''
  } catch (error) {
    authState.lastError = error.message
  }
}

async function submitLogin() {
  authState.lastError = ''
  try {
    await login({ ...loginForm })
    loginForm.password = ''
    loginForm.code = ''
  } catch {
    await loadCaptcha()
  }
}

async function refreshCurrentProfile() {
  try {
    await refreshProfile()
  } catch {
    await loadCaptcha()
  }
}

async function logoutCurrentUser() {
  logout()
  await loadCaptcha()
}
</script>

<style scoped>
.system-status ul {
  margin: 8px 0 0;
  padding-left: 18px;
}

.status-ok {
  color: #16a34a;
}

.status-bad {
  color: #dc2626;
}
</style>
