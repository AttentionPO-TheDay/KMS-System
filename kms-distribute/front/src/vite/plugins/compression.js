import viteCompression from 'vite-plugin-compression'

export default function createCompression(viteEnv) {
  return [
    viteCompression({
      ext: '.gz',
      algorithm: 'gzip',
      deleteOriginFile: false,
      threshold: 10240
    })
  ]
}
