<template>
  <div class="sidebar">
    <el-menu
      :default-active="activeMenu"
      :collapse="isCollapse"
      :background-color="scssVariables.menuBg"
      :text-color="scssVariables.menuText"
      :unique-opened="true"
      :active-text-color="scssVariables.menuActiveText"
      :collapse-transition="false"
      mode="vertical"
    >
      <sidebar-item
        v-for="route in sidebarRoutes"
        :key="route.path"
        :item="route"
        :base-path="route.path"
      />
    </el-menu>
  </div>
</template>

<script setup>
import SidebarItem from './SidebarItem'
import usePermissionStore from '@/store/modules/permission'
import useAppStore from '@/store/modules/app'

const route = useRoute()
const permissionStore = usePermissionStore()
const appStore = useAppStore()

const sidebarRoutes = computed(() => permissionStore.sidebarRouters)
const activeMenu = computed(() => {
  const { meta, path } = route
  if (meta.activeMenu) {
    return meta.activeMenu
  }
  return path
})

const isCollapse = computed(() => !appStore.sidebar.opened)

const scssVariables = {
  menuBg: '#304156',
  menuText: '#bfcbd9',
  menuActiveText: '#409EFF'
}
</script>

<style lang="scss" scoped>
.sidebar {
  height: 100%;
}
</style>
