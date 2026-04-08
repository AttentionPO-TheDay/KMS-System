<template>
  <el-menu
    :default-active="activeMenu"
    :background-color="scssVariables.menuBg"
    :text-color="scssVariables.menuText"
    :unique-opened="false"
    :active-text-color="scssVariables.menuActiveText"
    :collapse-transition="false"
    mode="vertical"
  >
    <sidebar-item
      v-for="route in sidebarRouters"
      :key="route.path"
      :item="route"
      :base-path="route.path"
    />
  </el-menu>
</template>

<script>
import { computed } from 'vue'
import SidebarItem from './SidebarItem'
import variables from '@/assets/styles/variables.module.scss'

export default {
  components: { SidebarItem },
  computed: {
    sidebarRouters() {
      return []
    },
    activeMenu() {
      const route = useRoute()
      const { meta, path } = route
      if (meta.activeMenu) {
        return meta.activeMenu
      }
      return path
    },
    scssVariables() {
      return variables
    }
  }
}
</script>

<style lang="scss">
.el-menu {
  border: none;
  height: 100%;
  width: 100% !important;
}
</style>
