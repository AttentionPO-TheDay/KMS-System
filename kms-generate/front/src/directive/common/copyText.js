export default {
  mounted(el, binding) {
    el.$copyText = binding.value
    el.addEventListener('click', () => {
      navigator.clipboard.writeText(el.$copyText).then(() => {
        ElMessage.success('复制成功')
      }).catch(() => {
        ElMessage.error('复制失败')
      })
    })
  }
}
