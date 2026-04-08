const useTagsViewStore = defineStore('tagsView', {
  state: () => ({
    visitedViews: [],
    cachedViews: []
  }),
  actions: {
    addView(view) {
      this.addVisitedView(view)
      this.addCachedView(view)
    },
    addVisitedView(view) {
      if (this.visitedViews.some(v => v.path === view.path)) return
      this.visitedViews.push(
        Object.assign({}, view, {
          title: view.meta.title || 'no-name'
        })
      )
    },
    addCachedView(view) {
      if (this.cachedViews.includes(view.name)) return
      if (view.meta && !view.meta.noCache) {
        this.cachedViews.push(view.name)
      }
    },
    delView(view) {
      return new Promise(resolve => {
        this.delVisitedView(view)
        this.delCachedView(view)
        resolve({
          visitedViews: [...this.visitedViews],
          cachedViews: [...this.cachedViews]
        })
      })
    },
    delVisitedView(view) {
      return new Promise(resolve => {
        const index = this.visitedViews.findIndex(v => v.path === view.path)
        if (index !== -1) {
          this.visitedViews.splice(index, 1)
        }
        resolve([...this.visitedViews])
      })
    },
    delCachedView(view) {
      return new Promise(resolve => {
        const index = this.cachedViews.indexOf(view.name)
        if (index !== -1) {
          this.cachedViews.splice(index, 1)
        }
        resolve([...this.cachedViews])
      })
    },
    delAllViews() {
      return new Promise(resolve => {
        this.visitedViews = []
        this.cachedViews = []
        resolve({
          visitedViews: [...this.visitedViews],
          cachedViews: [...this.cachedViews]
        })
      })
    },
    delOthersViews(view) {
      return new Promise(resolve => {
        this.visitedViews = this.visitedViews.filter(v => {
          return v.meta.affix || v.path === view.path
        })
        this.cachedViews = this.cachedViews.filter(i => {
          return i === view.name
        })
        resolve({
          visitedViews: [...this.visitedViews],
          cachedViews: [...this.cachedViews]
        })
      })
    },
    delLeftViews(view) {
      return new Promise(resolve => {
        const currentIndex = this.visitedViews.findIndex(v => v.path === view.path)
        if (currentIndex !== -1) {
          this.visitedViews = this.visitedViews.filter((item, idx) => {
            if (idx <= currentIndex || (item.meta && item.meta.affix)) {
              return true
            }
            const cachedIndex = this.cachedViews.indexOf(item.name)
            if (cachedIndex !== -1) {
              this.cachedViews.splice(cachedIndex, 1)
            }
            return false
          })
        }
        resolve({
          visitedViews: [...this.visitedViews],
          cachedViews: [...this.cachedViews]
        })
      })
    },
    delRightViews(view) {
      return new Promise(resolve => {
        const currentIndex = this.visitedViews.findIndex(v => v.path === view.path)
        if (currentIndex !== -1) {
          this.visitedViews = this.visitedViews.filter((item, idx) => {
            if (idx >= currentIndex || (item.meta && item.meta.affix)) {
              return true
            }
            const cachedIndex = this.cachedViews.indexOf(item.name)
            if (cachedIndex !== -1) {
              this.cachedViews.splice(cachedIndex, 1)
            }
            return false
          })
        }
        resolve({
          visitedViews: [...this.visitedViews],
          cachedViews: [...this.cachedViews]
        })
      })
    }
  }
})

export default useTagsViewStore
