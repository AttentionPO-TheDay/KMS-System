/**
 * 四个前端的产物完整性冒烟测试（纯 HTTP，不需要浏览器）。
 *
 * 校验点：
 *   1. 每个应用的 index.html 可访问，且带 no-store；
 *   2. index.html 里引用的每个 /assets/ 资源都返回 200 且 Content-Type 正确
 *      （CSS 必须是 text/css，JS 不能是 text/html —— text/html 意味着命中了
 *       SPA fallback，即「HTML 冒充 JS」）；
 *   3. 哈希资源带 immutable；
 *   4. 不存在的资源返回 404 而不是 200；
 *   5. 安全响应头在每个应用上都在。
 *
 * 用法: node tools/smoke-frontends.mjs
 */
const ORIGIN = 'http://127.0.0.1'
// /generate/ 前端已退役（页面并入 /updatedel/，见 kms-generate/front/RETIRED.md），
// 不再纳入冒烟范围；其前端入口现由网关显式返回 404。
const APPS = ['updatedel', 'distribute', 'user', 'acceptance']
const REF = /(?:src|href)="([^"]*\/assets\/[^"]+)"/g

let fails = 0
const bad = (m) => { fails++; console.log('  ✗ ' + m) }
const ok = (m) => console.log('  ✓ ' + m)

for (const app of APPS) {
  console.log(`\n===== ${app} =====`)
  const idxUrl = `${ORIGIN}/${app}/index.html`
  const r = await fetch(idxUrl)
  if (!r.ok) { bad(`${idxUrl} → HTTP ${r.status}`); continue }
  const cc = r.headers.get('cache-control') || ''
  cc.includes('no-store') ? ok(`index.html no-store`) : bad(`index.html 缺少 no-store (${cc || '无'})`)
  for (const h of ['x-frame-options', 'x-content-type-options', 'content-security-policy']) {
    r.headers.get(h) ? null : bad(`index.html 缺少安全头 ${h}`)
  }
  const html = await r.text()

  const refs = [...html.matchAll(REF)].map((m) => m[1])
  if (!refs.length) { bad('index.html 里没有 /assets/ 引用'); continue }

  for (const ref of refs) {
    const url = ref.startsWith('/') ? ORIGIN + ref : `${ORIGIN}/${app}/${ref}`
    const a = await fetch(url)
    const ct = (a.headers.get('content-type') || '').split(';')[0].trim()
    const acc = a.headers.get('cache-control') || ''
    const isCss = ref.endsWith('.css')
    if (a.status !== 200) { bad(`${ref} → HTTP ${a.status}`); continue }
    if (isCss && ct !== 'text/css') { bad(`${ref} → Content-Type ${ct}（应为 text/css）`); continue }
    if (!isCss && !/javascript/.test(ct)) { bad(`${ref} → Content-Type ${ct}（HTML 冒充 JS）`); continue }
    if (!acc.includes('immutable')) bad(`${ref} → 缺少 immutable (${acc || '无'})`)
  }
  ok(`${refs.length} 个入口资源均可访问且类型正确`)

  // 缺失资源必须 404，不能是 200 HTML
  const miss = await fetch(`${ORIGIN}/${app}/assets/__definitely_missing__.js`)
  if (miss.status !== 404) bad(`缺失资源返回 ${miss.status}（应为 404）`)
  else if (!(miss.headers.get('cache-control') || '').includes('no-store')) bad('缺失资源的 404 未带 no-store')
  else ok('缺失资源 → 404 + no-store')

  // gzip：带 Accept-Encoding 请求入口 JS，应回 Content-Encoding: gzip
  const jsRef = refs.find((x) => x.endsWith('.js'))
  if (jsRef) {
    const g = await fetch(jsRef.startsWith('/') ? ORIGIN + jsRef : `${ORIGIN}/${app}/${jsRef}`, {
      headers: { 'Accept-Encoding': 'gzip' }
    })
    ;(g.headers.get('content-encoding') || '').includes('gzip')
      ? ok('入口 JS 走 gzip')
      : bad(`入口 JS 未压缩 (${g.headers.get('content-encoding') || '无 Content-Encoding'})`)
  }
}

console.log(`\n================ 汇总 ================`)
console.log(fails ? `失败 ${fails} 项` : '全部通过')
process.exit(fails ? 1 : 0)