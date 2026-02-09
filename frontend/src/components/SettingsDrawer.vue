<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'

const emit = defineEmits<{
  (e: 'update:devMode', value: boolean): void
}>()

const props = defineProps<{
  devMode: boolean
}>()

const isOpen = ref(false)
const localDevMode = ref(props.devMode)

// Sync with prop
watch(() => props.devMode, (val) => {
  localDevMode.value = val
})

// Persist to localStorage
watch(localDevMode, (val) => {
  localStorage.setItem('loktis_dev_mode', val ? 'true' : 'false')
  emit('update:devMode', val)
})

// Load from localStorage on mount
onMounted(() => {
  const saved = localStorage.getItem('loktis_dev_mode')
  if (saved === 'true') {
    localDevMode.value = true
    emit('update:devMode', true)
  }
})

function toggleDrawer() {
  isOpen.value = !isOpen.value
}

function closeDrawer() {
  isOpen.value = false
}
</script>

<template>
  <!-- Settings Button -->
  <button
    @click="toggleDrawer"
    class="fixed bottom-4 right-4 z-40 w-12 h-12 bg-slate-800 hover:bg-slate-700 text-white rounded-full shadow-lg flex items-center justify-center transition-all duration-200"
    :class="{ 'ring-2 ring-amber-400': localDevMode }"
    title="Ustawienia"
  >
    <i class="pi pi-cog text-xl"></i>
  </button>
  
  <!-- Backdrop -->
  <Transition name="fade">
    <div
      v-if="isOpen"
      @click="closeDrawer"
      class="fixed inset-0 bg-black/50 z-40"
    ></div>
  </Transition>
  
  <!-- Drawer -->
  <Transition name="slide-right">
    <div
      v-if="isOpen"
      class="fixed right-0 top-0 h-full w-80 bg-white shadow-xl z-50 overflow-y-auto"
    >
      <div class="p-6">
        <!-- Header -->
        <div class="flex items-center justify-between mb-6">
          <h2 class="text-lg font-bold text-slate-800">Ustawienia</h2>
          <button
            @click="closeDrawer"
            class="w-8 h-8 rounded-full hover:bg-slate-100 flex items-center justify-center"
          >
            <i class="pi pi-times text-slate-500"></i>
          </button>
        </div>
        
        <!-- DEV Mode Toggle -->
        <div class="bg-slate-50 rounded-xl p-4 mb-4">
          <div class="flex items-center justify-between">
            <div>
              <h3 class="font-semibold text-slate-800">Tryb DEV</h3>
              <p class="text-xs text-slate-500 mt-1">
                Pokazuje szczegóły techniczne i dane debugowania
              </p>
            </div>
            <button
              @click="localDevMode = !localDevMode"
              class="relative w-14 h-7 rounded-full transition-colors duration-200"
              :class="localDevMode ? 'bg-amber-500' : 'bg-slate-300'"
            >
              <span
                class="absolute top-0.5 left-0.5 w-6 h-6 bg-white rounded-full shadow transition-transform duration-200"
                :class="{ 'translate-x-7': localDevMode }"
              ></span>
            </button>
          </div>
        </div>
        
        <!-- DEV Mode Info -->
        <div v-if="localDevMode" class="bg-amber-50 border border-amber-200 rounded-xl p-4 mb-4">
          <h4 class="font-semibold text-amber-800 text-sm mb-2">
            🛠️ DEV Mode aktywny
          </h4>
          <ul class="text-xs text-amber-700 space-y-1">
            <li>• Tabela pokrycia danych (per kategoria)</li>
            <li>• Status providerów (Overpass/Google)</li>
            <li>• Raw/kept/rejected POI counts</li>
            <li>• Confidence breakdown</li>
          </ul>
        </div>
        
        <!-- Version Info -->
        <div class="text-xs text-slate-400 mt-6">
          <p>Loktis v1.0.0</p>
          <p class="mt-1">© 2024 Loktis</p>
        </div>
      </div>
    </div>
  </Transition>
</template>

<style scoped>
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.2s ease;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}

.slide-right-enter-active,
.slide-right-leave-active {
  transition: transform 0.25s ease;
}
.slide-right-enter-from,
.slide-right-leave-to {
  transform: translateX(100%);
}
</style>
