<script setup lang="ts">
import { ref } from 'vue'
import MdiIcon from '@/components/icons/MdiIcon.vue'
import { mdiChevronDown } from '@mdi/js'

interface Exchange {
  img: string
  name: string
}

const props = defineProps<{
  title?: string
  name: string
  defaultValue?: string | number
  exchangeSelected: Exchange
  exchanges: Exchange[]
  type?: string
}>()

const openDropdown = ref(false)

const toggleDropdown = () => {
  openDropdown.value = !openDropdown.value
}

const getImageUrl = (imgPath: string) => {
  return new URL(`../../assets/img/${imgPath}`, import.meta.url).href
}
</script>

<template>
  <div class="flex items-center space-x-4">
    <div class="lg:max-w-[336px] w-full flex items-center relative px-5 py-3 border border-[#0c66ee] rounded-xl">
      <span class="text-sm font-medium pr-5 py-3 text-[#0c66ee] border-r border-[#0c66ee]">{{ title }}</span>
      <input
        :type="type || 'text'"
        class="w-full text-lg font-medium text-right border-none ring-0 focus:outline-none focus:ring-0 bg-transparent"
        :name="name"
        :value="defaultValue"
      />
    </div>
    <div class="relative w-full max-w-[106px] sm:max-w-[159px]">
      <button
        type="button"
        class="w-full flex items-center justify-center space-x-1 relative sm:px-6 py-[1.35rem] border border-[#0c66ee] rounded-xl text-sm font-medium"
        @click="toggleDropdown"
      >
        <img :src="getImageUrl(exchangeSelected.img)" alt="" class="flex-shrink-0 h-6 w-6 rounded-full" />
        <span class="ml-3 block truncate">{{ exchangeSelected.name }}</span>
        <MdiIcon :path="mdiChevronDown" :size="20" />
      </button>
      <Transition name="transform-fade-down">
        <ul
          v-if="openDropdown"
          class="absolute z-10 mt-1 w-full bg-white shadow-lg max-h-56 rounded-md py-1 text-base ring-1 ring-black/5 overflow-auto focus:outline-none sm:text-sm border border-[#0c66ee]"
          tabindex="-1"
        >
          <li
            v-for="exchange in exchanges"
            :key="exchange.name"
            class="text-gray-900 cursor-default select-none relative px-3 sm:px-5 py-2 hover:bg-gray-50"
            role="option"
          >
            <div class="flex items-center">
              <img :src="getImageUrl(exchange.img)" alt="" class="flex-shrink-0 h-6 w-6 rounded-full" />
              <span class="font-normal ml-3 block truncate">{{ exchange.name }}</span>
            </div>
          </li>
        </ul>
      </Transition>
    </div>
  </div>
</template>
