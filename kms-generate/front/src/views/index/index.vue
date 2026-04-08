<template>
  <div class="dashboard-container">
    <div class="dashboard-text">密钥生成系统</div>
    <div class="info-card">
      <el-row :gutter="20">
        <el-col :span="6">
          <div class="card-item">
            <div class="card-icon blue"><svg-icon icon-class="key" /></div>
            <div class="card-content">
              <div class="card-num">{{ stats.totalKeys }}</div>
              <div class="card-label">密钥总数</div>
            </div>
          </div>
        </el-col>
        <el-col :span="6">
          <div class="card-item">
            <div class="card-icon green"><svg-icon icon-class="user" /></div>
            <div class="card-content">
              <div class="card-num">{{ stats.totalUsers }}</div>
              <div class="card-label">用户总数</div>
            </div>
          </div>
        </el-col>
        <el-col :span="6">
          <div class="card-item">
            <div class="card-icon orange"><svg-icon icon-class="chart" /></div>
            <div class="card-content">
              <div class="card-num">{{ stats.todayGenerate }}</div>
              <div class="card-label">今日生成</div>
            </div>
          </div>
        </el-col>
        <el-col :span="6">
          <div class="card-item">
            <div class="card-icon purple"><svg-icon icon-class="chain" /></div>
            <div class="card-content">
              <div class="card-num">{{ stats.onChainCount }}</div>
              <div class="card-label">已上链</div>
            </div>
          </div>
        </el-col>
      </el-row>
    </div>
    <el-row :gutter="20" style="margin-top: 20px;">
      <el-col :span="12">
        <el-card shadow="hover">
          <template #header><span>系统公告</span></template>
          <div class="notice-content">
            <p>欢迎使用密钥生成系统</p>
            <p>系统支持SM2、SSCL等多种加密算法</p>
          </div>
        </el-card>
      </el-col>
      <el-col :span="12">
        <el-card shadow="hover">
          <template #header><span>快捷操作</span></template>
          <div class="quick-actions">
            <el-button type="primary" @click="$router.push('/generate/keygenerate/index')">密钥生成</el-button>
            <el-button type="success" @click="$router.push('/generate/history/index')">生成历史</el-button>
            <el-button type="info" @click="$router.push('/generate/commonparam/index')">公共参数</el-button>
            <el-button type="warning" @click="$router.push('/permission/request/index')">权限审批</el-button>
          </div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
const stats = reactive({
  totalKeys: 0,
  totalUsers: 0,
  todayGenerate: 0,
  onChainCount: 0
})
</script>

<style scoped>
.dashboard-container { padding: 20px }
.dashboard-text { font-size: 30px; font-weight: bold; margin-bottom: 20px; text-align: center }
.info-card { background: #fff; border-radius: 8px; padding: 20px }
.card-item { display: flex; align-items: center; background: #f8f9fa; border-radius: 8px; padding: 20px }
.card-icon { width: 60px; height: 60px; border-radius: 8px; display: flex; align-items: center; justify-content: center; font-size: 30px; color: #fff; margin-right: 15px }
.card-icon.blue { background: #409EFF }
.card-icon.green { background: #67C23A }
.card-icon.orange { background: #E6A23C }
.card-icon.purple { background: #9C27B0 }
.card-content { flex: 1 }
.card-num { font-size: 28px; font-weight: bold; color: #303133 }
.card-label { font-size: 14px; color: #909399; margin-top: 5px }
.notice-content p { margin: 10px 0; color: #606266 }
.quick-actions { display: flex; gap: 10px; flex-wrap: wrap }
</style>
