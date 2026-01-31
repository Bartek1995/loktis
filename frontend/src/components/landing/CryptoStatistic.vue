<script setup lang="ts">
import MdiIcon from '@/components/icons/MdiIcon.vue'
import { mdiChevronRight, mdiPlus, mdiMinus } from '@mdi/js'

interface CryptoData {
  id: number
  name: string
  price: number
  logo: string
  increase: boolean
  data: number[]
}

defineProps<{
  title?: string
  datasets: CryptoData[]
}>()

defineOptions({
  inheritAttrs: true
})

const getImageUrl = (name: string) => {
  return new URL(`../../assets/img/crypto-icon/${name}`, import.meta.url).href
}
</script>

<template>
  <div class="w-full lg:w-1/3 mt-6 lg:mt-0 overflow-hidden space-y-6" v-bind="$attrs">
    <div class="w-full flex items-center justify-between">
      <span class="font-medium">{{ title }}</span>
      <button
        class="px-3 py-1 text-sm font-medium text-blue-500 flex items-center space-x-1 rounded-md hover:bg-blue-50 transition duration-300"
      >
        <span>More</span>
        <MdiIcon :path="mdiChevronRight" :size="16" />
      </button>
    </div>
    <div class="flex flex-col">
      <div class="-my-2 overflow-x-auto sm:-mx-6 lg:-mx-8">
        <div class="px-2 sm:px-6 py-2 align-middle inline-block min-w-full overflow-hidden">
          <table class="min-w-full">
            <thead>
              <tr>
                <th class="text-left text-sm font-medium text-gray-500">Name</th>
                <th class="text-left text-sm font-medium text-gray-500">Price</th>
                <th class="hidden sm:block text-left text-sm font-medium text-gray-500">Chart</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in datasets" :key="item.id" class="border-b border-gray-200">
                <td class="py-4 whitespace-nowrap">
                  <div class="flex items-center space-x-2">
                    <img :src="getImageUrl(item.logo)" alt="" class="w-6 h-6" />
                    <span>{{ item.name }}</span>
                  </div>
                </td>
                <td class="py-4 whitespace-nowrap">
                  <div class="flex items-center">
                    <MdiIcon 
                      v-if="item.increase" 
                      :path="mdiPlus" 
                      :size="14" 
                      class="text-emerald-500" 
                    />
                    <MdiIcon 
                      v-else 
                      :path="mdiMinus" 
                      :size="14" 
                      class="text-red-500" 
                    />
                    <span>${{ item.price }}</span>
                  </div>
                </td>
                <td class="hidden sm:block whitespace-nowrap">
                  <div class="w-28 h-12 -mx-2 flex items-center">
                    <!-- Simple chart placeholder - can be replaced with actual chart -->
                    <svg class="w-full h-8" viewBox="0 0 100 30">
                      <polyline
                        :points="item.data.map((v, i) => `${i * 15},${30 - v * 0.35}`).join(' ')"
                        fill="none"
                        :stroke="item.increase ? '#28C165' : '#F4574D'"
                        stroke-width="2"
                      />
                    </svg>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  </div>
</template>
