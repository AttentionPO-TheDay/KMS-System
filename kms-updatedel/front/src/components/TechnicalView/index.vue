<template>
  <OperationFlow :kind="kind" :trace="operation" />
</template>

<script setup>
import { reactive } from 'vue'
import OperationFlow from './OperationFlow.vue'
import {
  createTechnicalTrace, startTechnicalTrace, recordTechnicalTrace,
  setTechnicalStage, progressTechnicalStage, finishTechnicalTrace
} from '@/utils/technical-operation-trace'

const props = defineProps({ kind: { type: String, required: true } })
const operation = reactive(createTechnicalTrace())

defineExpose({
  start: (values, options = {}) => startTechnicalTrace(operation, values, options.mode === 'pool' ? 'pool' : props.kind),
  stage: (id, status, label, values) => setTechnicalStage(operation, id, status, label, values),
  progress: (id, values) => progressTechnicalStage(operation, id, values),
  record: (label, values) => recordTechnicalTrace(operation, label, values),
  finish: (status, label, values) => finishTechnicalTrace(operation, status, label, values)
})
</script>
