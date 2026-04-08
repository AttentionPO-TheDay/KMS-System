<template>
  <component :is="type" v-bind="linkProps" />
</template>

<script>
import { isExternal } from '@/utils/validate'

export default {
  props: {
    to: {
      type: [String, Object],
      required: true
    }
  },
  computed: {
    isExternal() {
      return isExternal(this.to)
    },
    type() {
      return this.isExternal ? 'a' : 'router-link'
    },
    linkProps() {
      if (this.isExternal) {
        return {
          href: this.to,
          target: '_blank',
          rel: 'noopener'
        }
      }
      return {
        to: this.to
      }
    }
  }
}
</script>
