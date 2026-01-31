<script setup lang="ts">
/**
 * BaseAccordion - FAQ accordion component
 * Adapted from nefa-main
 */
import { ref } from 'vue';

interface AccordionItem {
  title: string;
  description: string;
}

defineProps<{
  accordion: AccordionItem;
}>();

const isOpen = ref(false);

function toggle() {
  isOpen.value = !isOpen.value;
}
</script>

<template>
  <li
    class="bg-white dark:bg-surface-800 rounded-xl shadow-sm overflow-hidden transition-all duration-300"
    :class="{ 'shadow-md': isOpen }"
  >
    <button
      @click="toggle"
      class="w-full px-6 py-5 flex items-center justify-between text-left transition-colors hover:bg-surface-50 dark:hover:bg-surface-700"
    >
      <span class="font-semibold text-surface-800 dark:text-surface-100">
        {{ accordion.title }}
      </span>
      <span
        class="ml-4 shrink-0 w-8 h-8 flex items-center justify-center rounded-full bg-surface-100 dark:bg-surface-700 transition-transform duration-300"
        :class="{ 'rotate-180': isOpen }"
      >
        <i class="pi pi-chevron-down text-sm text-surface-500"></i>
      </span>
    </button>
    
    <Transition name="accordion">
      <div v-show="isOpen" class="px-6 pb-5">
        <p class="text-surface-600 dark:text-surface-400 leading-relaxed">
          {{ accordion.description }}
        </p>
      </div>
    </Transition>
  </li>
</template>

<style scoped>
.accordion-enter-active,
.accordion-leave-active {
  transition: all 0.3s ease;
  max-height: 500px;
}

.accordion-enter-from,
.accordion-leave-to {
  opacity: 0;
  max-height: 0;
}
</style>
