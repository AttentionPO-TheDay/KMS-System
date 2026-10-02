<template>
  <div :class="classObj" class="app-wrapper" :style="{ '--current-color': theme }">
    <div v-if="device === 'mobile' && sidebar.opened && !hideSidebar" class="drawer-bg" @click="handleClickOutside"/>
    <sidebar v-if="!sidebar.hide && !hideSidebar" class="sidebar-container" />
    <div :class="{ hasTagsView: needTagsView, sidebarHide: sidebar.hide || hideSidebar }" class="main-container">
      <div :class="{ 'fixed-header': fixedHeader }">
        <navbar :hide-sidebar="hideSidebar" @setLayout="setLayout" />
        <tags-view v-if="needTagsView" />
      </div>
      <app-main />
      <settings ref="settingRef" />
    </div>
  </div>
</template>

<script setup>
import { useWindowSize } from '@vueuse/core'
import Sidebar from './components/Sidebar/index.vue'
import { AppMain, Navbar, Settings, TagsView } from './components'
import defaultSettings from '@/settings'

import useAppStore from '@/store/modules/app'
import useSettingsStore from '@/store/modules/settings'

const settingsStore = useSettingsStore()
const route = useRoute()
const theme = computed(() => settingsStore.theme);
const sideTheme = computed(() => settingsStore.sideTheme);
const sidebar = computed(() => useAppStore().sidebar);
const device = computed(() => useAppStore().device);
const needTagsView = computed(() => settingsStore.tagsView);
const fixedHeader = computed(() => settingsStore.fixedHeader);

/**
 * 整页不显示侧边栏（路由 `meta.hideSidebar`）。
 *
 * 目前只有节点端的**工作台**会带上这个标记：它是刚进入时的主页面，
 * 整页都在展示子系统入口与节点的数据，旁边再挂一列菜单会与内容争注意力。
 *
 * ⚠️ 标记是**按主体**打的（见 store/modules/permission.js 的 generateRoutes）——
 *    只有 NODE 的工作台会带，管理端不受影响。
 *    这里只负责"读标记"，不负责"判断谁该有标记"，避免同一件事两处判。
 *
 * ⚠️ 别把它当通用开关：侧边栏是这套界面的主导航，
 *    除"主页面"之外的页面隐藏它，用户就失去了定位手段。
 */
const hideSidebar = computed(() => route.meta.hideSidebar === true)

const classObj = computed(() => ({
  hideSidebar: !sidebar.value.opened || hideSidebar.value,
  openSidebar: sidebar.value.opened && !hideSidebar.value,
  withoutAnimation: sidebar.value.withoutAnimation,
  mobile: device.value === 'mobile'
}))

const { width, height } = useWindowSize();
const WIDTH = 992; // refer to Bootstrap's responsive design

watch(() => device.value, () => {
  if (device.value === 'mobile' && sidebar.value.opened) {
    useAppStore().closeSideBar({ withoutAnimation: false })
  }
})

watchEffect(() => {
  if (width.value - 1 < WIDTH) {
    useAppStore().toggleDevice('mobile')
    useAppStore().closeSideBar({ withoutAnimation: true })
  } else {
    useAppStore().toggleDevice('desktop')
  }
})

function handleClickOutside() {
  useAppStore().closeSideBar({ withoutAnimation: false })
}

const settingRef = ref(null);
function setLayout() {
  settingRef.value.openSetting();
}
</script>

<style lang="scss" scoped>
  @import "@/assets/styles/mixin.scss";
  @import "@/assets/styles/variables.module.scss";

.app-wrapper {
  @include clearfix;
  position: relative;
  height: 100%;
  width: 100%;

  &.mobile.openSidebar {
    position: fixed;
    top: 0;
  }
}

.drawer-bg {
  background: #000;
  opacity: 0.3;
  width: 100%;
  top: 0;
  height: 100%;
  position: absolute;
  z-index: 999;
}

.fixed-header {
  position: fixed;
  top: 0;
  right: 0;
  z-index: 9;
  width: calc(100% - #{$base-sidebar-width});
  transition: width 0.28s;
}

.hideSidebar .fixed-header {
  width: calc(100% - 54px);
}

.sidebarHide .fixed-header {
  width: 100%;
}

.mobile .fixed-header {
  width: 100%;
}
</style>