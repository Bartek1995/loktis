<!-- src/layout/AppTopbar.vue -->
<script setup lang="ts">
import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import Toolbar from 'primevue/toolbar'
import Button from 'primevue/button'
import Menu from 'primevue/menu'
import Avatar from 'primevue/avatar'
import Badge from 'primevue/badge'
import type { MenuItem } from 'primevue/menuitem'

import { useLayout } from '@/layout/composables/layout'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const auth = useAuthStore()
const { toggleMenu, toggleDarkMode, isDarkTheme } = useLayout()

// Popup refs
const quickMenuRef = ref<InstanceType<typeof Menu> | null>(null)
const userMenuRef = ref<InstanceType<typeof Menu> | null>(null)

// Dane uzytkownika
const isLoggedIn = computed(() => auth.isLoggedIn)
const user = computed(() => auth.user)
const displayName = computed(() => user.value?.first_name || user.value?.username || 'Guest')
const avatarUrl = computed(() => user.value?.avatar || '')
const initials = computed(() => {
  const a = (user.value?.first_name || user.value?.username || 'GU').trim()
  const b = (user.value?.last_name || '').trim()
  return (a[0] || 'G').toUpperCase() + (b[0] || (a[1] || 'U')).toUpperCase()
})

// Przykladowe liczby/skrot do funkcji - podlacz pod swoje API
const unread = ref(3)

// Meny szybkiego dostepu (ikona "apps")
const quickMenuItems: MenuItem[] = [
  { label: 'Lista mieszkan', icon: 'pi pi-building', command: () => router.push('/') },
  { label: 'Rzuty', icon: 'pi pi-image', command: () => router.push('/layouts') },
  { separator: true },
  { label: 'Diagnostyka', icon: 'pi pi-wrench', command: () => router.push('/diagnostics') },
]

// Menu uzytkownika
const userMenuItems: MenuItem[] = [
  { label: 'Panel glowny', icon: 'pi pi-home', command: () => router.push('/') },
  { label: 'Ustawienia', icon: 'pi pi-cog', command: () => router.push('/settings') },
  { separator: true },
  {
    label: 'Wyloguj',
    icon: 'pi pi-sign-out',
    command: async () => {
      auth.logout()
    },
  },
]

// Handlery otwierania popupow
function openQuickMenu(e: MouseEvent) {
  quickMenuRef.value?.toggle(e)
}
function openUserMenu(e: MouseEvent) {
  if (!isLoggedIn.value) {
    router.push('/auth/login')
    return
  }
  userMenuRef.value?.toggle(e)
}
</script>

<template>
  <Toolbar class="fixed top-0 inset-x-0 z-50 w-full bg-surface-0 dark:bg-surface-900 px-3 md:px-4 shadow-md border-b border-surface">
    <template #start>
      <div class="flex items-center gap-3">
        <Button
          icon="pi pi-bars"
          class="p-button-rounded p-button-text"
          aria-label="Toggle navigation"
          @click="toggleMenu"
        />

        <router-link to="/" class="flex items-center gap-2 no-underline text-color">
          <i class="pi pi-building text-xl text-primary" />
          <span class="font-bold text-lg">Loktis</span>
        </router-link>
      </div>
    </template>

    <template #end>
      <div class="flex items-center gap-1 md:gap-2">
        <!-- Tryb ciemny/jasny -->
        <Button
          :icon="isDarkTheme ? 'pi pi-moon' : 'pi pi-sun'"
          class="p-button-rounded p-button-text"
          aria-label="Toggle theme"
          @click="toggleDarkMode"
        />

        <!-- Szybkie akcje (Menu popup) -->
        <span class="relative">
          <Button
            icon="pi pi-th-large"
            class="p-button-rounded p-button-text"
            aria-label="Open quick menu"
            @click="openQuickMenu"
          />
          <Badge v-if="unread > 0" :value="unread" class="absolute -top-1 -right-1" />
        </span>
        <Menu ref="quickMenuRef" :model="quickMenuItems" popup />

        <!-- Avatar / User menu -->
        <Button class="p-button-text p-0" aria-haspopup="true" aria-controls="user_menu" @click="openUserMenu">
          <div class="flex items-center gap-2 px-2">
            <Avatar
              v-if="avatarUrl"
              :image="avatarUrl"
              shape="circle"
              size="large"
              aria-label="User avatar"
            />
            <Avatar
              v-else
              :label="initials"
              shape="circle"
              size="large"
              aria-label="User initials"
            />
            <span class="hidden md:block text-sm font-medium truncate max-w-40">{{ displayName }}</span>
            <i class="pi pi-angle-down hidden md:block" />
          </div>
        </Button>
        <Menu id="user_menu" ref="userMenuRef" :model="userMenuItems" popup />
      </div>
    </template>
  </Toolbar>
</template>
