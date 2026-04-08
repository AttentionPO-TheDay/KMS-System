<template>
  <div class="top-right-btn" :style="style">
    <el-row>
      <el-tooltip class="item" effect="dark" :content="showSearch ? '隐藏搜索' : '显示搜索'" placement="top" v-if="search">
        <el-button size="mini" circle icon="Search" @click="toggleSearch()" />
      </el-tooltip>
      <el-tooltip class="item" effect="dark" content="刷新" placement="top">
        <el-button size="mini" circle icon="Refresh" @click="refresh()" />
      </el-tooltip>
      <el-tooltip class="item" effect="dark" content="显隐列" placement="top" v-if="columns">
        <el-button size="mini" circle icon="Menu" @click="showColumn()" />
      </el-tooltip>
    </el-row>
    <el-dialog :title="title" v-model="open" append-to-body>
      <el-transfer :data="columns" v-model="visibleColumns" :titles="['隐藏', '显示']" @change="dataChange"></el-transfer>
    </el-dialog>
  </div>
</template>

<script>
export default {
  name: 'RightToolbar',
  props: {
    showSearch: {
      type: Boolean,
      default: true
    },
    search: {
      type: Boolean,
      default: true
    },
    columns: {
      type: Array
    },
    style: {
      type: String,
      default: 'margin-right: 10px'
    }
  },
  emits: ['update:showSearch', 'queryTable', 'change'],
  data() {
    return {
      open: false,
      title: '显示/隐藏',
      visibleColumns: []
    }
  },
  methods: {
    toggleSearch() {
      this.$emit('update:showSearch', !this.showSearch)
    },
    refresh() {
      this.$emit('queryTable')
    },
    showColumn() {
      this.open = true
    },
    dataChange(data) {
      this.$emit('change', data)
    }
  }
}
</script>

<style lang="scss" scoped>
.top-right-btn {
  float: right;
}
</style>
