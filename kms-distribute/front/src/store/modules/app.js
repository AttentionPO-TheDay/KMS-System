import Cookies from 'js-cookie'

const useAppStore = defineStore('app', {
  state: () => ({
    sidebar: {
      opened: Cookies.get('sidebarStatus') ? !!+Cookies.get('sidebarStatus') : true,
      withoutAnimation: false,
      hide: false
    },
    device: 'desktop'
  }),
  actions: {
    toggleSideBar() {
      if (this.sidebar.opened) {
        Cookies.set('sidebarStatus', 1)
      } else {
        Cookies.set('sidebarStatus', 0)
      }
      this.sidebar.opened = !this.sidebar.opened
      this.sidebar.withoutAnimation = false
    },
    closeSideBar(withoutAnimation) {
      Cookies.set('sidebarStatus', 0)
      this.sidebar.opened = false
      this.sidebar.withoutAnimation = withoutAnimation
    },
    toggleDevice(device) {
      this.device = device
    }
  }
})

export default useAppStore
