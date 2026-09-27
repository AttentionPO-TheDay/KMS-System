export const apiBases = {
  generateApi: import.meta.env.VITE_APP_GENERATE_API || '/generate-api',
  lifecycleApi: import.meta.env.VITE_APP_LIFECYCLE_API || '/lifecycle-api',
  // 分发模块（Django）的对外前缀。用户侧分发接口走它，见 §5.1。
  pqkdsApi: import.meta.env.VITE_APP_PQKDS_API || '/pqkds-api'
}
