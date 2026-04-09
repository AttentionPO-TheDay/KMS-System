export const apiBases = {
  generateApi: import.meta.env.VITE_APP_GENERATE_API || '/generate-api',
  lifecycleApi: import.meta.env.VITE_APP_LIFECYCLE_API || '/lifecycle-api',
  distributeApi: import.meta.env.VITE_APP_DISTRIBUTE_API || '/distribute-api'
}
