<template>
  <div class="shell">
    <aside class="sidebar">
      <div class="brand">
        <p class="eyebrow">Unified UI</p>
        <h1>kms-user</h1>
        <p>统一用户界面，聚合生成、生命周期与分发能力。</p>
      </div>
      <nav class="nav">
        <RouterLink to="/workbench">工作台</RouterLink>
        <RouterLink to="/generate">生成系统</RouterLink>
        <RouterLink to="/lifecycle">生命周期系统</RouterLink>
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
import { apiBases } from '@/config/api-bases'

const { generateApi, lifecycleApi, distributeApi } = apiBases
</script>
