<script setup lang="ts">
/**
 * Login View - tymczasowo nieaktywny
 * 
 * TODO: Aktywować gdy będzie potrzebna autoryzacja użytkowników
 */
import { ref } from 'vue';
import { useRouter } from 'vue-router';
import { useToast } from 'primevue/usetoast';
import { useAuthStore } from '@/stores/auth';

const router = useRouter();
const toast = useToast();
const auth = useAuthStore();

const email = ref('');
const password = ref('');
const isLoading = ref(false);

async function handleLogin() {
  if (!email.value || !password.value) {
    toast.add({
      severity: 'warn',
      summary: 'Uwaga',
      detail: 'Wprowadź email i hasło',
      life: 3000,
    });
    return;
  }

  isLoading.value = true;

  try {
    const success = await auth.login(email.value, password.value);
    
    if (success) {
      toast.add({
        severity: 'success',
        summary: 'Zalogowano',
        detail: 'Witaj!',
        life: 2000,
      });
      router.push({ name: 'landing' });
    } else {
      toast.add({
        severity: 'error',
        summary: 'Błąd',
        detail: 'Nieprawidłowy email lub hasło',
        life: 3000,
      });
    }
  } catch (error) {
    toast.add({
      severity: 'error',
      summary: 'Błąd',
      detail: 'Wystąpił błąd podczas logowania',
      life: 3000,
    });
  } finally {
    isLoading.value = false;
  }
}
</script>

<template>
  <div class="flex items-center justify-center min-h-screen bg-surface-100">
    <Card class="w-full max-w-md">
      <template #title>
        <div class="text-center">
          <i class="pi pi-home text-4xl mb-2 text-primary"></i>
          <h1 class="text-2xl font-bold">Analizator Ogłoszeń</h1>
          <p class="text-surface-500 text-sm mt-1">Zaloguj się aby kontynuować</p>
        </div>
      </template>
      
      <template #content>
        <form @submit.prevent="handleLogin" class="flex flex-col gap-4">
          <div class="flex flex-col gap-2">
            <label for="email" class="font-medium">Email</label>
            <InputText 
              id="email"
              v-model="email"
              type="email"
              placeholder="twoj@email.pl"
              :disabled="isLoading"
            />
          </div>
          
          <div class="flex flex-col gap-2">
            <label for="password" class="font-medium">Hasło</label>
            <Password 
              id="password"
              v-model="password"
              :feedback="false"
              toggleMask
              placeholder="••••••••"
              :disabled="isLoading"
              inputClass="w-full"
            />
          </div>
          
          <Button 
            type="submit"
            label="Zaloguj się"
            icon="pi pi-sign-in"
            :loading="isLoading"
            class="mt-2"
          />
        </form>
      </template>
      
      <template #footer>
        <div class="text-center text-sm text-surface-500">
          <p>Logowanie jest obecnie wyłączone (MVP)</p>
        </div>
      </template>
    </Card>
  </div>
</template>
