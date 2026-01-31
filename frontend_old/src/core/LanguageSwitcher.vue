<!-- src/core/LanguageSwitcher.vue -->
<script setup lang="ts">
import { ref, watch, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useLanguageStore } from '@/stores/language'

/* PrimeVue komponenty (jeśli nie włączasz auto-importu) */
import Button from 'primevue/button'
import Menu   from 'primevue/menu'

/* ──────────────── dostępne języki ───────────────── */
const languages = [
  { code: 'pl', label: 'Polski',  icon: 'pi pi-flag-fill'  },
  { code: 'en', label: 'English', icon: 'pi pi-flag'       },
]

/* ──────────────── i18n + store ──────────────────── */
const languageStore = useLanguageStore()
const { locale, t } = useI18n()

/* synchronizacja locale ↔ store */
locale.value = languageStore.selected
watch(
  () => languageStore.selected,
  (lang) => { locale.value = lang }
)

/* ──────────────── PrimeVue Menu refs ────────────── */
const menuRef = ref<InstanceType<typeof Menu> | null>(null)
function toggleMenu (event: Event) {
  menuRef.value?.toggle(event)
}

/* Mapujemy języki na strukturę Menu ---------------- */
const menuItems = computed(() => languages.map((lng) => ({
  label: lng.label,
  icon:  lng.icon,
  class: languageStore.selected === lng.code ? 'font-semibold text-primary-600' : '',
  command: () => languageStore.setLanguage(lng.code),
})))
</script>

<template>
  <!-- BTN z tooltipem -->
  <Button
    icon="pi pi-globe"
    text
    rounded
    aria-label="Language"
    @click="toggleMenu"
  />

  <!-- Menu PrimeVue w trybie popup -->
  <Menu
    ref="menuRef"
    :model="menuItems"
    popup
  />
</template>
