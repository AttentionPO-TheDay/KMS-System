<template>
  <div class="top-right-btn" :style="style">
    <el-row>
      <el-tooltip class="item" effect="dark" :content="showSearch ? '隐藏搜索' : '显示搜索'" placement="top" v-if="search">
        <el-button size="small" circle icon="Search" @click="toggleSearch()" />
      </el-tooltip>
      <el-tooltip class="item" effect="dark" content="刷新" placement="top">
        <el-button size="small" circle icon="Refresh" @click="refresh()" />
      </el-tooltip>
      <el-tooltip class="item" effect="dark" content="显隐列" placement="top" v-if="columns">
        <el-button size="small" circle icon="Menu" @click="showColumn()" />
      </el-tooltip>
    </el-row>
    <el-dialog :title="title" v-model="open" append-to-body>
      <el-transfer
        :titles="['显示', '隐藏']"
        v-model="value"
        :data="columns"
        @change="dataChange"
      />
    </el-dialog>
  </div>
</template>

<script setup>
const props = defineProps({
  showSearch: {
    type: Boolean,
    default: true
  },
  columns: {
    type: Array
  },
  search: {
    type: Boolean,
    default: true
  },
  gutter: {
    type: Number,
    default: 10
  }
})

const emit = defineEmits(['update:showSearch', 'queryTable'])

const { proxy } = getCurrentInstance()
const open = ref(false)
const value = ref([])
const title = ref("显示/隐藏")

const style = computed(() => {
  const ret = {}
  if (props.gutter) {
    ret.marginRight = `${props.gutter / 2}px`
  }
  return ret
})

function toggleSearch() {
  emit('update:showSearch', !props.showSearch)
}

function refresh() {
  emit('queryTable')
}

function showColumn() {
  open.value = true
}

function dataChange(data) {
  for (let item of props.columns) {
    const key = item.key
    item.visible = !data.includes(key)
  }
}
</script>

<style lang="scss" scoped>
.top-right-btn {
  float: right;
}
</style>
