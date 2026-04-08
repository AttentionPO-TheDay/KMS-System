const useDictStore = defineStore('dict', {
  state: () => ({
    dict: {}
  }),
  actions: {
    getDict() {
      return this.dict
    }
  }
})

export default useDictStore
