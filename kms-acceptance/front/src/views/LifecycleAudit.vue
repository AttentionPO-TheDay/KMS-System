<template>
  <section class="lifecycle-audit">
    <header class="audit-header">
      <div><p class="eyebrow">ACCEPTANCE / LIFECYCLE AUDIT</p><h1>验收密钥生命周期</h1>
        <p class="description">按测试批次追溯更新和回收，只展示验收专用密钥元数据。</p></div>
      <button class="btn-ghost" :disabled="loading" @click="refresh">{{ loading ? '读取中…' : '刷新记录' }}</button>
    </header>
    <p class="scope-note">这里保留测试前后快照，不改变密钥。仅当前管理员会话及版本可见；升级前未记录的历史状态不会补造。</p>
    <nav class="audit-tabs" aria-label="测试分类">
      <button v-for="tab in tabs" :key="tab.id" :aria-pressed="scenario === tab.id" :class="{selected:scenario===tab.id}"
        @click="switchTab(tab.id)">{{ tab.label }}</button>
    </nav>
    <p v-if="error" class="audit-error" role="alert">{{ error }} <button class="btn-ghost" @click="refresh">重新读取</button></p>
    <section class="audit-panel" aria-label="测试批次">
      <div class="panel-heading"><h2>测试批次</h2><span>{{ list ? `共 ${list.total} 批` : '数据尚未取得' }}</span></div>
      <div v-if="loading && !list" class="empty" role="status">正在读取批次…</div>
      <div v-else-if="list && !list.items.length" class="empty">
        <strong>尚无此类生命周期快照</strong><p>升级后执行更新或回收测试，才会记录逐把密钥的前后状态。旧测试仅保留原有汇总结果。</p>
        <router-link to="/load-test">返回验收测试台</router-link>
      </div>
      <div v-else-if="list" class="table-scroll">
        <table><thead><tr><th>批次 ID</th><th>测试项目</th><th>执行结果</th><th>接口成功 TPS</th><th>实际完成 / 待核查数</th><th>测试开始</th><th>明细</th></tr></thead>
          <tbody><tr v-for="batch in list.items" :key="batch.id" :class="{active:batch.id===selected}">
            <td class="identifier">{{ batch.id }}</td><td>{{ title(batch.scenarioId) }}</td><td>{{ statusText(batch.status) }}</td>
            <td>{{ format(batch.successfulTps) }}</td><td>{{ batch.completed }} / {{ batch.eligible }}</td><td>{{ time(batch.startedAt) }}</td>
            <td><button class="text-button" :aria-expanded="batch.id===selected" @click="selectBatch(batch.id)">查看明细</button></td>
          </tr></tbody></table>
      </div>
      <footer v-if="list" class="pager"><span>每页 {{ size }} 批</span><button :disabled="loading || page<=1" @click="changePage(page-1)">上一页</button>
        <span>{{ page }} / {{ Math.max(1, Math.ceil(list.total/size)) }}</span><button :disabled="loading || page*size>=list.total" @click="changePage(page+1)">下一页</button></footer>
    </section>

    <section v-if="selected" class="audit-panel details-panel" aria-label="批次状态变化">
      <div class="panel-heading"><h2>{{ detail ? title(detail.batch.scenarioId) : '批次明细' }}</h2><span class="identifier">{{ selected }}</span></div>
      <p v-if="detailError" class="audit-error" role="alert">{{ detailError }}</p>
      <p v-if="detailLoading && !detail" class="empty" role="status">正在读取密钥快照…</p>
      <template v-if="detail">
        <div class="audit-metrics" aria-label="批次统计">
          <div><span>候选密钥池</span><strong>{{ format(detail.batch.poolSize) }}</strong></div>
          <div><span>初始有效，可核查</span><strong>{{ format(detail.batch.eligible) }}</strong></div>
          <div><span>实际完成</span><strong>{{ format(detail.batch.completed) }}</strong></div>
          <div><span>仍未完成</span><strong>{{ format(detail.batch.pending) }}</strong></div>
          <div><span>缺失 / 未核验</span><strong>{{ format(detail.batch.unknown) }}</strong></div>
          <div><span>{{ detail.batch.scenarioId==='update-tps' ? '版本更新完成率' : '最终状态回收率' }}</span><strong>{{ rate(detail.batch.completionRate) }}</strong></div>
        </div>
        <dl class="audit-facts">
          <dt>核查口径</dt><dd>{{ detail.batch.scenarioId==='update-tps' ? '同一 keyId 的版本号高于测试前版本，不使用旧有 chain_status=1 冒充更新完成。' : '测试前有效的密钥中，核验时 status=3 的数量 / 初始有效数量。' }}</dd>
          <dt>原始吞吐</dt><dd>接口成功 {{ format(detail.batch.successfulTps) }} TPS；HTTP 请求 {{ format(detail.batch.httpRequests) }}，HTTP 错误 {{ format(detail.batch.httpErrors) }}，连接错误 {{ format(detail.batch.socketErrors) }}。这不是数据库完成速率。</dd>
          <dt>测试配置</dt><dd>{{ detail.batch.threads }} 线程 · {{ detail.batch.connections }} 连接 · {{ detail.batch.durationSeconds }} 秒，速率目标 ≥ {{ format(detail.batch.targetTps) }} TPS</dd>
          <template v-if="detail.batch.scenarioId==='revoke-rate'"><dt>回收率目标</dt><dd>最终状态回收率严格大于 98%；核验不可用或初始有效数量为零时，不能判定通过。</dd></template>
          <dt>快照时间</dt><dd>初始 {{ time(detail.batch.beforeAt) }}；核验 {{ time(detail.batch.observedAt) }}</dd>
          <dt>测试说明</dt><dd>测试账户 {{ detail.batch.account }}，业务域 acceptance；初始非有效密钥 {{ detail.batch.excluded }} 把不计入完成率。{{ detail.batch.scenarioId!=='update-tps' ? detail.batch.reason : '' }}</dd>
        </dl>
        <p v-if="detail.batch.error" class="audit-error" role="status">{{ detail.batch.error }}</p>
        <form class="detail-filters" @submit.prevent="queryDetails">
          <label>密钥 ID<input v-model="query" maxlength="64" placeholder="可部分匹配" /></label>
          <label>核查结果<select v-model="outcome"><option value="">全部</option><option value="COMPLETED">实际完成</option><option value="PENDING">仍未完成</option><option value="UNVERIFIED">未核验</option><option value="MISSING">记录缺失</option><option value="EXCLUDED">不计入完成率</option></select></label>
          <button class="btn-primary" :disabled="detailLoading">查询</button><button type="button" class="btn-ghost" :disabled="detailLoading" @click="showPending">查看仍未完成</button>
        </form>
        <div class="table-scroll" :aria-busy="detailLoading">
          <table><thead><tr><th>密钥 ID</th><th>测试前状态</th><th>核验时状态</th><th>版本变化</th><th>核查结果</th><th>数据库更新时间</th></tr></thead>
            <tbody><tr v-for="row in detail.items" :key="row.keyId"><td class="identifier">{{ row.keyId }}</td><td>{{ keyStatus(row.before?.status) }}</td><td>{{ row.after ? (row.after.exists ? keyStatus(row.after.status) : '记录不存在') : '未核验' }}</td>
              <td>{{ row.before?.version ?? '未记录' }} → {{ row.after?.version ?? '未记录' }}</td><td><span :class="['outcome', row.outcome.toLowerCase()]">{{ outcomeText(row.outcome) }}</span></td><td>{{ time(row.after?.updatedAt) }}</td></tr></tbody></table>
          <p v-if="!detail.items.length" class="empty">没有符合筛选条件的密钥记录。</p>
        </div>
        <footer class="pager"><span>匹配 {{ format(detail.total) }} 把</span><label>每页<select v-model.number="detailSize" @change="queryDetails"><option :value="20">20</option><option :value="50">50</option><option :value="100">100</option></select></label>
          <button :disabled="detailLoading || detailPage<=1" @click="changeDetailPage(detailPage-1)">上一页</button><span>{{ detailPage }} / {{ Math.max(1,Math.ceil(detail.total/detailSize)) }}</span><button :disabled="detailLoading || detailPage*detailSize>=detail.total" @click="changeDetailPage(detailPage+1)">下一页</button></footer>
        <p class="scope-note">这是本次压测候选池的观测快照。wrk 会轮询复用 keyId，汇总请求数不等于独立密钥数；没有逐项 HTTP 回执时，不推断每把密钥实际提交了几次。刷新只读已归档快照，不重新回收或更改验收结论。</p>
      </template>
    </section>
  </section>
</template>

<script setup>
import { onMounted, onBeforeUnmount, ref } from 'vue'
import { acceptanceFetch } from '../api/demo-context'
const tabs=[{id:'update-tps',label:'更新测试'},{id:'revoke-tps',label:'异常回收测试'},{id:'revoke-rate',label:'最终回收率'}]
const scenario=ref('update-tps'),list=ref(null),page=ref(1),size=20,loading=ref(false),error=ref('')
const selected=ref(''),detail=ref(null),detailPage=ref(1),detailSize=ref(20),detailLoading=ref(false),detailError=ref(''),query=ref(''),outcome=ref('')
let listRevision=0,detailRevision=0
const title=id=>tabs.find(t=>t.id===id)?.label || id
const format=v=>Number(v||0).toLocaleString('zh-CN',{maximumFractionDigits:2})
const rate=v=>v==null?'尚不可核定':`${format(v)}%`
const time=v=>!v?'未记录':Number.isNaN(new Date(v).getTime())?String(v):new Date(v).toLocaleString('zh-CN',{hour12:false})
const keyStatus=v=>({'0':'有效','1':'已冻结','2':'更新中','3':'已回收'})[v]||v||'未记录'
const statusText=v=>({running:'执行中',preparing:'准备中',verifying:'核验中',passed:'已通过',failed_threshold:'未达标',failed:'执行失败',cancelled:'已取消'})[v]||v
const outcomeText=v=>({COMPLETED:'实际完成',PENDING:'仍未完成',UNVERIFIED:'未核验',MISSING:'记录缺失',EXCLUDED:'不计入完成率'})[v]||v
async function loadList(){const current=++listRevision;loading.value=true;error.value='';try{
  const params=new URLSearchParams({scenario:scenario.value,page:String(page.value),pageSize:String(size)})
  const data=await acceptanceFetch(`/acceptance/lifecycle?${params}`)
  if(current!==listRevision)return;list.value=data;page.value=data.page
}catch(e){if(current===listRevision){list.value=null;error.value=e.message||'批次数据不可用'}}finally{if(current===listRevision)loading.value=false}}
async function loadDetails(){const current=++detailRevision;detailLoading.value=true;detailError.value='';try{
  const params=new URLSearchParams({page:String(detailPage.value),pageSize:String(detailSize.value),q:query.value,outcome:outcome.value})
  const data=await acceptanceFetch(`/acceptance/lifecycle/${selected.value}?${params}`)
  if(current!==detailRevision)return;detail.value=data;detailPage.value=data.page
}catch(e){if(current===detailRevision){detail.value=null;detailError.value=e.message||'密钥快照不可用'}}finally{if(current===detailRevision)detailLoading.value=false}}
function switchTab(id){scenario.value=id;page.value=1;list.value=null;selected.value='';detail.value=null;detailRevision++;return loadList()}
function changePage(v){page.value=v;return loadList()}
function selectBatch(id){selected.value=id;detail.value=null;query.value='';outcome.value='';detailPage.value=1;return loadDetails()}
function changeDetailPage(v){detailPage.value=v;return loadDetails()}
function queryDetails(){detailPage.value=1;return loadDetails()}
function showPending(){outcome.value='PENDING';return queryDetails()}
async function refresh(){await loadList();if(selected.value)await loadDetails()}
onMounted(loadList)
onBeforeUnmount(()=>{listRevision++;detailRevision++})
</script>

<style scoped>
.lifecycle-audit{max-width:1280px;margin:0 auto;color:var(--kms-text-primary);min-width:0}.audit-header{display:flex;justify-content:space-between;align-items:center;gap:24px;margin-bottom:16px}.eyebrow{color:var(--kms-brand-text);font-size:.75rem;font-weight:600;margin:0 0 8px}h1{font-size:1.75rem;margin:0}h2{font-size:1rem;margin:0}.description{font-size:.875rem;color:var(--kms-text-secondary);margin:8px 0 0}.scope-note{font-size:.8125rem;line-height:1.7;color:var(--kms-text-secondary);margin:16px 0}.audit-tabs{display:flex;flex-wrap:wrap;gap:8px;margin:20px 0}.audit-tabs button,.pager button{background:var(--kms-surface-1);color:var(--kms-text-primary);border:1px solid var(--kms-border);border-radius:4px;padding:8px 12px;cursor:pointer}.audit-tabs .selected{color:var(--kms-brand-text);background:var(--kms-brand-subtle);border-color:var(--kms-brand)}button:focus-visible,a:focus-visible{outline:2px solid var(--kms-brand);outline-offset:2px}button:disabled{opacity:.55;cursor:not-allowed}.audit-panel{border:1px solid var(--kms-border);background:var(--kms-surface-1);border-radius:6px;margin-bottom:20px;min-width:0}.panel-heading{display:flex;align-items:center;flex-wrap:wrap;gap:16px;padding:16px 20px}.panel-heading span{font-size:.8125rem;color:var(--kms-text-secondary)}.table-scroll{overflow-x:auto}table{border-collapse:collapse;width:100%;min-width:920px;font-size:.8125rem}th,td{text-align:left;padding:12px 16px;border-bottom:1px solid var(--kms-border);white-space:nowrap}th{background:var(--kms-surface-2);color:var(--kms-text-secondary);font-weight:600}tbody tr.active{background:var(--kms-brand-subtle)}.identifier{font-family:ui-monospace,Consolas,monospace;font-size:.8125rem}.text-button{border:0;background:transparent;color:var(--kms-brand-text);font:inherit;cursor:pointer}.pager{display:flex;align-items:center;justify-content:flex-end;flex-wrap:wrap;gap:12px;padding:12px 20px;font-size:.8125rem}.pager>span:first-child{margin-right:auto}.empty{padding:24px 20px;color:var(--kms-text-secondary);font-size:.875rem;line-height:1.7}.empty p{max-width:65ch}.audit-error{color:var(--kms-danger-strong);font-size:.875rem;padding:12px 20px;line-height:1.6;overflow-wrap:anywhere}.audit-metrics{display:flex;flex-wrap:wrap;gap:20px 32px;padding:16px 20px;border-top:1px solid var(--kms-border);border-bottom:1px solid var(--kms-border)}.audit-metrics div{min-width:120px;flex:1}.audit-metrics span{display:block;font-size:.8125rem;color:var(--kms-text-secondary)}.audit-metrics strong{display:block;margin-top:8px;font-size:1.375rem;font-variant-numeric:tabular-nums}.audit-facts{display:grid;grid-template-columns:100px minmax(0,1fr);gap:12px 16px;padding:16px 20px;margin:0;font-size:.8125rem;line-height:1.7}.audit-facts dt{color:var(--kms-text-secondary)}.audit-facts dd{margin:0;overflow-wrap:anywhere}.detail-filters{display:flex;flex-wrap:wrap;align-items:flex-end;gap:12px;padding:12px 20px;border-top:1px solid var(--kms-border)}.detail-filters label{display:flex;flex-direction:column;gap:6px;font-size:.8125rem;color:var(--kms-text-secondary)}input,select{font:inherit;background:var(--kms-surface-1);color:var(--kms-text-primary);border:1px solid var(--kms-border);border-radius:4px;min-height:36px;padding:6px 10px;box-sizing:border-box}input:focus-visible,select:focus-visible{outline:2px solid var(--kms-brand);outline-offset:1px}.outcome{font-weight:600}.outcome.completed{color:var(--kms-success-strong)}.outcome.pending,.outcome.unverified,.outcome.missing{color:var(--kms-warning-strong)}.details-panel>.scope-note{padding:0 20px}.audit-facts,.scope-note{max-width:100ch}@media(max-width:700px){.audit-header{align-items:flex-start;flex-direction:column;gap:12px}h1{font-size:1.5rem}.panel-heading,.pager,.audit-metrics,.detail-filters,.audit-facts{padding-left:12px;padding-right:12px}.audit-facts{grid-template-columns:76px minmax(0,1fr)}.audit-metrics{gap:16px}.audit-metrics div{min-width:100px}.detail-filters label{flex:1 1 140px}.detail-filters input,.detail-filters select{max-width:100%;width:100%}.panel-heading .identifier{overflow-wrap:anywhere}}@media(pointer:coarse){button{min-height:44px}}
</style>
