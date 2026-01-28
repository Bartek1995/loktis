<script setup lang="ts">
/**
 * Not Found View (404)
 */
import { useRouter } from 'vue-router';

const router = useRouter();

function goHome() {
  router.push({ name: 'landing' });
}
</script>

<template>
  <div class="flex flex-col items-center justify-center min-h-screen bg-surface-100">
    <div class="text-center">
      <h1 class="text-8xl font-bold text-surface-300 mb-2">404</h1>
      <h2 class="text-2xl font-semibold mb-2">Strona nie znaleziona</h2>
      <p class="text-surface-500 mb-6">Strona, której szukasz, nie istnieje.</p>
      <Button 
        label="Wróć na stronę główną" 
        icon="pi pi-home"
        @click="goHome"
      />
    </div>
  </div>
</template>
