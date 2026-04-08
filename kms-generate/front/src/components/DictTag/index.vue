<template>
  <div>
    <el-tag :type="dictType">{{ label }}</el-tag>
  </div>
</template>

<script>
export default {
  name: 'DictTag',
  props: {
    data: {
      type: Object,
      required: true
    },
    type: {
      type: String,
      default: 'default'
    }
  },
  computed: {
    label() {
      return this.data.label
    },
    dictType() {
      return this.type || this.data.type || 'default'
    }
  }
}
</script>
