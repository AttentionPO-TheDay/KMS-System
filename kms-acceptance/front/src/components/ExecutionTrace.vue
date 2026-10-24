<template>
  <section v-if="events.length || running" class="execution-trace" aria-label="后台执行终端">
    <header class="terminal-titlebar"><h4><span aria-hidden="true">&gt;_</span> 执行终端</h4><span class="terminal-mode">{{ running ? '运行中' : '执行记录' }}</span><button type="button" :disabled="!lines.length" @click="copy">{{ copyLabel }}</button><button type="button" :disabled="!lines.length" @click="download">下载日志</button></header>
    <div class="terminal-toolbar"><span>任务执行器 / 结构化日志</span><label><input v-model="follow" type="checkbox" @change="scrollToEnd">跟随输出</label></div>
    <div ref="viewport" class="terminal-viewport" tabindex="0" role="log" :aria-live="running ? 'polite' : 'off'" aria-label="任务执行日志" @scroll="onScroll">
      <div v-if="previous && running && lines.length" class="terminal-note">[RECORD] 以下为上次执行记录；本次请求仍在执行。</div>
      <div v-for="line in lines" :key="line.id" class="terminal-line" :class="line.state"><span v-if="line.time" class="log-time">[{{ line.time }}] </span><span class="log-tag">[{{ line.tag }}] </span><span class="log-message">{{ line.text }}</span></div>
      <div v-if="running" class="live-stage terminal-line"><span class="log-tag">[LIVE] </span><span>{{ stage || '请求已发出，等待服务端返回执行记录。' }}</span></div>
      <div v-else class="terminal-end">kms&gt; 执行记录结束<span class="cursor" aria-hidden="true">▌</span></div>
    </div>
    <p v-if="copyError" class="copy-error" role="status">{{ copyError }}</p>
    <details v-if="timeline.rows.length" class="worker-timeline"><summary>查看{{ workerUnit }}时间线</summary><div class="axis"><span>0 ms</span><span>{{ number(timeline.durationMs) }} ms</span></div><div v-for="(row, index) in timeline.rows" :key="row.worker" class="worker-row"><span :title="row.worker">{{ workerUnit }} {{ index + 1 }}<small>{{ row.spans.length }} 个任务</small></span><div class="worker-track"><span v-for="(span, i) in row.spans" :key="i" class="worker-span" :style="{ left: `${span.left}%`, width: `${span.width}%` }" :title="`${row.worker}: ${number(span.startMs)} → ${number(span.endMs)} ms`"></span></div></div></details>
  </section>
</template>

<script setup>
import { computed, nextTick, ref, watch } from 'vue'
import { workerTimeline } from '../utils/execution-trace.js'
import { terminalLines, terminalText } from '../utils/terminal-output.js'
const props = defineProps({ events: { type: Array, default: () => [] }, running: Boolean, previous: Boolean, stage: { type: String, default: '' }, spans: { type: Array, default: () => [] } })
const viewport = ref(null), follow = ref(true), copyLabel = ref('复制'), copyError = ref('')
const lines = computed(() => terminalLines(props.events, props.spans))
const timeline = computed(() => workerTimeline(props.spans))
const workerUnit = computed(() => props.spans.some(span => span.kind === 'process') ? '进程' : '线程')
const number = value => value.toLocaleString('zh-CN', { maximumFractionDigits: 2 })
const outputText = () => [props.previous && props.running ? '[RECORD] 上次执行记录' : '', terminalText(lines.value), props.running ? `[LIVE] ${props.stage || '等待服务端返回执行记录'}` : 'kms> 执行记录结束'].filter(Boolean).join('\n')
async function scrollToEnd() { await nextTick(); if (follow.value && viewport.value) viewport.value.scrollTop = viewport.value.scrollHeight }
function onScroll() { if (viewport.value && viewport.value.scrollHeight - viewport.value.scrollTop - viewport.value.clientHeight > 24) follow.value = false }
watch(() => [props.events, props.stage, props.spans, props.running], (_, old) => { copyLabel.value = '复制'; copyError.value = ''; if (props.running || old?.[3]) scrollToEnd() })
async function copy() { try { await navigator.clipboard.writeText(outputText()); copyLabel.value = '已复制'; copyError.value = '' } catch { copyError.value = '复制失败，可选中终端文本后复制。' } }
function download() { const url = URL.createObjectURL(new Blob([outputText()], { type: 'text/plain;charset=utf-8' })); const a = document.createElement('a'); a.href = url; a.download = 'kms-execution.log'; a.click(); URL.revokeObjectURL(url) }
</script>

<style scoped>
.execution-trace { --term-bg: oklch(16% .009 255); --term-panel: oklch(21% .01 255); --term-border: oklch(35% .014 255); --term-text: oklch(91% .009 255); --term-muted: oklch(72% .015 255); --term-cyan: oklch(83% .10 210); --term-green: oklch(85% .15 145); --term-red: oklch(80% .13 25); margin: 16px 0; min-width: 0; color: var(--term-text); border: 1px solid var(--term-border); border-radius: 5px; background: var(--term-bg); overflow: hidden; font: 12px/1.8 Consolas, 'Cascadia Mono', 'SFMono-Regular', 'Noto Sans SC', monospace; }
.terminal-titlebar { display: flex; flex-wrap: wrap; align-items: center; gap: 12px; padding: 8px 12px; background: var(--term-panel); border-bottom: 1px solid var(--term-border); }
h4 { margin: 0; font: inherit; font-weight: 600; color: var(--term-text); }h4 > span { color: var(--term-cyan); margin-right: 4px; }.terminal-mode { color: var(--term-muted); font-size: 11px; margin-right: auto; }
button { color: var(--term-text); background: transparent; border: 1px solid var(--term-border); border-radius: 3px; padding: 2px 8px; font: inherit; font-size: 11px; cursor: pointer; }button:hover:not(:disabled) { background: var(--term-border); }button:disabled { opacity: .5; cursor: default; }
button:focus-visible, input:focus-visible, summary:focus-visible, .terminal-viewport:focus-visible { outline: 2px solid var(--term-cyan); outline-offset: -2px; }
.terminal-toolbar { display: flex; flex-wrap: wrap; justify-content: space-between; gap: 8px; padding: 6px 12px; font-size: 11px; color: var(--term-muted); }.terminal-toolbar label { display: inline-flex; gap: 5px; align-items: center; cursor: pointer; }input { accent-color: var(--term-cyan); margin: 0; }
.terminal-viewport { min-height: 70px; max-height: 380px; overflow: auto; padding: 8px 14px 14px; scrollbar-color: var(--term-border) var(--term-bg); }
.terminal-line { white-space: pre-wrap; overflow-wrap: anywhere; font-variant-numeric: tabular-nums; }.log-time { color: var(--term-muted); }.log-tag { color: var(--term-cyan); }.data { color: var(--term-muted); }.data .log-tag { color: var(--term-muted); }.success .log-tag, .success .log-message { color: var(--term-green); }.failed .log-tag, .failed .log-message { color: var(--term-red); }.live-stage { color: var(--term-cyan); margin-top: 8px; }.terminal-note { color: var(--term-muted); margin-bottom: 8px; }.terminal-end { color: var(--term-muted); margin-top: 10px; }.cursor { margin-left: 6px; color: var(--term-text); }.copy-error { padding: 0 12px; color: var(--term-red); }
.worker-timeline { padding: 10px 12px; border-top: 1px solid var(--term-border); color: var(--term-muted); }summary { cursor: pointer; color: var(--term-cyan); }.axis { margin: 10px 0 4px 70px; display: flex; justify-content: space-between; font-size: 10px; }.worker-row { display: grid; grid-template-columns: 60px minmax(0, 1fr); gap: 10px; align-items: center; margin: 10px 0; }.worker-row small { display: block; font-size: 10px; }.worker-track { position: relative; height: 22px; background: var(--term-panel); }.worker-span { position: absolute; height: 14px; top: 4px; background: var(--term-cyan); box-shadow: inset 0 0 0 1px var(--term-bg); }
@media (max-width: 600px) { .terminal-titlebar { gap: 8px; padding: 8px; }.terminal-viewport { padding: 8px; max-height: 340px; }.terminal-toolbar { padding: 6px 8px; } }
</style>
