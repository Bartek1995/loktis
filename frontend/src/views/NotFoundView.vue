<script setup lang="ts">
import { useRouter } from 'vue-router';

const router = useRouter();

function goHome() {
  router.push({ name: 'landing' });
}
</script>

<template>
  <div class="min-h-screen bg-gradient-to-br from-slate-50 via-white to-blue-50 flex items-center justify-center p-4">
    <div class="text-center">
      <div class="w-32 h-32 mx-auto mb-8 bg-gradient-to-br from-blue-100 to-blue-200 rounded-full flex items-center justify-center">
        <i class="pi pi-search text-5xl text-blue-400"></i>
      </div>
      
      <h1 class="text-6xl font-bold text-slate-800 mb-4">404</h1>
      <h2 class="text-2xl font-semibold text-slate-600 mb-4">Strona nie znaleziona</h2>
      <p class="text-slate-500 mb-8 max-w-md mx-auto">
        Przepraszamy, ale strona której szukasz nie istnieje lub została przeniesiona.
      </p>
      
      <button 
        @click="goHome"
        class="px-8 py-4 bg-gradient-to-r from-blue-500 to-blue-600 text-white font-semibold rounded-full shadow-lg hover:shadow-xl hover:scale-105 transition-all duration-300 flex items-center gap-2 mx-auto"
      >
        <i class="pi pi-home"></i>
        Wróć do strony głównej
      </button>
    </div>
  </div>
</template>
