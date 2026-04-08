import vue from '@vitejs/plugin-vue'
import viteCompression from 'vite-plugin-compression'
import { createSvgIconsPlugin } from 'vite-plugin-svg-icons'
import AutoImport from 'unplugin-auto-import/vite'
import vitePluginSetupExtend from 'unplugin-vue-setup-extend-plus/vite'

export default function createVitePlugins(env, isBuild) {
  const { VITE_BUILD_COMPRESS } = env
  const plugins = [
    vue(),
    createSvgIconsPlugin({
      iconDirs: [process.cwd() + '/src/assets/icons'],
      symbolId: 'icon-[dir]-[name]'
    }),
    AutoImport({
      imports: ['vue', 'vue-router', 'pinia'],
      dts: 'src/auto-imports.d.ts',
      eslintrc: {
        enabled: false
      }
    }),
    vitePluginSetupExtend({})
  ]

  if (isBuild) {
    plugins.push(
      viteCompression({
        ext: '.gz',
        algorithm: 'gzip',
        threshold: 1024 * 50,
        deleteOriginFile: false,
        disable: VITE_BUILD_COMPRESS !== 'gzip'
      })
    )
  }

  return plugins
}
