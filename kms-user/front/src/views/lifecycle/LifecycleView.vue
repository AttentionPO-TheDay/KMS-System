<template>
  <section class="page">
    <div class="page-header">
      <p class="eyebrow">Lifecycle</p>
      <h2>生命周期系统迁移区</h2>
      <p>后续从 `kms-updatedel/front` 迁入更新、回收、自动更新和权限审批页面。</p>
    </div>

    <article class="panel">
      <h3>计划迁入</h3>
      <ul>
        <li>密钥更新</li>
        <li>密钥回收</li>
        <li>自动更新</li>
        <li>权限申请与审批</li>
      </ul>
      <p>API 前缀：<code>{{ apiBase }}</code></p>
      <RouterLink class="inline-link" to="/permissions">申请密钥自动更新权限</RouterLink>
    </article>
  </section>
</template>

<script setup>
import { apiBases } from '@/config/api-bases'

const apiBase = apiBases.lifecycleApi
</script>
