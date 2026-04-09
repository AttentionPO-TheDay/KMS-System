<template>
  <section class="page">
    <div class="page-header">
      <p class="eyebrow">Workbench</p>
      <h2>统一工作台</h2>
      <p>这里将承接老系统 `userKeys.vue` 的集成式操作体验。</p>
    </div>

    <div class="card-grid">
      <article class="card">
        <h3>生成链路</h3>
        <p>用户注册、公共参数、密钥生成、生成历史、我的密钥。</p>
        <RouterLink to="/generate">进入生成系统</RouterLink>
      </article>
      <article class="card">
        <h3>更新与回收链路</h3>
        <p>密钥更新、密钥回收、自动更新、权限申请与审批。</p>
        <RouterLink to="/updatedel">进入更新与回收系统</RouterLink>
      </article>
      <article class="card">
        <h3>分发查询</h3>
        <p>分发记录列表、详情查询和后续分发态势展示。</p>
        <RouterLink to="/distribute">进入分发系统</RouterLink>
      </article>
      <article class="card">
        <h3>临时提权</h3>
        <p>普通用户在这里申请查看公共密钥列表和密钥自动更新两类临时权限。</p>
        <RouterLink to="/permissions">进入权限申请</RouterLink>
      </article>
    </div>
  </section>
</template>
