<template>
  <main class="admin-data app-container">
    <header class="data-header">
      <div>
        <p class="eyebrow">密钥数据 / 管理员只读</p>
        <h1>{{ config.title }}</h1>
        <p class="page-description">{{ config.description }}</p>
      </div>
      <div class="header-actions">
        <span class="updated-at">{{ loadedAt ? `更新于 ${loadedAt}` : '尚未取得数据' }}</span>
        <el-button icon="Refresh" :loading="loading" @click="load()">刷新数据</el-button>
      </div>
    </header>

    <el-tabs v-if="section === 'keys'" v-model="keySpace" class="space-tabs" @tab-change="switchSpace">
      <el-tab-pane label="节点密钥" name="keys" />
      <el-tab-pane label="验收压测记录" name="acceptance" />
    </el-tabs>
    <p v-if="kind === 'acceptance'" class="dataset-notice">
      专用测试账户 {{ result?.account || 'acceptance_user' }} · 与节点密钥分开统计。这里只展示已入库记录，HTTP 压测速率不等于落库或上链完成速率。
      <a href="/acceptance/#/lifecycle">查看更新与回收测试批次</a>
    </p>

    <section class="metrics-strip" aria-label="全量数据统计" :aria-busy="loading">
      <div v-for="metric in metrics" :key="metric.label" class="metric">
        <span>{{ metric.label }}</span><strong>{{ metric.value }}</strong>
      </div>
    </section>
    <div v-if="kind === 'keys' && typeCounts.length" class="type-strip" aria-label="算法分布">
      <span class="strip-label">算法分布</span>
      <button v-for="item in typeCounts" :key="item.algorithm" type="button"
        :class="{ selected: filters.algorithm === item.algorithm }" @click="selectAlgorithm(item.algorithm)">
        {{ algorithmName(item.algorithm) }} <b>{{ number(item.count) }}</b>
      </button>
    </div>
    <div v-if="kind === 'distribution' && result" class="range-strip">
      <span class="strip-label">分发范围</span>
      <span>同域 {{ number(result?.summary?.byRange?.same || 0) }}</span>
      <span>跨域 {{ number(result?.summary?.byRange?.cross || 0) }}</span>
      <span>混合 {{ number(result?.summary?.byRange?.mixed || 0) }}</span>
    </div>

    <section class="records-panel" aria-label="筛选与记录明细">
      <div class="records-heading">
        <h2>{{ config.recordTitle }}</h2>
        <span>全量统计与筛选结果分开显示 · 仅查询元数据</span>
      </div>
      <el-form class="filter-bar" label-position="top" @submit.prevent="search">
        <el-form-item :label="config.searchLabel">
          <el-input v-model="filters.q" clearable :placeholder="config.searchLabel" maxlength="128" />
        </el-form-item>
        <el-form-item v-if="kind !== 'acceptance'" label="节点">
          <el-input v-model="filters.node" clearable placeholder="节点标识，可部分匹配" maxlength="64" />
        </el-form-item>
        <el-form-item v-if="config.algorithms" label="算法 / 保护方式">
          <el-select v-model="filters.algorithm" clearable placeholder="全部算法">
            <el-option v-for="algorithm in config.algorithms" :key="algorithm" :label="algorithmName(algorithm)" :value="algorithm" />
          </el-select>
        </el-form-item>
        <el-form-item label="状态">
          <el-select v-model="filters.status" clearable placeholder="全部状态">
            <el-option v-for="status in config.statuses" :key="status" :label="stateText(status)" :value="status" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="kind === 'distribution'" label="分发范围">
          <el-select v-model="filters.range" clearable placeholder="全部范围">
            <el-option label="同域" value="same" /><el-option label="跨域" value="cross" /><el-option label="混合" value="mixed" />
          </el-select>
        </el-form-item>
        <el-form-item label="创建日期">
          <el-date-picker v-model="filters.dates" type="daterange" value-format="YYYY-MM-DD"
            start-placeholder="开始日期" end-placeholder="结束日期" range-separator="至" :editable="false" />
        </el-form-item>
        <div class="filter-actions">
          <el-button type="primary" native-type="submit" :loading="loading">查询</el-button>
          <el-button :disabled="loading" @click="reset">重置</el-button>
        </div>
      </el-form>
      <div class="result-bar">
        <div>
          <strong>{{ loading ? '正在读取…' : result ? `匹配 ${number(result.total)} 条` : '数据尚不可用' }}</strong>
          <span v-if="kind === 'keys'">{{ filters.status === 'ACTIVE' ? '当前默认仅看有效密钥' : '按当前条件查看版本记录' }}</span>
        </div>
        <el-button v-if="kind === 'keys'" link type="primary" :disabled="loading" @click="toggleHistory">
          {{ filters.status === 'ACTIVE' ? '查看全部历史版本' : '仅看当前有效' }}
        </el-button>
      </div>

      <div v-if="error" class="source-error" role="alert">
        <strong>数据源暂时不可用</strong><span>{{ error }}</span><el-button @click="load()">重新读取</el-button>
      </div>
      <el-skeleton v-else-if="loading && !result" :rows="7" animated class="table-skeleton" />
      <el-table v-else v-loading="loading" :data="result?.items || []" :row-key="rowKey"
        stripe class="records-table" :aria-label="config.recordTitle">
        <el-table-column type="expand" width="44">
          <template #default="scope">
            <dl class="record-details">
              <template v-for="item in detailItems(scope.row)" :key="item.label">
                <dt>{{ item.label }}</dt><dd>{{ item.value }}</dd>
              </template>
            </dl>
          </template>
        </el-table-column>
        <el-table-column v-for="column in config.columns" :key="column.key" :label="column.label"
          :min-width="column.width || 120" show-overflow-tooltip>
          <template #default="scope">
            <el-tag v-if="column.kind === 'status'" :type="statusTone(scope.row[column.key])" effect="light" disable-transitions>
              {{ stateText(scope.row[column.key]) }}
            </el-tag>
            <el-tag v-else-if="column.kind === 'chain'" :type="chainTone(scope.row)" effect="plain" disable-transitions>
              {{ chainText(scope.row) }}
            </el-tag>
            <span v-else :class="{ 'identifier': column.kind === 'id' }">{{ cell(scope.row, column) }}</span>
          </template>
        </el-table-column>
        <template #empty>
          <div class="empty-state"><strong>没有符合条件的{{ config.recordTitle }}</strong>
            <span>{{ kind === 'acceptance' ? '测试结果需经异步消费后入库；也可以清除筛选条件再查询。' : '调整节点、状态或时间范围后重新查询。' }}</span>
          </div>
        </template>
      </el-table>
      <footer class="table-footer">
        <span>{{ result?.source || '查询只读元数据，不展示密钥材料' }}</span>
        <el-pagination :current-page="page" :page-size="pageSize" :page-sizes="[20, 50, 100]" :total="result?.total || 0"
          :disabled="loading" :pager-count="5" layout="total, sizes, prev, pager, next"
          @current-change="changePage" @size-change="changeSize" />
      </footer>
    </section>
  </main>
</template>

<script setup>
import { computed, onBeforeUnmount, reactive, ref, watch } from 'vue'
import http, { unwrap } from '@/api/pqkds/http'
import { chainEvidenceText } from '@/utils/node-chain-evidence'
import { protectionLabel } from '@/utils/protection-algorithms'

const props = defineProps({ section: { type: String, required: true } })
const keySpace = ref('keys')
const kind = computed(() => props.section === 'keys' ? keySpace.value : props.section)
const column = (key, label, width, kind) => ({ key, label, width, kind })
const configs = {
  keys: { title: '密钥总览', description: '核查节点密钥的当前状态、历史版本与链上存证。', recordTitle: '密钥版本记录', searchLabel: '密钥 ID',
    algorithms: ['SM2', 'SSCL', 'KYBER', 'FALCON_CL_V1', 'FALCON'], statuses: ['ACTIVE', 'PENDING', 'RETIRED', 'REVOKED', 'EXPIRED', 'LEGACY'],
    columns: [column('keyId','密钥 ID',240,'id'), column('nodeId','所属节点',130), column('algorithm','算法',240,'algorithm'),
      column('version','版本',75), column('status','密钥状态',110,'status'), column('chainBinding','上链存证',160,'chain'), column('createdAt','创建时间',180,'date')] },
  acceptance: { title: '密钥总览', description: '验收压测记录与节点业务数据分开查询。', recordTitle: '验收压测记录', searchLabel: '记录 ID',
    algorithms: ['SSCL', 'SM2'], statuses: ['0','1','2','3'],
    columns: [column('keyId','记录 ID',120,'id'), column('userName','所属测试账户',180), column('algorithm','算法',120,'algorithm'),
      column('keyName','测试标记',180), column('version','版本',75), column('status','密钥状态',110,'status'), column('chainStatus','上链状态',130,'chain'), column('createdAt','入库记录时间',180,'date')] },
  pool: { title: '预分配池', description: '查看保护包的可取用、占用与消费情况，追溯关联密钥和会话。', recordTitle: '预分配池项', searchLabel: '池批次 / 关联密钥 ID',
    algorithms: ['kyber_kem','falcon_cl_v1','gm_sm2','gm_sscl'], statuses: ['READY','RESERVED','CONSUMED','REVOKED','EXPIRED'],
    columns: [column('poolId','池批次',220,'id'),column('keyIndex','序号',75),column('sourceNode','来源节点',130),column('targetNode','目标节点',130),
      column('wrappingAlgorithm','保护算法',240,'algorithm'),column('payloadAlgorithm','载荷算法',130,'algorithm'),column('status','池项状态',110,'status'),column('expiresAt','过期时间',180,'date')] },
  sessions: { title: '会话数据', description: '核查发起与接收节点、保护方式和会话有效期。', recordTitle: '会话记录', searchLabel: '会话 ID',
    algorithms: ['gm_sm2','gm_sscl','kyber_kem','falcon_cl_v1','aes_falcon'], statuses: ['initiated','established','blockchain_recorded','expired','revoked'],
    columns: [column('sessionId','会话 ID',230,'id'),column('sourceNode','发起节点',140),column('targetNode','接收节点',140),column('sessionType','保护方式',240,'algorithm'),
      column('status','会话状态',130,'status'),column('createdAt','创建时间',180,'date'),column('expiresAt','过期时间',180,'date')] },
  distribution: { title: '分发批次', description: '按真实批次核查分发结果、接收节点与跨域范围。', recordTitle: '分发批次', searchLabel: '批次 ID',
    statuses: ['success','partial','failed','pending'],
    columns: [column('batchId','批次 ID',230,'id'),column('distributionType','范围',90,'range'),column('sourceNode','发起节点',130),column('receiverNode','接收节点',190),
      column('status','分发结果',120,'status'),column('nodeSuccessCount','成功节点 / 次数',145),column('wrappingAlgorithm','保护算法',220,'algorithm'),column('createdAt','创建时间',180,'date')] }
}
const config = computed(() => configs[kind.value])
const loading = ref(false), result = ref(null), error = ref(''), loadedAt = ref('')
const page = ref(1), pageSize = ref(20)
const filters = reactive({ q:'', node:'', algorithm:'', status:'', range:'', dates:[] })
const number = value => value == null ? '不可用' : Number(value).toLocaleString('zh-CN')
const total = () => result.value?.summary?.total
const count = (...states) => result.value ? states.reduce((sum, state) => sum + (result.value.summary?.byStatus?.[state] || 0), 0) : null
const metrics = computed(() => {
  const sets = {
    keys: [['版本记录总数',total()],['当前有效',count('ACTIVE')],['待启用',count('PENDING')],['已被取代',count('RETIRED')],['已回收 / 过期',count('REVOKED','EXPIRED')]],
    acceptance: [['已入库记录',total()],['有效记录',count('0')],['冻结 / 更新中',count('1','2')],['已回收',count('3')],['已上链记录',result.value?.summary?.chainCounts?.['1'] ?? (result.value ? 0 : null)]],
    pool: [['池项总数',total()],['可取用',count('READY','unused')],['占用中',count('RESERVED')],['已消费',count('CONSUMED','used','distributed')],['失效 / 过期',count('REVOKED','EXPIRED','expired')]],
    sessions: [['会话总数',total()],['已发起',count('initiated')],['已建立',count('established')],['已上链',count('blockchain_recorded')],['过期 / 撤销',count('expired','revoked')]],
    distribution: [['批次总数',total()],['全部成功',count('success')],['部分成功',count('partial')],['失败',count('failed')],['进行中',count('pending')]]
  }
  return (sets[kind.value] || []).map(([label,value])=>({label,value:number(value)}))
})
const typeCounts = computed(() => Object.entries(result.value?.summary?.byType || {}).map(([algorithm,count])=>({algorithm,count})))
const algorithmName = algorithm => ({ FALCON:'标准 Falcon（会话签名）', falcon:'标准 Falcon（会话签名）',
  kyber:'改进型双份额密钥封装（实验版 v1）', falcon_lattice:'Falcon（历史保护方式）',
  sm2:'SM2',sscl:'SSCL',sm4:'SM4-GCM',aes_256:'AES-256-GCM',aes_falcon:'AES + 标准 Falcon 签名' })[algorithm] || protectionLabel(algorithm)
const stateText = state => ({ ACTIVE:'有效',PENDING:'待启用',RETIRED:'已被取代',REVOKED:'已回收',EXPIRED:'已过期',LEGACY:'历史记录',
  READY:'可取用',RESERVED:'占用中',CONSUMED:'已消费',unused:'可取用（历史）',used:'已消费（历史）',distributed:'已分发（历史）',
  initiated:'已发起',established:'已建立',blockchain_recorded:'已上链',expired:'已过期',revoked:'已撤销',
  success:'全部成功',partial:'部分成功',failed:'失败',pending:'进行中', '0':'有效','1':'已冻结','2':'更新中','3':'已回收' })[state] || state || '未知'
const statusTone = state => ['ACTIVE','READY','established','blockchain_recorded','success','0'].includes(state) ? 'success'
  : ['failed','REVOKED','revoked','3'].includes(state) ? 'danger' : ['PENDING','RESERVED','pending','partial','initiated','1','2'].includes(state) ? 'warning' : 'info'
const chainText = row => kind.value === 'acceptance' ? (row.chainStatus==='1' && row.txId && Number(row.blockHeight)>0 ? '已上链' : ({'0':'等待上链','1':'待核验存证','2':'上链失败'})[row.chainStatus] || '未知') : chainEvidenceText(row.chainBinding)
const chainTone = row => chainText(row)==='已上链' ? 'success' : chainText(row).includes('失败') ? 'danger' : 'info'
const formatTime = value => !value ? '—' : Number.isNaN(new Date(value).getTime()) ? String(value) : new Date(value).toLocaleString('zh-CN',{hour12:false})
const cell = (row,c) => c.kind==='algorithm' ? algorithmName(row[c.key]) : c.kind==='date' ? formatTime(row[c.key])
  : c.kind==='range' ? ({same:'同域',cross:'跨域',mixed:'混合'})[row[c.key]] || '—' : row[c.key] ?? '—'
const rowKey = row => String(row.rowId || row.sessionId || row.batchId || `${row.keyId}:${row.version}`)
function detailItems(row) {
  const binding = row.chainBinding || row
  return [
    ['记录标识',row.keyId || row.poolId || row.sessionId || row.batchId],['完整算法标识',row.algorithm || row.wrappingAlgorithm || row.sessionType],
    ['安全级别',row.securityLevel],['生成方案',row.generationScheme],['关联长期密钥',row.longTermKeyId],['关联密钥版本',row.longTermKeyVersion],
    ['关联会话',row.sessionId],['来源域',row.sourceDomain],['目标域',(row.targetDomains || []).join('、') || row.targetDomain],
    ['交易哈希',binding.txId],['区块高度',binding.blockHeight],['存证错误',binding.lastError],
    ['创建时间',formatTime(row.createdAt)],['过期时间',row.expiresAt && formatTime(row.expiresAt)]
  ].filter(([,value])=>value!==undefined && value!==null && value!=='').map(([label,value])=>({label,value}))
}
let revision = 0
async function load() {
  const current = ++revision
  loading.value = true; error.value = ''
  try {
    const response = await http.get('/security-monitor/records/', {params:{section:kind.value,page:page.value,pageSize:pageSize.value,
      q:filters.q,node:filters.node,algorithm:filters.algorithm,status:filters.status,range:filters.range,
      from:filters.dates?.[0] || '',to:filters.dates?.[1] || ''}}).then(unwrap)
    if (current!==revision) return
    result.value=response;page.value=response.page
    loadedAt.value=new Date().toLocaleTimeString('zh-CN',{hour12:false})
  } catch (failure) {
    if (current!==revision) return
    result.value=null;loadedAt.value='';error.value=failure.message || '请检查服务连接后重试。'
  } finally { if(current===revision) loading.value=false }
}
function search(){page.value=1;return load()}
function reset(){Object.assign(filters,{q:'',node:'',algorithm:'',status:kind.value==='keys'?'ACTIVE':'',range:'',dates:[]});return search()}
function switchSpace(){result.value=null;return reset()}
function toggleHistory(){filters.status=filters.status==='ACTIVE'?'':'ACTIVE';return search()}
function selectAlgorithm(value){filters.algorithm=filters.algorithm===value?'':value;return search()}
function changePage(value){page.value=value;return load()}
function changeSize(value){pageSize.value=value;return search()}
watch(()=>props.section,()=>{keySpace.value='keys';result.value=null;reset()},{immediate:true})
onBeforeUnmount(()=>{revision++})
</script>

<style scoped>
.admin-data { --data-border: var(--el-border-color-light); --data-muted: var(--kms-text-secondary,var(--el-text-color-secondary)); color:var(--kms-text-primary,var(--el-text-color-primary)); min-width:0; padding:20px 24px; }
.data-header { display:flex; align-items:center; justify-content:space-between; gap:20px; margin-bottom:20px; }
.eyebrow { color:var(--data-muted); font-size:.75rem; margin:0 0 6px; }
h1 { font-size:1.5rem; font-weight:650; line-height:1.3; margin:0; }
.page-description { margin:8px 0 0; color:var(--data-muted); font-size:.875rem; }
.header-actions { display:flex; align-items:center; gap:12px; flex-shrink:0; }
.updated-at { font-size:.75rem; color:var(--data-muted); }
.space-tabs { margin-bottom:12px; }
.dataset-notice { padding:12px 16px; border:1px solid var(--data-border); background:var(--el-fill-color-light); border-radius:6px; font-size:.8125rem; line-height:1.7; margin:0 0 16px; }
.metrics-strip { display:flex; flex-wrap:wrap; align-items:center; padding:16px 0; border-top:1px solid var(--data-border); border-bottom:1px solid var(--data-border); gap:24px 40px; margin-bottom:16px; }
.metric { min-width:110px; display:flex; flex-direction:column; gap:6px; }
.metric span { font-size:.8125rem; color:var(--data-muted); }
.metric strong { font-size:1.375rem; font-weight:650; font-variant-numeric:tabular-nums; }
.type-strip,.range-strip { display:flex; flex-wrap:wrap; align-items:center; gap:8px 16px; margin-bottom:20px; font-size:.8125rem; }
.strip-label { color:var(--data-muted); }
.type-strip button { border:1px solid var(--data-border); border-radius:4px; padding:6px 10px; background:var(--el-bg-color); color:inherit; cursor:pointer; font:inherit; }
.type-strip button b { margin-left:8px; font-variant-numeric:tabular-nums; }
.type-strip button.selected { color:var(--el-color-primary); border-color:var(--el-color-primary); background:var(--el-color-primary-light-9); }
.type-strip button:focus-visible { outline:2px solid var(--el-color-primary); outline-offset:2px; }
.records-panel { background:var(--kms-surface-1,var(--el-bg-color)); border:1px solid var(--data-border); border-radius:8px; min-width:0; }
.records-heading { display:flex; align-items:center; flex-wrap:wrap; gap:12px; padding:16px 20px 4px; }
h2 { font-size:1rem; font-weight:600; margin:0; }
.records-heading span { font-size:.75rem; color:var(--data-muted); }
.filter-bar { display:flex; flex-wrap:wrap; align-items:flex-end; gap:12px; padding:12px 20px 16px; }
.filter-bar :deep(.el-form-item) { margin:0; width:180px; }
.filter-bar :deep(.el-form-item__label) { font-size:.8125rem; line-height:20px; margin-bottom:6px; }
.filter-bar :deep(.el-select) { width:100%; }
.filter-bar :deep(.el-form-item:has(.el-date-editor)) { width:280px; }
.filter-bar :deep(.el-date-editor) { width:100%; max-width:100%; }
.filter-actions { display:flex; gap:8px; }
.filter-actions :deep(.el-button + .el-button) { margin-left:0; }
.result-bar { display:flex; align-items:center; justify-content:space-between; gap:12px; padding:10px 20px; border-top:1px solid var(--data-border); background:var(--el-fill-color-lighter); font-size:.8125rem; }
.result-bar span { margin-left:12px; color:var(--data-muted); }
.records-table { font-size:.8125rem; font-variant-numeric:tabular-nums; width:100%; }
.records-table :deep(.cell) { white-space:nowrap; }
.records-table :deep(th.el-table__cell) { background:var(--el-fill-color-light); font-weight:600; }
.records-table :deep(.el-table__cell) { padding:10px 0; }
.identifier { font-family:ui-monospace,Consolas,monospace; font-size:.8125rem; }
.record-details { display:grid; grid-template-columns:130px minmax(0,1fr); gap:10px 16px; margin:0; padding:20px 40px; font-size:.8125rem; background:var(--el-fill-color-lighter); }
.record-details dt { color:var(--data-muted); }
.record-details dd { margin:0; overflow-wrap:anywhere; }
.table-footer { display:flex; align-items:center; justify-content:space-between; flex-wrap:wrap; gap:12px; padding:16px 20px; border-top:1px solid var(--data-border); }
.table-footer > span { font-size:.75rem; color:var(--data-muted); max-width:65ch; line-height:1.6; }
.source-error { display:flex; flex-wrap:wrap; gap:12px; align-items:center; padding:24px 20px; color:var(--el-color-danger); }
.source-error span { font-size:.875rem; }
.table-skeleton { padding:24px; }
.empty-state { display:flex; flex-direction:column; gap:8px; padding:32px 16px; line-height:1.6; }
.empty-state strong { font-size:.875rem; color:var(--el-text-color-primary); }
.empty-state span { font-size:.8125rem; color:var(--data-muted); }
@media(max-width:900px) { .data-header { align-items:flex-start; flex-direction:column; gap:12px; } .header-actions { width:100%; justify-content:space-between; } .metrics-strip { gap:20px 32px; } }
@media(max-width:600px) { .admin-data { padding:16px 12px; } .metrics-strip { gap:16px; } .metric { flex:1 1 120px; } .filter-bar { padding:12px; } .filter-bar :deep(.el-form-item) { width:calc(50% - 6px); min-width:0; } .filter-bar :deep(.el-form-item:first-child),.filter-bar :deep(.el-form-item:has(.el-date-editor)) { width:100%; } .records-heading,.result-bar,.table-footer { padding-left:12px; padding-right:12px; } .result-bar { flex-wrap:wrap; } .result-bar span { display:block; margin:6px 0 0; } .table-footer { overflow-x:auto; } .record-details { grid-template-columns:90px minmax(0,1fr); padding:16px; } }
@media(pointer:coarse) { .type-strip button { min-height:44px; } }
</style>
