<script setup lang="ts">
defineProps<{
  path: string
  size?: number
}>()
</script>

<template>
  <svg
    :width="size || 24"
    :height="size || 24"
    viewBox="0 0 24 24"
    class="inline-block"
  >
    <path fill="currentColor" :d="path" />
  </svg>
</template>
