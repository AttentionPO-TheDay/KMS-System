import store from '@/store'

export function useDict(...args) {
  const res = ref({})
  args.forEach(dictName => {
    res.value[dictName] = []
    const dict = store.getters.dict[dictName]
    if (dict) {
      res.value[dictName] = dict
    }
  })
  return res
}
