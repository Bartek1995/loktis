<script setup lang="ts">
/**
 * Access Denied View
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
      <i class="pi pi-lock text-6xl text-orange-500 mb-4"></i>
      <h1 class="text-3xl font-bold mb-2">Brak dostępu</h1>
      <p class="text-surface-500 mb-6">Nie masz uprawnień do tej strony.</p>
      <Button 
        label="Wróć na stronę główną" 
        icon="pi pi-home"
        @click="goHome"
      />
    </div>
  </div>
</template>
