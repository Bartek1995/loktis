<script setup lang="ts">
import MdiIcon from '@/components/icons/MdiIcon.vue'
import { mdiCheckCircle } from '@mdi/js'

defineProps<{
  title: string
}>()
</script>

<template>
  <li class="space-y-2">
    <div class="flex items-center space-x-2">
      <MdiIcon :path="mdiCheckCircle" :size="20" class="text-[#0c66ee]" />
      <span>{{ title }}</span>
    </div>
    <slot></slot>
  </li>
</template>
