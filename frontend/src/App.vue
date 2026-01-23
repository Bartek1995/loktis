<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useLayoutStore } from './stores/layoutStore'
import Sidebar from './components/Sidebar.vue'
import Toolbar from './components/Toolbar.vue'
import FloorCanvas from './components/FloorCanvas.vue'

const layoutStore = useLayoutStore()
const sidebarVisible = ref(true)

onMounted(() => {
  layoutStore.fetchLayouts()
})
</script>

<template>
  <div class="h-screen w-full flex flex-col bg-gray-50 dark:bg-gray-950">
    <!-- Toolbar -->
    <Toolbar />

    <!-- Main Content -->
    <div class="flex flex-1 overflow-hidden gap-0">
      <!-- Sidebar -->
      <Sidebar v-show="sidebarVisible" />

      <!-- Canvas Area -->
      <div class="flex-1 flex flex-col overflow-hidden">
        <FloorCanvas />
      </div>
    </div>
  </div>
</template>

<style scoped></style>
