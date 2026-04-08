import { saveAs } from 'file-saver'
import { getToken } from '@/utils/auth'
import { tansParams, blobValidate } from '@/utils/ruoyi'
import axios from 'axios'

/**
 * 下载文件
 * @param {*} url
 * @param {*} params
 * @param {*} filename
 * @param {*} config
 */
export function download(url, params, filename, config) {
  url = import.meta.env.VITE_APP_BASE_API + url
  return axios({
    method: 'post',
    url: url,
    data: params,
    params: params,
    headers: {
      'Content-Type': 'application/x-www-form-urlencoded',
      'Authorization': 'Bearer ' + getToken()
    },
    responseType: 'blob',
    ...config
  }).then(async (data) => {
    const isBlob = blobValidate(data.data)
    if (isBlob) {
      const blob = new Blob([data.data])
      saveAs(blob, filename)
    } else {
      const resText = await data.data.text()
      const rspObj = JSON.parse(resText)
      const msg = rspObj.msg || errorCode[rspObj.code] || rspObj.code
      Message.error(msg)
    }
  }).catch((r) => {
    console.error(r)
    Message.error('下载文件出现错误，请联系管理员！')
  })
}

export default {
  download
}
