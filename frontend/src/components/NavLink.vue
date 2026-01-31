<script setup lang="ts">
defineProps<{
  name: string
  url: string
}>()
</script>

<template>
  <li class="w-full">
    <a
      class="md:px-4 py-2 text-sm bg-transparent rounded-lg text-[#666666] hover:text-gray-900 focus:outline-none focus:shadow-outline"
      :href="url"
    >
      {{ name }}
    </a>
  </li>
</template>
