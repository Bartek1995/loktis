<script setup lang="ts">
import { RouterView } from 'vue-router'
</script>

<template>
  <div class="w-full min-h-screen bg-slate-50 font-sans">
    <RouterView />
  </div>
</template>

<style>
@import url('https://fonts.googleapis.com/css2?family=Poppins:wght@300;400;500;600;700&display=swap');

body {
  font-family: 'Poppins', sans-serif;
}
</style>
