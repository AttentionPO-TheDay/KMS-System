<template>
  <span>{{ currentLabel }}</span>
</template>

<script setup>
const props = defineProps({
  options: {
    type: Array,
    default: () => []
  },
  value: {
    type: [String, Number],
    default: ''
  }
})

const currentLabel = computed(() => {
  const match = props.options.find(item => String(item.value) === String(props.value))
  return match ? match.label : props.value
})
</script>
