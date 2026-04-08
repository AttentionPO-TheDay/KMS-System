<template>
  <div :class="{'hidden': hidden}" class="pagination-container">
    <el-pagination
      :background="background"
      :current-page.sync="currentPage"
      :page-size.sync="pageSize"
      :layout="layout"
      :page-sizes="pageSizes"
      :pager-count="pagerCount"
      :total="total"
      v-bind="$attrs"
      @size-change="handleSizeChange"
      @current-change="handleCurrentChange"
    />
  </div>
</template>

<script>
import { computed } from 'vue'

export default {
  name: 'Pagination',
  props: {
    total: {
      required: true,
      type: Number
    },
    page: {
      type: Number,
      default: 1
    },
    limit: {
      type: Number,
      default: 10
    },
    pageSizes: {
      type: Array,
      default() {
        return [10, 20, 30, 50]
      }
    },
    pagerCount: {
      type: Number,
      default: document.body.clientWidth < 992 ? 5 : 7
    },
    layout: {
      type: String,
      default: 'total, sizes, prev, pager, next, jumper'
    },
    background: {
      type: Boolean,
      default: true
    },
    autoScroll: {
      type: Boolean,
      default: true
    },
    hidden: {
      type: Boolean,
      default: false
    }
  },
  emits: ['update:page', 'update:limit', 'pagination', 'size-change', 'current-change'],
  setup(props, { emit }) {
    const currentPage = computed({
      get() {
        return props.page
      },
      set(val) {
        emit('update:page', val)
      }
    })
    const pageSize = computed({
      get() {
        return props.limit
      },
      set(val) {
        emit('update:limit', val)
      }
    })
    function handleSizeChange(val) {
      if (props.page * val > props.total) {
        currentPage.value = 1
      }
      emit('pagination', { page: currentPage.value, limit: val })
      emit('size-change', val)
    }
    function handleCurrentChange(val) {
      emit('pagination', { page: val, limit: props.limit })
      emit('current-change', val)
    }
    return {
      currentPage,
      pageSize,
      handleSizeChange,
      handleCurrentChange
    }
  }
}
</script>

<style lang="scss" scoped>
.pagination-container {
  background: #fff;
  padding: 32px 16px;
}

.pagination-container.hidden {
  display: none;
}
</style>
