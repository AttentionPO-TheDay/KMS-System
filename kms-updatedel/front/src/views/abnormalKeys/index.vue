<template>
  <div class="app-container">
    <el-tabs model-value="node">
      <el-tab-pane label="节点密钥审查与回收" name="node">
        <NodeRecords />
      </el-tab-pane>
      <el-tab-pane label="用户密钥（旧生命周期）" name="legacy" lazy>
        <LegacyAbnormalKeys />
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup>
import NodeRecords from './nodeRecords.vue'
import LegacyAbnormalKeys from './legacy.vue'
</script>
