<script setup lang="ts">
/**
 * BaseButton - Gradient button component
 * Adapted from nefa-main with modern styling
 */
defineProps<{
  gradient?: boolean;
  outline?: boolean;
  size?: 'sm' | 'md' | 'lg';
}>();
</script>

<template>
  <button
    class="inline-flex items-center justify-center rounded-full font-medium transition-all duration-300 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-nefa-blue"
    :class="[
      // Size variants
      size === 'sm' && 'px-4 py-2 text-sm',
      size === 'lg' && 'px-8 py-4 text-lg',
      (!size || size === 'md') && 'px-6 py-3 text-base',
      // Style variants
      gradient && 'bg-gradient-to-r from-nefa-blue-light to-nefa-blue text-white shadow-lg hover:shadow-xl hover:scale-[1.02]',
      outline && 'border-2 border-nefa-blue text-nefa-blue hover:bg-nefa-blue/10',
      !gradient && !outline && 'bg-surface-100 text-surface-800 hover:bg-surface-200 dark:bg-surface-700 dark:text-surface-200'
    ]"
  >
    <slot />
  </button>
</template>
