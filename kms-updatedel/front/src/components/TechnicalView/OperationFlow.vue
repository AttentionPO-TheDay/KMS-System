<template>
  <section v-if="trace.status !== 'idle'" class="operation-flow" aria-label="业务执行流程">
    <header>
      <div><h3>{{ titles[kind] }}执行流程</h3><span class="operation-count">已完成 {{ completed }} / {{ trace.stages.length }} 个步骤</span></div>
      <el-tag :type="types[trace.status]">{{ statuses[trace.status] }}</el-tag>
    </header>
    <dl class="operation-facts">
      <template v-for="(value, key) in trace.facts" :key="key">
        <dt>{{ labels[key] }}</dt><dd>{{ display(key, value) }}</dd>
      </template>
    </dl>
    <ol class="operation-stages" aria-label="执行步骤" aria-live="polite" aria-atomic="false">
      <li v-for="(stage, index) in trace.stages" :key="stage.id" :class="stage.status" :data-stage="stage.id" :data-status="stage.status"
          :aria-current="stage.status === 'running' ? 'step' : undefined">
        <span class="stage-index" aria-hidden="true">{{ stage.status === 'success' ? '✓' : index + 1 }}</span>
        <div class="stage-body">
          <div class="stage-heading"><h4>{{ stage.title }}</h4><el-tag size="small" :type="types[stage.status]">{{ stageStatuses[stage.status] }}</el-tag></div>
          <p v-if="stage.label" class="stage-detail">{{ stage.label }}</p>
          <dl v-if="stage.startedAt" class="stage-facts">
            <template v-for="key in stage.evidence.filter(key => stage.facts[key] !== undefined)" :key="key">
              <dt>{{ labels[key] }}</dt><dd>{{ display(key, stage.facts[key]) }}</dd>
            </template>
          </dl>
        </div>
        <time v-if="stage.startedAt" class="stage-time">{{ time(stage.startedAt) }}<span v-if="stage.finishedAt">{{ duration(stage) }}</span></time>
      </li>
    </ol>
    <el-collapse class="operation-history">
      <el-collapse-item name="events" :title="'执行记录（' + trace.events.length + ' 条）'">
        <ol class="operation-events">
          <li v-for="(event, index) in trace.events" :key="event.at + '-' + index">
            <time>{{ time(event.at) }}</time><span>{{ event.label }}</span>
          </li>
        </ol>
      </el-collapse-item>
    </el-collapse>
  </section>
</template>

<script setup>
import { computed } from 'vue'
const props = defineProps({ kind: { type: String, required: true }, trace: { type: Object, required: true } })
const titles = { preallocation: '预分配', distribution: '密钥分发', update: '密钥更新' }
const statuses = { running: '执行中', success: '已完成', partial: '部分完成', failed: '执行失败' }
const stageStatuses = { pending: '未开始', running: '处理中', success: '已完成', partial: '需处理', failed: '失败' }
const types = { pending: 'info', running: 'primary', success: 'success', partial: 'warning', failed: 'danger' }
const labels = { nodeId: '本节点', peerNodeId: '接收节点', algorithm: '算法', keyId: '密钥 ID',
  version: '当前版本', nextVersion: '目标版本', batchId: '批次 ID', poolId: '预分配池 ID',
  sessionId: '会话 ID', requested: '请求数量', prepared: '保护包数量', accepted: '入池成功',
  rejected: '入池失败', sessionStatus: '会话状态', keyStored: '本地材料已保存', expiresAt: '有效期至',
  generated: '已生成', wrapped: '已封装', signed: '已签名', uploaded: '已上传', remaining: '池剩余数量',
  selfTestOk: '自检通过', reused: '复用已封存材料', reconciled: '公钥与版本一致' }
const completed = computed(() => props.trace.stages.filter(stage => stage.status === 'success').length)
const time = value => new Date(value).toLocaleTimeString('zh-CN', { hour12: false })
const duration = stage => Math.max(0, new Date(stage.finishedAt) - new Date(stage.startedAt)) + ' ms'
function display(key, value) {
  if (typeof value === 'boolean') return value ? '是' : '否'
  if (key === 'sessionStatus') return ({ initiated: '待双方确认', established: '已建立', closed: '已关闭', revoked: '已撤销', expired: '已过期' })[value] || value
  return value
}
</script>

<style scoped>
.operation-flow { margin: 16px 0 24px; padding: 20px 24px; border: 1px solid var(--el-border-color); border-radius: 6px; }
header, .stage-heading { display: flex; align-items: center; justify-content: space-between; gap: 16px; }
h3, h4 { margin: 0; color: var(--el-text-color-primary); }
h3 { font-size: 17px; }
h4 { font-size: 14px; font-weight: 600; }
.operation-count { display: block; margin-top: 5px; color: var(--el-text-color-secondary); font-size: 12px; }
.operation-facts { display: grid; grid-template-columns: 110px minmax(0, 1fr) 110px minmax(0, 1fr); gap: 10px 16px; margin: 20px 0; font-size: 13px; }
dt { color: var(--el-text-color-secondary); }
dd { margin: 0; overflow-wrap: anywhere; font-variant-numeric: tabular-nums; }
ol { padding: 0; list-style: none; }
.operation-stages { margin: 20px 0 0; border-top: 1px solid var(--el-border-color-lighter); }
.operation-stages > li { display: grid; grid-template-columns: 30px minmax(0, 1fr) 86px; align-items: start; gap: 14px; padding: 17px 8px; border-bottom: 1px solid var(--el-border-color-lighter); }
.stage-index { display: grid; place-items: center; width: 26px; height: 26px; border: 1px solid var(--el-border-color); border-radius: 50%; color: var(--el-text-color-secondary); font-size: 12px; }
.running { background: var(--el-color-primary-light-9); }
.running .stage-index { border-color: var(--el-color-primary); color: var(--el-color-primary); }
.success .stage-index { background: var(--el-color-success-light-9); border-color: var(--el-color-success-light-5); color: var(--el-color-success); }
.failed .stage-index { border-color: var(--el-color-danger); color: var(--el-color-danger); }
.partial .stage-index { border-color: var(--el-color-warning); color: var(--el-color-warning); }
.stage-detail { margin: 8px 0 0; color: var(--el-text-color-regular); font-size: 13px; line-height: 1.6; }
.stage-facts { display: flex; flex-wrap: wrap; gap: 6px 10px; margin: 8px 0 0; font-size: 12px; }
.stage-facts dd { margin-right: 14px; }
.stage-time { padding-top: 5px; color: var(--el-text-color-secondary); font-size: 12px; text-align: right; font-variant-numeric: tabular-nums; }
.stage-time span { display: block; margin-top: 6px; }
.operation-history { margin-top: 16px; border: 0; }
.operation-events { margin: 0; font-size: 12px; }
.operation-events li { display: grid; grid-template-columns: 90px minmax(0, 1fr); gap: 12px; padding: 6px 0; }
.operation-events time { color: var(--el-text-color-secondary); }
</style>
