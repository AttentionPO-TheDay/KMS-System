<template>
  <div>
    <span class="header-search">
      <el-input v-model="search" placeholder="搜索" @keyup.enter="handleSearch" />
    </span>
  </div>
</template>

<script>
export default {
  name: 'HeaderSearch',
  data() { return { search: '' } },
  methods: {
    handleSearch() {
      if (this.search) {
        this.$router.push({ path: '/search', query: { q: this.search } })
      }
    }
  }
}
</script>
