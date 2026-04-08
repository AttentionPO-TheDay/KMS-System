<template>
  <div v-if="!item.hidden" class="menu-wrapper">
    <template v-if="hasOneShowingChild(item.children, item) && (!onlyOneChild.children || onlyOneChild.noShowingChildren) && !item.alwaysShow">
      <sidebar-item-link v-if="onlyOneChild.meta" :to="resolvePath(onlyOneChild.path, onlyOneChild.query)">
        <el-menu-item :index="resolvePath(onlyOneChild.path)" :class="{ 'submenu-title-noDropdown': !isNest }">
          <svg-icon v-if="onlyOneChild.meta.icon" :icon-class="onlyOneChild.meta.icon" />
          <span v-if="onlyOneChild.meta.title">{{ onlyOneChild.meta.title }}</span>
        </el-menu-item>
      </sidebar-item-link>
    </template>

    <el-sub-menu v-else ref="subMenu" :index="resolvePath(item.path)" popper-append-to-body>
      <template #title>
        <svg-icon v-if="item.meta && item.meta.icon" :icon-class="item.meta.icon" />
        <span v-if="item.meta && item.meta.title">{{ item.meta.title }}</span>
      </template>
      <sidebar-item v-for="child in item.children" :key="child.path" :item="child" :is-nest="true" :base-path="resolvePath(child.path)" class="nest-menu" />
    </el-sub-menu>
  </div>
</template>

<script>
import path from 'path'
import { isExternal } from '@/utils/validate'
import SvgIcon from '@/components/SvgIcon'
import sidebarItemLink from './sidebarItemLink'

export default {
  name: 'SidebarItem',
  components: { SvgIcon, sidebarItemLink },
  props: {
    item: {
      type: Object,
      required: true
    },
    isNest: {
      type: Boolean,
      default: false
    },
    basePath: {
      type: String,
      default: ''
    }
  },
  data() {
    this.onlyOneChild = null
    return {}
  },
  methods: {
    hasOneShowingChild(children, parent) {
      if (!children) {
        children = []
      }
      const showingChildren = children.filter(item => {
        if (item.hidden) {
          return false
        } else {
          this.onlyOneChild = item
          return true
        }
      })

      if (showingChildren.length === 1) {
        return true
      }

      if (showingChildren.length === 0) {
        this.onlyOneChild = { ...parent, path: '', noShowingChildren: true }
        return true
      }

      return false
    },
    resolvePath(routePath, routeQuery) {
      if (isExternal(routePath)) {
        return routePath
      }
      if (isExternal(this.basePath)) {
        return this.basePath
      }
      if (routeQuery) {
        const query = JSON.parse(routeQuery)
        return { path: path.resolve(this.basePath, routePath), query: query }
      }
      return path.resolve(this.basePath, routePath)
    }
  }
}
</script>

<style lang="scss">
.el-sub-menu__title {
  padding: 0 !important;
}

.menu-wrapper {
  svg {
    margin-right: 12px;
  }
}
</style>
