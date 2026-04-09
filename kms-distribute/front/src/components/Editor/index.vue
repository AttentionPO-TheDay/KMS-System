<template>
  <div class="editor-placeholder">
    <el-input v-model="content" type="textarea" :rows="6" v-bind="$attrs" />
  </div>
</template>

<script setup>
const props = defineProps({
  modelValue: {
    type: String,
    default: ''
  }
})

const emit = defineEmits(['update:modelValue'])

const content = computed({
  get: () => props.modelValue,
  set: value => emit('update:modelValue', value)
})
</script>
