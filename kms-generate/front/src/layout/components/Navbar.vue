<template>
  <div class="navbar">
    <hamburger v-if="hamburger" :is-active="sidebar.opened" class="hamburger-container" @toggleClick="toggleSideBar" />
    <breadcrumb v-if="hamburger" class="breadcrumb-container" />
    <topnav v-if="topNav" class="topnav-container" />
    <div class="right-menu">
      <search id="header-search" class="right-menu-item hover-effect" />
      <screenfull id="screenfull" class="right-menu-item hover-effect" />
      <size-select id="size-select" class="right-menu-item hover-effect" />
      <el-dropdown class="avatar-container right-menu-item hover-effect" trigger="click">
        <div class="avatar-wrapper">
          <img :src="userStore.avatar" class="user-avatar" />
          <el-icon><caret-bottom /></el-icon>
        </div>
        <template #dropdown>
          <el-dropdown-menu>
            <router-link to="/user/profile">
              <el-dropdown-item>个人中心</el-dropdown-item>
            </router-link>
            <el-dropdown-item divided command="logout">
              <span>退出登录</span>
            </el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
    </div>
  </div>
</template>

<script setup>
import Breadcrumb from './Sidebar/sidebarItem.vue'
import TopNav from '@/components/TopNav'
import Hamburger from '@/components/Hamburger'
import Screenfull from '@/components/Screenfull'
import SizeSelect from '@/components/SizeSelect'
import Search from '@/components/HeaderSearch'
import useUserStore from '@/store/modules/user'
import useAppStore from '@/store/modules/app'

const userStore = useUserStore()
const appStore = useAppStore()

const sidebar = computed(() => appStore.sidebar)
const topNav = computed(() => true)
const hamburger = computed(() => true)

function toggleSideBar() {
  appStore.toggleSideBar(false)
}
</script>

<style lang="scss" scoped>
.navbar {
  height: 50px;
  overflow: hidden;
  position: relative;
  background: #fff;
  box-shadow: 0 1px 4px rgba(0,21,41,.08);
  display: flex;
  align-items: center;

  .hamburger-container {
    line-height: 46px;
    height: 100%;
    float: left;
    cursor: pointer;
    transition: background .3s;
    -webkit-tap-highlight-color:transparent;

    &:hover {
      background: rgba(0, 0, 0, .025)
    }
  }

  .breadcrumb-container {
    float: left;
  }

  .topnav-container {
    float: left;
  }

  .right-menu {
    margin-left: auto;
    margin-right: 10px;
    display: flex;
    align-items: center;

    .right-menu-item {
      display: inline-block;
      padding: 0 8px;
      font-size: 18px;
      color: #5a5e66;
      vertical-align: text-bottom;

      &.hover-effect {
        cursor: pointer;
        transition: background .3s;

        &:hover {
          background: rgba(0, 0, 0, .025)
        }
      }
    }

    .avatar-container {
      margin-left: 8px;

      .avatar-wrapper {
        margin-top: 5px;
        position: relative;
        display: flex;
        align-items: center;

        .user-avatar {
          cursor: pointer;
          width: 40px;
          height: 40px;
          border-radius: 10px;
        }

        i {
          cursor: pointer;
          position: absolute;
          right: -20px;
          top: 25px;
          font-size: 12px;
        }
      }
    }
  }
}
</style>
