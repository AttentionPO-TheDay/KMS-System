<template>
  <SecurityMonitor v-if="userStore.principalType === 'ADMIN'" section="keys" />
  <div v-else class="app-container">节点请进入自己的工作台查看生命周期与分发。</div>
</template>

<script setup>
import SecurityMonitor from '@/views/securityMonitor/index.vue'
import useUserStore from '@/store/modules/user'

const userStore = useUserStore()
</script>
