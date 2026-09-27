import { createApp } from 'vue'
// 样式入口改为 SCSS：内部 @import 共享设计令牌包（design-tokens/）
import './style.scss'
import App from './App.vue'
import router from './router'

const app = createApp(App)
app.use(router)
app.mount('#app')
