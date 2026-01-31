<script setup lang="ts">
import buyAndTradeImg from '@/assets/img/buy-and-trade.webp'

defineOptions({
  inheritAttrs: true
})
</script>

<template>
  <div class="col-span-12 lg:col-span-6" v-bind="$attrs">
    <div class="w-full">
      <img :src="buyAndTradeImg" class="mt-4 sm:-mt-4" alt="" />
    </div>
  </div>
</template>
