<template>
  <div>
    <el-drawer v-model="showSettings" :withHeader="true" :direction="direction" :size="size" title="布局设置">
      <div class="setting-drawer-content">
        <div class="setting-item">
          <span>侧边栏主题</span>
          <el-select v-model="sideTheme" style="width: 150px">
            <el-option label="深色主题" value="theme-dark" />
            <el-option label="浅色主题" value="theme-light" />
          </el-select>
        </div>
        <div class="setting-item">
          <span>主题颜色</span>
          <el-color-picker v-model="theme" :predefine="predefineColors" size="small" />
        </div>
        <div class="setting-item">
          <span>标签页开启</span>
          <el-switch v-model="tagsView" class="drawer-switch" />
        </div>
        <div class="setting-item">
          <span>固定头部</span>
          <el-switch v-model="fixedHeader" class="drawer-switch" />
        </div>
        <div class="setting-item">
          <span>侧边栏Logo</span>
          <el-switch v-model="sidebarLogo" class="drawer-switch" />
        </div>
      </div>
    </el-drawer>
  </div>
</template>

<script>
export default {
  name: 'Settings'
}
</script>

<style lang="scss" scoped>
.setting-drawer-content {
  padding: 20px;

  .setting-item {
    margin-bottom: 20px;
    display: flex;
    align-items: center;
    justify-content: space-between;

    span {
      font-size: 14px;
    }
  }
}
</style>
