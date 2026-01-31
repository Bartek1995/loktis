<script setup lang="ts">
import advancedTradingImg from '@/assets/img/advanced-trading-tools.webp'

defineOptions({
  inheritAttrs: true
})
</script>

<template>
  <div class="col-span-12 lg:col-span-6" v-bind="$attrs">
    <div class="w-full sm:mt-20 xl:mt-0">
      <img :src="advancedTradingImg" class="w-full" alt="" />
    </div>
  </div>
</template>
