<script setup lang="ts">
import { ref } from 'vue'
import MdiIcon from '@/components/icons/MdiIcon.vue'
import { mdiChevronUp, mdiChevronDown } from '@mdi/js'

interface AccordionData {
  title: string
  description: string
}

defineProps<{
  accordion: AccordionData
}>()

const selected = ref(false)
</script>

<template>
  <li class="relative border-b-2 border-gray-200">
    <button type="button" class="w-full py-4 text-left" @click="selected = !selected">
      <div class="flex items-center justify-between">
        <span class="font-medium">{{ accordion.title }}</span>
        <MdiIcon v-if="selected" :path="mdiChevronUp" :size="20" />
        <MdiIcon v-else :path="mdiChevronDown" :size="20" />
      </div>
    </button>

    <Transition name="slide">
      <div v-if="selected" class="relative overflow-hidden">
        <div class="py-2">
          <p class="text-sm text-gray-700 tracking-wide leading-relaxed">
            {{ accordion.description }}
          </p>
        </div>
      </div>
    </Transition>
  </li>
</template>
