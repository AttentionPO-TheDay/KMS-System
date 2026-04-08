<template>
  <section class="page">
    <div class="page-header">
      <p class="eyebrow">Generate</p>
      <h2>生成系统迁移区</h2>
      <p>后续从 `kms-generate/front` 迁入生成、历史、公共参数与用户密钥页面。</p>
    </div>

    <article class="panel">
      <h3>计划迁入</h3>
      <ul>
        <li>密钥生成</li>
        <li>生成历史</li>
        <li>公共参数</li>
        <li>我的密钥</li>
      </ul>
      <p>API 前缀：<code>{{ apiBase }}</code></p>
      <RouterLink class="inline-link" to="/permissions">申请查看公共密钥列表</RouterLink>
    </article>
  </section>
</template>

<script setup>
import { apiBases } from '@/config/api-bases'

const apiBase = apiBases.generateApi
</script>
