import { getSelfNode } from '@/api/pqkds/node-self'

/**
 * 节点初始化状态的会话级缓存（阶段 2）。
 *
 * 为什么需要缓存
 * ------------
 * 路由守卫对**每次导航**都要判断"这个节点是否已完成首次初始化"，而每次判断背后是
 * 「令牌自省（HTTP→Java）+ 查库（Django）」两个网络往返。节点用户每切一次页面
 * 就多两次调用，代价明显。状态只在初始化完成的那一刻变化，因此按会话缓存足够。
 *
 * 为什么单独一个模块
 * ----------------
 * 缓存要在两处使用：守卫读它（`permission.js`），登出清它（`store/modules/user.js`）。
 * 若把缓存放在 `permission.js` 里、由 store 去 import，会形成
 * `store → permission → store` 的循环依赖。抽成独立模块两边都能引，且方向单一。
 *
 * 并发去重：存的是 **Promise** 而非结果值 —— 连续快速导航时会同时跑多个
 * `beforeEach`，存 Promise 让它们共用同一次请求，而不是各发一份。
 */

let pending = null

/**
 * 取当前节点账号的初始化状态。
 *
 * @returns {Promise<'PENDING_INIT'|'ACTIVE'|'DISABLED'|null>}
 *   - `PENDING_INIT` 未完成初始化 → 守卫送去引导页
 *   - `ACTIVE`       已完成       → 正常放行
 *   - `DISABLED`     无节点身份/已停用
 *   - `null`         查询失败     → **不阻断导航**（见下）
 */
export function fetchNodeInitStatus() {
  if (!pending) {
    pending = getSelfNode()
      .then((data) => {
        if (!data?.mapped) return 'DISABLED' // 账号没关联节点：不是有效节点身份
        return data?.node?.status || null
      })
      .catch((error) => {
        // 失败**不缓存**：否则一次网络抖动会让该节点在整个会话里绕过初始化检查。
        console.warn('[node-init] 读取初始化状态失败，本次跳过拦截：', error?.message)
        pending = null
        // 不阻断导航：这个查询依赖分发模块可达，它挂掉时若直接拒绝，
        // 整个控制台会因一个辅助接口不可用而全站打不开 —— 那是把故障放大。
        return null
      })
  }
  return pending
}

/** 清缓存。登出/切换账号时必须调用，否则上一个账号的状态会泄漏给下一个。 */
export function resetNodeInitStatusCache() {
  pending = null
}

/**
 * 初始化成功后主动失效缓存。
 *
 * 引导页完成初始化后节点状态变为 ACTIVE，但缓存里还是 PENDING_INIT ——
 * 不清的话守卫会把用户一直弹回引导页，形成"初始化完了还进不去"的循环。
 */
export function markNodeInitialized() {
  pending = Promise.resolve('ACTIVE')
}