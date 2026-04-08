<template>
  <div class="app-container">
    <el-row :gutter="20">
      <el-col :span="6">
        <el-card shadow="hover">
          <div class="user-info">
            <img :src="userStore.avatar" class="user-avatar" />
            <div class="user-name">{{ userStore.name }}</div>
            <div class="user-role">{{ getRoleLevelText(userStore.roleLevel) }}</div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="18">
        <el-card shadow="hover">
          <el-tabs v-model="activeTab">
            <el-tab-pane label="基本信息" name="info">
              <el-form :model="userForm" label-width="100px">
                <el-form-item label="用户ID">{{ userForm.userId }}</el-form-item>
                <el-form-item label="用户名">{{ userForm.userName }}</el-form-item>
                <el-form-item label="手机号码">{{ userForm.phonenumber || '-' }}</el-form-item>
                <el-form-item label="邮箱">{{ userForm.email || '-' }}</el-form-item>
                <el-form-item label="创建时间">{{ userForm.createTime || '-' }}</el-form-item>
              </el-form>
            </el-tab-pane>
          </el-tabs>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup name="UserProfile">
import { getUserProfile } from "@/api/system/user"
import useUserStore from '@/store/modules/user'

const userStore = useUserStore()
const activeTab = ref('info')
const userForm = ref({})

function getRoleLevelText(level) {
  const levelMap = { 0: '管理员', 1: '中级用户', 2: '普通用户' }
  return levelMap[level] || '未知'
}

getUserProfile().then(response => {
  userForm.value = response.data
})
</script>

<style scoped>
.user-info { text-align: center; padding: 20px; }
.user-avatar { width: 80px; height: 80px; border-radius: 50%; margin-bottom: 15px; }
.user-name { font-size: 20px; font-weight: bold; margin-bottom: 10px; }
.user-role { color: #909399; }
</style>
