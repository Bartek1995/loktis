<script setup lang="ts">
const getImageUrl = (name: string) => {
  return new URL(`../../assets/img/partner/${name}`, import.meta.url).href
}

defineProps<{
  img: string
}>()
</script>

<template>
  <div>
    <img :src="getImageUrl(img)" class="sm:w-1/2 lg:w-72 mx-auto" alt="" />
  </div>
</template>
