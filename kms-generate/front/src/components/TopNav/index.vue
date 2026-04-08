<template>
  <el-menu mode="horizontal" :default-active="activeMenu" :ellipsis="false">
    <template v-for="item in topbarRouters">
      <el-menu-item :key="item.path" :index="item.path" v-if="!item.children">{{ item.meta?.title }}</el-menu-item>
    </template>
  </el-menu>
</template>

<script>
export default {
  name: 'TopNav',
  computed: {
    topbarRouters() {
      return []
    },
    activeMenu() {
      const route = useRoute()
      return route.path
    }
  }
}
</script>
