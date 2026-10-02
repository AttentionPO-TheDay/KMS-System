<template>
  <div :class="{ 'has-logo': showLogo }" class="sidebar-container">
    <logo v-if="showLogo" :collapse="isCollapse" />
    <el-scrollbar wrap-class="scrollbar-wrapper">
      <el-menu
        :default-active="activeMenu"
        :collapse="isCollapse"
        :background-color="getMenuBackground"
        :text-color="getMenuTextColor"
        :unique-opened="true"
        :active-text-color="theme"
        :collapse-transition="false"
        mode="vertical"
        :class="sideTheme"
      >
        <sidebar-item
          v-for="(route, index) in sidebarRouters"
          :key="route.path + index"
          :item="route"
          :base-path="route.path"
        />
      </el-menu>
    </el-scrollbar>
  </div>
</template>

<script setup>
import Logo from './Logo'
import SidebarItem from './SidebarItem'
import variables from '@/assets/styles/variables.module.scss'
import useAppStore from '@/store/modules/app'
import useSettingsStore from '@/store/modules/settings'
import usePermissionStore from '@/store/modules/permission'
import useUserStore from '@/store/modules/user'
import { PRINCIPAL_NODE, resolvePrincipalType } from '@/utils/principal'
import { findOwningZone, isBusinessZone } from '@/utils/subsystems'

const route = useRoute();
const appStore = useAppStore()
const settingsStore = useSettingsStore()
const permissionStore = usePermissionStore()
const userStore = useUserStore()

/**
 * 侧边栏展示的路由。
 *
 * 节点端有一条额外收敛：**进入某个业务子系统后，只显示该子系统那一棵**。
 * 需求原话是"每个子系统进去后侧边栏只有该系统的功能"——三个业务主线
 * 各管密钥生命周期的一段，混在一列里看不出边界。
 *
 * 判断"当前在哪个子系统"用顶层条目的 `menuId`（后端随 router 下发），
 * 不用 path/title —— 那两个会被迁移改名，改名后判断会**静默失效**。
 *
 * 三种情形：
 *   1. 不在任何业务子系统内（门户、工作台、节点信息、引导页）
 *      → 显示完整节点树。否则用户在节点信息页会看不到任何菜单，
 *        连工作台都回不去。
 *   2. 在业务子系统内 → 只显示该子系统那一棵
 *   3. 管理端 → 原样显示（不动）
 */
const sidebarRouters = computed(() => {
  const all = permissionStore.sidebarRouters || []
  const principal = resolvePrincipalType({
    principalType: userStore.principalType,
    roleLevel: userStore.roleLevel
  })
  if (principal !== PRINCIPAL_NODE) {
    return all
  }
  const zone = findOwningZone(all, route.path)
  if (!zone || !isBusinessZone(zone.menuId)) {
    return all
  }
  return [zone]
});

const showLogo = computed(() => settingsStore.sidebarLogo);
const sideTheme = computed(() => settingsStore.sideTheme);
const theme = computed(() => settingsStore.theme);
const isCollapse = computed(() => !appStore.sidebar.opened);

// 获取菜单背景色
const getMenuBackground = computed(() => {
  if (settingsStore.isDark) {
    return 'var(--sidebar-bg)';
  }
  return sideTheme.value === 'theme-dark' ? variables.menuBg : variables.menuLightBg;
});

// 获取菜单文字颜色
const getMenuTextColor = computed(() => {
  if (settingsStore.isDark) {
    return 'var(--sidebar-text)';
  }
  return sideTheme.value === 'theme-dark' ? variables.menuText : variables.menuLightText;
});

const activeMenu = computed(() => {
  const { meta, path } = route;
  if (meta.activeMenu) {
    return meta.activeMenu;
  }
  return path;
});
</script>

<style lang="scss" scoped>
.sidebar-container {
  background-color: v-bind(getMenuBackground);
  
  .scrollbar-wrapper {
    background-color: v-bind(getMenuBackground);
  }

  .el-menu {
    border: none;
    height: 100%;
    width: 100% !important;
    
    .el-menu-item, .el-sub-menu__title {
      &:hover {
        background-color: var(--menu-hover, rgba(0, 0, 0, 0.06)) !important;
      }
    }

    .el-menu-item {
      color: v-bind(getMenuTextColor);
      
      &.is-active {
        color: var(--menu-active-text, #409eff);
        background-color: var(--menu-hover, rgba(0, 0, 0, 0.06)) !important;
      }
    }

    .el-sub-menu__title {
      color: v-bind(getMenuTextColor);
    }
  }
}
</style>
