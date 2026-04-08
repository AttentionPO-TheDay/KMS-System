import { getDictDataAll } from "@/api/system/dict/data"

export function useDict(...args) {
  const res = ref({})
  args.forEach(arg => {
    res.value[arg] = ref([])
  })
  return res
}
