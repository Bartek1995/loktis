<script setup lang="ts">
/**
 * BaseSection - Grid container component (12-column)
 * Adapted from nefa-main for consistent layout
 */
</script>

<template>
  <div class="relative max-w-screen-xl px-4 sm:px-6 lg:px-8 mx-auto grid grid-cols-12 gap-x-6 gap-y-8">
    <slot />
  </div>
</template>
