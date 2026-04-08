<template>
  <el-dropdown trigger="click" @command="handleSetSize">
    <div>
      <svg-icon icon-class="size" />
    </div>
    <template #dropdown>
      <el-dropdown-menu>
        <el-dropdown-item v-for="item of sizeOptions" :key="item.value" :command="item.value" :disabled="size === item.value">
          {{ item.label }}
        </el-dropdown-item>
      </el-dropdown-menu>
    </template>
  </el-dropdown>
</template>

<script>
export default {
  name: 'SizeSelect',
  data() {
    return {
      sizeOptions: [
        { label: '默认', value: 'default' },
        { label: '中等', value: 'medium' },
        { label: '小型', value: 'small' }
      ]
    }
  },
  computed: { size() { return useAppStore().size } },
  methods: {
    handleSetSize(size) {
      useAppStore().setSize(size)
      location.reload()
    }
  }
}
</script>
