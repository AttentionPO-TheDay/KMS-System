import defaultSettings from '@/settings'

const useSettingsStore = defineStore('settings', {
  state: () => ({
    title: defaultSettings.title,
    theme: defaultSettings.theme,
    sideTheme: defaultSettings.sideTheme,
    fixedHeader: defaultSettings.fixedHeader,
    sidebarLogo: defaultSettings.sidebarLogo,
    tagsView: defaultSettings.tagsView,
    size: Cookies.get('size') || defaultSettings.size
  }),
  actions: {
    setTitle(title) {
      this.title = title
    },
    setTheme(theme) {
      this.theme = theme
    },
    setSideTheme(sideTheme) {
      this.sideTheme = sideTheme
    }
  }
})

export default useSettingsStore
