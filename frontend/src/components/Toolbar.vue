<script setup lang="ts">
import { computed } from 'vue'
import { useLayoutStore } from '../stores/layoutStore'

const layoutStore = useLayoutStore()

const isDarkMode = computed({
  get: () => localStorage.getItem('darkMode') === 'true',
  set: (value) => {
    localStorage.setItem('darkMode', value ? 'true' : 'false')
    const html = document.documentElement
    if (value) {
      html.classList.add('dark')
    } else {
      html.classList.remove('dark')
    }
  },
})

const toggleDarkMode = () => {
  isDarkMode.value = !isDarkMode.value
}

const handleNewLayout = () => {
  const name = prompt('Nazwa nowego planu:', 'Nowy plan')
  if (name) {
    layoutStore.createLayout(name).catch(() => {
      alert('Błąd przy tworzeniu planu')
    })
  }
}

const handleSave = () => {
  layoutStore.saveLayout().catch(() => {
    alert('Błąd przy zapisie')
  })
}
</script>

<template>
  <div class="border-b border-gray-200 bg-white dark:border-gray-700 dark:bg-gray-900 shadow-sm">
    <div class="flex items-center justify-between px-6 py-3 gap-4">
      <!-- Title -->
      <div class="flex items-center gap-2 flex-1">
        <i class="pi pi-home text-2xl text-blue-600"></i>
        <h1 class="text-xl font-bold text-gray-900 dark:text-gray-100">FloorPlan Ergonomics</h1>
      </div>

      <!-- Actions -->
      <div class="flex items-center gap-2">
        <!-- New Plan -->
        <Button
          icon="pi pi-file-export"
          rounded
          text
          severity="secondary"
          @click="handleNewLayout"
          v-tooltip="{ value: 'Nowy plan', showDelay: 500 }"
        />

        <!-- Save -->
        <Button
          icon="pi pi-save"
          rounded
          text
          severity="success"
          @click="handleSave"
          v-tooltip="{ value: 'Zapisz (Ctrl+S)', showDelay: 500 }"
          :disabled="!layoutStore.currentLayout"
        />

        <!-- Export -->
        <Button
          icon="pi pi-download"
          rounded
          text
          @click="() => {}"
          v-tooltip="{ value: 'Eksportuj', showDelay: 500 }"
          :disabled="!layoutStore.currentLayout"
        />

        <Divider layout="vertical" />

        <!-- Dark Mode -->
        <Button
          :icon="isDarkMode ? 'pi pi-sun' : 'pi pi-moon'"
          rounded
          text
          @click="toggleDarkMode"
          v-tooltip="{ value: isDarkMode ? 'Jasny tryb' : 'Ciemny tryb', showDelay: 500 }"
        />
      </div>
    </div>
  </div>
</template>

<style scoped></style>
