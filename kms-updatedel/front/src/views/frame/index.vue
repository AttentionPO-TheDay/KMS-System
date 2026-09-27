<template>
  <div class="frame-wrap">
    <el-alert
      v-if="!src"
      type="warning"
      :closable="false"
      show-icon
      title="该菜单没有配置要嵌入的地址（菜单的 query 里应带 url=…）"
    />
    <iframe
      v-else
      :src="src"
      class="frame"
      frameborder="no"
      referrerpolicy="same-origin"
    ></iframe>
  </div>
</template>

<script setup>
/**
 * 同源内嵌页容器（P4）。
 *
 * 为什么不用 RuoYi 自带的 `InnerLink`
 * ----------------------------------
 * `InnerLink` 走的是后端 `MetaVo` 的 4 参构造，而那里有一句
 * `if (StringUtils.ishttp(link))` —— **只有 http(s) 绝对地址**才会被写进 `meta.link`。
 * 我们要嵌的是**同源路径**（`/distribute/`、`/acceptance/`），
 * 于是 `meta.link` 恒为 null，前端不渲染 iframe，页面白屏。
 *
 * 换句话说：`InnerLink` 是给"外链"用的，不是给"同源子应用"用的。
 * 硬要用它就得把 `http://<主机>/distribute/` 写死进菜单 ——
 * 换个访问域名就废，所以这里改用本组件。
 *
 * 登录态怎么传
 * ------------
 * 同源 iframe **共享 Cookie**，而主 KMS 的令牌就在 `Admin-Token` 这个 Cookie 里，
 * 因此被嵌页面发出的同源请求天然带着它 —— 不需要在 URL 里塞令牌
 * （塞进 URL 会被网关日志、浏览器历史、Referer 记录下来，是更差的做法）。
 */

import { computed } from 'vue'
import { useRoute } from 'vue-router'

const route = useRoute()

/**
 * 目标地址的兜底表：**按路由末段**映射。
 *
 * 为什么需要它：菜单下发的 `query`（`{"url":"/distribute/"}`）**只在"从侧边栏点进去"时**
 * 才出现在 URL 上。于是直接敲地址、点书签、或者**按 F5 刷新**时 `route.query.url` 是空的 ——
 * 页面会显示"该菜单没有配置要嵌入的地址"，内嵌内容整个消失。
 *
 * 这不是理论问题：刷新是极常见的操作，而"刷新后页面变了样"属于很难被当成 bug 报上来的那种故障。
 * 所以这里按路径末段兜底，让内嵌页在**任何进入方式**下都能正常显示。
 * `query` 仍然优先（便于临时指向别处），只是不再是唯一来源。
 */
const TARGET_BY_SEGMENT = {
  distribute: '/distribute/',
  blockchain: '/distribute/#/blockchain',
  nodelist: '/distribute/#/node',
  acceptance: '/acceptance/'
}

function normalize(value) {
  const text = String(Array.isArray(value) ? value[0] : value || '').trim()
  if (!text) {
    return ''
  }
  // 只允许同源相对路径：写成绝对地址会让这个组件退化成开放的 iframe 容器
  return text.startsWith('/') ? text : `/${text}`
}

/** 要嵌入的地址：优先取 `query.url`，取不到则按路由末段兜底 */
const src = computed(() => {
  const fromQuery = normalize(route.query?.url)
  if (fromQuery) {
    return fromQuery
  }
  const segments = String(route.path || '').split('/').filter(Boolean)
  return TARGET_BY_SEGMENT[segments[segments.length - 1]] || ''
})
</script>

<style scoped>
.frame-wrap {
  height: calc(100vh - 84px);
}

.frame {
  width: 100%;
  height: 100%;
  border: 0;
  background: #fff;
}
</style>
