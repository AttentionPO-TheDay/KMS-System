<template>
  <section class="page">
    <div class="page-header">
      <p class="eyebrow">Distribute</p>
      <h2>分发系统迁移区</h2>
      <p>后续将 `kms-distribute/front/src/views/distribute/record.vue` 纳入统一前端。</p>
    </div>

    <article class="panel">
      <h3>当前纳入范围</h3>
      <ul>
        <li>分发记录列表</li>
        <li>分发记录详情</li>
        <li>分发状态筛选</li>
      </ul>
      <p>API 前缀：<code>{{ apiBase }}</code></p>
    </article>
  </section>
</template>

<script setup>
import { apiBases } from '@/config/api-bases'

const apiBase = apiBases.distributeApi
</script>
