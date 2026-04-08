import { ElMessage, ElMessageBox } from 'element-plus'

export default {
  // 消息提示
  msg(content) {
    ElMessage.info(content)
  },
  // 错误消息
  msgError(content) {
    ElMessage.error(content)
  },
  // 成功消息
  msgSuccess(content) {
    ElMessage.success(content)
  },
  // 警告消息
  msgWarning(content) {
    ElMessage.warning(content)
  },
  // 弹出提示
  alert(content) {
    ElMessageBox.alert(content, "系统提示")
  },
  // 错误提示
  alertError(content) {
    ElMessageBox.alert(content, "系统提示", { type: 'error' })
  },
  // 成功提示
  alertSuccess(content) {
    ElMessageBox.alert(content, "系统提示", { type: 'success' })
  },
  // 警告提示
  alertWarning(content) {
    ElMessageBox.alert(content, "系统提示", { type: 'warning' })
  },
  // 确认消息
  confirm(content) {
    return ElMessageBox.confirm(content, "系统提示", {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: "warning",
    })
  },
  // 确认弹出消息
  confirm(content, title) {
    return ElMessageBox.confirm(content, title || "系统提示", {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: "warning",
    })
  },
  // 提示输入
  prompt(content, title) {
    return ElMessageBox.prompt(content, title || "系统提示", {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: "warning",
    })
  }
}
