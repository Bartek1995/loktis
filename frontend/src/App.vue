// src/App.vue
<script setup lang="ts">
import Toast from 'primevue/toast';
</script>

<template>
  <Toast position="top-right" />
  <router-view />
</template>

<style>
body {
  scrollbar-width: thin;
  scrollbar-color: rgba(141, 139, 139, 0.2) transparent;
}
</style>
