<script setup lang="ts">
defineOptions({
  inheritAttrs: false
})
</script>

<template>
  <button
    class="text-sm text-center rounded-full hover:shadow-lg hover:shadow-[#0c66ee]/30 hover:-translate-y-0.5 active:translate-y-0 transition-all duration-300"
    v-bind="$attrs"
  >
    <slot></slot>
  </button>
</template>
