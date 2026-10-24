import { build } from 'vite'

// Verify the release differs from the deployed frontend only in the upload offset.
await build({
  mode: 'production',
  plugins: [{
    name: 'pool-baseline-comparison',
    enforce: 'pre',
    transform(code, id) {
      if (id.endsWith('/src/views/preallocate/index.vue')) {
        if (!code.includes('startIndex: start,')) throw new Error('Upload offset missing from source')
        return code.replace(/        startIndex: start,\r?\n/, '')
      }
    }
  }],
  build: { outDir: '../../kms-ops/releases/pool-chunk-index-20261023/frontend-baseline-build' }
})
