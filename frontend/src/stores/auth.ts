/**
 * Auth Store - tymczasowo nieaktywny (przygotowany na przyszłość)
 * 
 * TODO: Aktywować gdy będzie potrzebna autoryzacja użytkowników
 */
import { defineStore } from 'pinia';
import { ref, computed } from 'vue';

export const useAuthStore = defineStore('auth', () => {
  // State
  const isAuthReady = ref(true); // Dla MVP zawsze ready (brak auth)
  const isLoggedIn = ref(false);
  const user = ref<{ id: number; email: string; name: string } | null>(null);
  const accessToken = ref<string | null>(null);

  // Getters
  const userName = computed(() => user.value?.name || 'Gość');
  const userEmail = computed(() => user.value?.email || '');

  // Actions
  async function initialize() {
    // MVP: brak autoryzacji, od razu ready
    isAuthReady.value = true;
    
    // TODO: Odkomentuj gdy auth będzie aktywne
    // const token = localStorage.getItem('access_token');
    // if (token) {
    //   accessToken.value = token;
    //   await fetchUser();
    // }
  }

  async function login(email: string, password: string): Promise<boolean> {
    // TODO: Implementacja logowania
    console.warn('Auth nieaktywne - login pominięty');
    return false;
  }

  async function logout() {
    user.value = null;
    accessToken.value = null;
    isLoggedIn.value = false;
    localStorage.removeItem('access_token');
  }

  async function fetchUser() {
    // TODO: Pobierz dane użytkownika z API
  }

  return {
    // State
    isAuthReady,
    isLoggedIn,
    user,
    accessToken,
    // Getters
    userName,
    userEmail,
    // Actions
    initialize,
    login,
    logout,
    fetchUser,
  };
});
