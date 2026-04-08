<template>
  <div>
    <iframe :src="url" frameborder="0" width="100%" height="100%" />
  </div>
</template>

<script>
export default {
  name: 'InnerLink',
  props: {
    url: {
      type: String,
      required: true
    }
  }
}
</script>
