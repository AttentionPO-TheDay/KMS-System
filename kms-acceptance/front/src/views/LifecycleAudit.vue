<template>
  <section class="lifecycle-audit">
    <header class="audit-header">
      <div><h1>验收密钥生命周期</h1></div>
      <button class="btn-ghost" :disabled="loading" @click="refresh">{{ loading ? '读取中…' : '刷新记录' }}</button>
    </header>
    <nav class="audit-tabs" aria-label="测试分类">
      <button v-for="tab in tabs" :key="tab.id" :aria-pressed="scenario === tab.id" :class="{selected:scenario===tab.id}"
        @click="switchTab(tab.id)">{{ tab.label }}</button>
    </nav>
    <p v-if="error" class="audit-error" role="alert">{{ error }} <button class="btn-ghost" @click="refresh">重新读取</button></p>
    <section class="audit-panel" aria-label="测试批次">
      <div class="panel-heading"><h2>测试批次</h2><span>{{ list ? `共 ${list.total} 批` : '数据尚未取得' }}</span></div>
      <div v-if="loading && !list" class="empty" role="status">正在读取批次…</div>
      <div v-else-if="list && !list.items.length" class="empty">
        <strong>暂无生命周期记录</strong>
        <router-link to="/load-test">返回验收测试台</router-link>
      </div>
      <div v-else-if="list" class="table-scroll">
        <table><thead><tr><th>批次 ID</th><th>测试项目</th><th>执行结果</th><th>{{ symmetric ? '实际对称密钥回收速率（条/秒）' : scenario==='revoke-rate' ? '异常密钥回收率' : scenario==='revoke-tps' ? '实际自动回收速率' : '实际更新速率' }}</th><th>实际完成 / 待核查数</th><th>测试开始</th><th>明细</th></tr></thead>
          <tbody><tr v-for="batch in list.items" :key="batch.id" :class="{active:batch.id===selected}">
            <td class="identifier">{{ batch.id }}</td><td>{{ title(batch.scenarioId) }}</td><td>{{ statusText(batch.status) }}</td>
            <td>{{ scenario==='revoke-rate' ? (batch.evidenceSource ? rate(batch.completionRate) : '旧版口径，需重测') : format(batch.successfulTps) }}</td><td>{{ batch.completed }} / {{ batch.eligible }}</td><td>{{ time(batch.startedAt) }}</td>
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
          <div><span>{{ symmetric ? '到期SM4样本' : detail.batch.evidenceSource ? (detail.batch.scenarioId==='revoke-rate' ? '实际发起回收' : '已注入异常样本') : '初始有效，可核查' }}</span><strong>{{ format(detail.batch.eligible) }}</strong></div>
          <div><span>实际完成</span><strong>{{ format(detail.batch.completed) }}</strong></div>
          <div><span>仍未完成</span><strong>{{ format(detail.batch.pending) }}</strong></div>
          <div><span>缺失 / 未核验</span><strong>{{ format(detail.batch.unknown) }}</strong></div>
          <div><span>{{ symmetric ? '到期样本回收比例' : detail.batch.scenarioId==='update-tps' ? '版本更新完成率' : detail.batch.evidenceSource ? '异常密钥回收率' : '最终状态回收率' }}</span><strong>{{ rate(detail.batch.completionRate) }}</strong></div>
        </div>
        <dl class="audit-facts">
          <dt>核查口径</dt><dd>{{ symmetric ? '实际删除的独立到期SM4密钥数量 / 数据库回收耗时；未到期及保留状态对照不得删除。' : detail.batch.evidenceSource ? (detail.batch.scenarioId==='revoke-rate' ? '最终回收成功数 / 实际发起回收密钥数；已发起但失败的计入分母，与速率及固定秒数无关。' : '实际自动回收异常数 / 注入异常数；正常及仅告警对照不得被回收。') : detail.batch.scenarioId==='update-tps' ? '同一密钥的版本号高于测试前版本。' : '已回收数 / 初始有效数。' }}</dd>
          <template v-if="detail.batch.evidenceSource && !symmetric"><dt>异常样本 / 实际发起 / 未发起</dt><dd>{{ format(detail.batch.injected) }} / {{ format(detail.batch.attempted) }} / {{ format(detail.batch.notAttempted) }}</dd></template>
          <template v-if="symmetric"><dt>回收速率 / 耗时</dt><dd>{{ format(detail.batch.successfulTps) }} 条/秒 / {{ format(detail.batch.elapsedMs) }} ms，要求 ≥10000条/秒。计时包含数据库筛选、删除及提交，不含样本准备、回收后核验和临时表清理。</dd></template>
          <template v-else-if="detail.batch.evidenceSource"><dt>实际回收速率</dt><dd>{{ format(detail.batch.successfulTps) }} 条/秒，包含检测与依赖失效写入；不含样本准备、清理和链上确认。</dd></template>
          <template v-else-if="detail.batch.elapsedMs"><dt>实际更新速率</dt><dd>{{ format(detail.batch.successfulTps) }} 条/秒；版本实际变化数除以提交至最终状态核验耗时。</dd>
            <dt>固定更新数量 / 耗时</dt><dd>{{ format(detail.batch.poolSize) }} 把 / {{ format(detail.batch.elapsedMs) }} ms；请求受理速率 {{ format(detail.batch.acceptedTps) }} TPS。</dd></template>
          <template v-else><dt>接口吞吐</dt><dd>成功 {{ format(detail.batch.successfulTps) }} TPS；HTTP 请求 {{ format(detail.batch.httpRequests) }}，HTTP 错误 {{ format(detail.batch.httpErrors) }}，连接错误 {{ format(detail.batch.socketErrors) }}。</dd>
          <dt>测试配置</dt><dd>{{ detail.batch.threads }} 线程 · {{ detail.batch.connections }} 连接 · {{ detail.batch.durationSeconds }} 秒，速率目标 ≥ {{ format(detail.batch.targetTps) }} TPS</dd></template>
          <template v-if="detail.batch.scenarioId==='revoke-rate'"><dt>回收率目标</dt><dd>{{ detail.batch.evidenceSource ? '异常密钥回收率 ≥ 98%；本次实际发起回收的密钥作为分母。' : '旧版普通密钥回收口径，请重新执行异常密钥回收率测试。' }}</dd></template>
          <dt>快照时间</dt><dd>初始 {{ time(detail.batch.beforeAt) }}；核验 {{ time(detail.batch.observedAt) }}</dd>
          <dt>测试账户</dt><dd>{{ detail.batch.account }}</dd>
          <dt>排除密钥数</dt><dd>{{ detail.batch.excluded }}</dd>
          <template v-if="detail.batch.scenarioId!=='update-tps' && detail.batch.reason"><dt>核验结果</dt><dd>{{ detail.batch.reason }}</dd></template>
        </dl>
        <p v-if="detail.batch.error" class="audit-error" role="status">{{ detail.batch.error }}</p>
        <form class="detail-filters" @submit.prevent="queryDetails">
          <label>密钥 ID<input v-model="query" maxlength="64" /></label>
          <label>核查结果<select v-model="outcome"><option value="">全部</option><option value="COMPLETED">实际完成</option><option value="PENDING">仍未完成</option><option value="NOT_ATTEMPTED">未发起回收</option><option value="CONTROL_PASSED">对照通过</option><option value="CONTROL_FAILED">对照失败</option><option value="UNVERIFIED">未核验</option><option value="MISSING">记录缺失</option><option value="EXCLUDED">不计入完成率</option></select></label>
          <button class="btn-primary" :disabled="detailLoading">查询</button><button type="button" class="btn-ghost" :disabled="detailLoading" @click="showPending">查看仍未完成</button>
        </form>
        <div class="table-scroll" :aria-busy="detailLoading">
          <table><thead><tr><th>密钥 ID</th><th v-if="detail.batch.evidenceSource">{{ symmetric ? '资源 / 算法' : '异常依据 / 算法' }}</th><th>测试前状态</th><th>核验时状态</th><th>{{ symmetric ? '有效期' : '版本变化' }}</th><th>核查结果</th><th>{{ symmetric ? '快照时间' : '数据库更新时间' }}</th></tr></thead>
            <tbody><tr v-for="row in detail.items" :key="row.keyId"><td class="identifier">{{ row.keyId }}</td><td v-if="detail.batch.evidenceSource"><template v-if="symmetric"><span :title="row.keyHash">{{ row.poolId }} / {{ row.algorithm }}</span></template><template v-else>{{ row.anomalyRule || '正常对照' }} / {{ row.algorithm }}</template></td><td>{{ keyStatus(row.before?.status) }}</td><td>{{ row.after ? (row.after.exists ? keyStatus(row.after.status) : symmetric ? '已删除' : '记录不存在') : '未核验' }}</td>
              <td><template v-if="symmetric">{{ time(row.expiresAt) }}</template><template v-else>{{ row.before?.version ?? '未记录' }} → {{ row.after?.version ?? '未记录' }}</template></td><td><span :class="['outcome', row.outcome.toLowerCase()]">{{ outcomeText(row.outcome) }}</span></td><td>{{ time(row.after?.updatedAt) }}</td></tr></tbody></table>
          <p v-if="!detail.items.length" class="empty">没有符合筛选条件的密钥记录。</p>
        </div>
        <footer class="pager"><span>匹配 {{ format(detail.total) }} 把</span><label>每页<select v-model.number="detailSize" @change="queryDetails"><option :value="20">20</option><option :value="50">50</option><option :value="100">100</option></select></label>
          <button :disabled="detailLoading || detailPage<=1" @click="changeDetailPage(detailPage-1)">上一页</button><span>{{ detailPage }} / {{ Math.max(1,Math.ceil(detail.total/detailSize)) }}</span><button :disabled="detailLoading || detailPage*detailSize>=detail.total" @click="changeDetailPage(detailPage+1)">下一页</button></footer>
      </template>
    </section>
  </section>
</template>

<script setup>
import { onMounted, onBeforeUnmount, ref, computed } from 'vue'
import { useRoute } from 'vue-router'
import { acceptanceFetch } from '../api/demo-context'
const tabs=[{id:'update-tps',label:'更新测试'},{id:'revoke-tps',label:'异常回收测试'},{id:'revoke-rate',label:'异常密钥回收率'},{id:'symmetric-reclaim-tps',label:'对称密钥回收'}]
const route=useRoute()
const scenario=ref(tabs.some(t=>t.id===route.query.scenario)?route.query.scenario:'update-tps'),list=ref(null),page=ref(1),size=20,loading=ref(false),error=ref('')
const selected=ref(''),detail=ref(null),detailPage=ref(1),detailSize=ref(20),detailLoading=ref(false),detailError=ref(''),query=ref(''),outcome=ref('')
let listRevision=0,detailRevision=0
const symmetric=computed(()=>scenario.value==='symmetric-reclaim-tps')
const title=id=>tabs.find(t=>t.id===id)?.label || id
const format=v=>Number(v||0).toLocaleString('zh-CN',{maximumFractionDigits:2})
const rate=v=>v==null?'尚不可核定':`${format(v)}%`
const time=v=>!v?'未记录':Number.isNaN(new Date(v).getTime())?String(v):new Date(v).toLocaleString('zh-CN',{hour12:false})
const keyStatus=v=>({'0':'有效','1':'已冻结','2':'更新中','3':'已回收',ACTIVE:'有效',REVOKED:'已回收'})[v]||v||'未记录'
const statusText=v=>({running:'执行中',preparing:'准备中',verifying:'核验中',passed:'已通过',failed_threshold:'未达标',failed:'执行失败',cancelled:'已取消'})[v]||v
const outcomeText=v=>({COMPLETED:'实际完成',PENDING:'仍未完成',NOT_ATTEMPTED:'未发起回收',CONTROL_PASSED:'对照通过',CONTROL_FAILED:'对照失败',UNVERIFIED:'未核验',MISSING:'记录缺失',EXCLUDED:'不计入完成率'})[v]||v
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
