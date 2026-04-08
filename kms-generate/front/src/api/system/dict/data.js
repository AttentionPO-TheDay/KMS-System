import request from '@/utils/request'

export function getDictDataAll(dictType) {
  return request({
    url: '/system/dict/data/type/' + dictType,
    method: 'get'
  })
}
