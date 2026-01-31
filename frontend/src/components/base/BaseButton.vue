<script setup lang="ts">
defineOptions({
  inheritAttrs: false
})
</script>

<template>
  <button
    class="text-sm text-center rounded-full hover:shadow-md hover:shadow-[#0c66ee]/50 transition duration-300"
    v-bind="$attrs"
  >
    <slot></slot>
  </button>
</template>
