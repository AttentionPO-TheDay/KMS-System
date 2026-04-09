<template>
  <div class="navbar">
    <hamburger v-if="false" id="hamburger-container" :is-active="sidebar.opened" class="hamburger-container" @toggleClick="toggleSideBar" />

    <breadcrumb v-if="false" id="breadcrumb-container" class="breadcrumb-container" />

    <topnav v-if="false" id="topnav-container" class="topnav-container" />

    <div class="right-menu">
      <template v-if="device !== 'mobile'">
        <search id="header-search" class="right-menu-item" />

        <el-tooltip content="文档" effect="dark" placement="bottom">
          <Doc v-if="false" id="guide-doc" class="right-menu-item hover-effect" />
        </el-tooltip>

        <el-tooltip content="全屏" effect="dark" placement="bottom">
          <screenfull id="screenfull" class="right-menu-item hover-effect" />
        </el-tooltip>

        <el-tooltip content="布局大小" effect="dark" placement="bottom">
          <size-select id="size-select" class="right-menu-item hover-effect" />
        </el-tooltip>
      </template>

      <div class="right-menu-item hover-effect">
        <span>{{ name }}</span>
      </div>

      <div class="right-menu-item hover-effect">
        <el-dropdown @command="handleCommand">
          <span class="el-dropdown-link">
            <span>{{ roles[0] || '用户' }}</span>
            <el-icon class="el-icon--right">
              <arrow-down />
            </el-icon>
          </span>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="userProfile" divided>
                <span>个人中心</span>
              </el-dropdown-item>
              <el-dropdown-item command="logout" divided>
                <span>退出登录</span>
              </el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </div>
    </div>
  </div>
</template>

<script setup>
import useUserStore from '@/store/modules/user'
import useAppStore from '@/store/modules/app'

const userStore = useUserStore()
const appStore = useAppStore()

const name = computed(() => userStore.name)
const roles = computed(() => userStore.roles)
const sidebar = computed(() => appStore.sidebar)
const device = computed(() => appStore.device)

function toggleSideBar() {
  appStore.toggleSideBar()
}

function handleCommand(command) {
  switch (command) {
    case 'userProfile':
      proxy.$router.push({ path: '/user/profile' })
      break
    case 'logout':
      logout()
      break
    default:
      break
  }
}

function logout() {
  ElMessageBox.confirm('确定注销并退出系统吗？', '提示', {
    confirmButtonText: '确定',
    cancelButtonText: '取消',
    type: 'warning'
  }).then(() => {
    userStore.logOut().then(() => {
      location.href = `${import.meta.env.BASE_URL}index`
    })
  }).catch(() => {})
}
</script>

<style lang="scss" scoped>
.navbar {
  height: 50px;
  overflow: hidden;
  position: relative;
  background: #fff;
  box-shadow: 0 1px 4px rgba(0, 21, 41, 0.08);

  .hamburger-container {
    line-height: 46px;
    height: 100%;
    float: left;
    cursor: pointer;
    transition: background 0.3s;
    -webkit-tap-highlight-color: transparent;

    &:hover {
      background: rgba(0, 0, 0, 0.025);
    }
  }

  .breadcrumb-container {
    float: left;
  }

  .topnav-container {
    float: left;
  }

  .right-menu {
    float: right;
    height: 100%;
    line-height: 50px;
    display: flex;

    &:focus {
      outline: none;
    }

    .right-menu-item {
      display: inline-block;
      padding: 0 8px;
      height: 100%;
      font-size: 18px;
      color: #5a5e66;
      vertical-align: text-bottom;

      &.hover-effect {
        cursor: pointer;
        transition: background 0.3s;

        &:hover {
          background: rgba(0, 0, 0, 0.025);
        }
      }
    }

    .el-dropdown-link {
      cursor: pointer;
      color: var(--current-color);
    }
  }
}
</style>
