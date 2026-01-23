<script setup lang="ts">
import { useLayoutStore } from '../stores/layoutStore'

const layoutStore = useLayoutStore()

const modeButtons = [
  { label: 'Wybór', value: 'select', icon: 'pi pi-arrow-pointer' },
  { label: 'Ściana', value: 'wall', icon: 'pi pi-bars' },
  { label: 'Obiekt', value: 'object', icon: 'pi pi-box' },
  { label: 'Drzwi', value: 'door', icon: 'pi pi-home' },
]

const selectMode = (mode: any) => {
  layoutStore.setMode(mode)
}

const handleDeleteCurrent = () => {
  if (layoutStore.selectedObjectId) {
    layoutStore.removeElement(layoutStore.selectedObjectId)
    layoutStore.selectElement(null)
  }
}

const handleDeleteLayout = (id: number) => {
  const confirmed = window.confirm('Na pewno usunąć ten plan?')
  if (confirmed) {
    layoutStore.deleteLayout(id)
  }
}

const isCurrentMode = (mode: string) => layoutStore.mode === mode
</script>

<template>
  <div class="w-80 bg-white dark:bg-gray-900 border-r border-gray-200 dark:border-gray-700 flex flex-col">
    <!-- Header -->
    <div class="border-b border-gray-200 dark:border-gray-700 px-4 py-3">
      <h2 class="font-bold text-lg text-gray-900 dark:text-gray-100 flex items-center gap-2">
        <i class="pi pi-list"></i>
        Panel
      </h2>
    </div>

    <!-- Scrollable Content -->
    <div class="flex-1 overflow-y-auto">
      <!-- Mode Selector -->
      <div class="px-4 py-4 border-b border-gray-200 dark:border-gray-700">
        <h3 class="font-semibold text-sm text-gray-700 dark:text-gray-300 mb-3 flex items-center gap-2">
          <i class="pi pi-palette text-sm"></i>
          Tryb edycji
        </h3>
        <div class="space-y-2">
          <Button
            v-for="btn in modeButtons"
            :key="btn.value"
            :label="btn.label"
            :icon="btn.icon"
            class="w-full"
            size="small"
            :severity="isCurrentMode(btn.value) ? 'primary' : 'secondary'"
            @click="selectMode(btn.value)"
          />
        </div>
      </div>

      <!-- Layout List -->
      <div class="px-4 py-4 border-b border-gray-200 dark:border-gray-700">
        <h3 class="font-semibold text-sm text-gray-700 dark:text-gray-300 mb-3 flex items-center gap-2">
          <i class="pi pi-list text-sm"></i>
          Plany ({{ layoutStore.layouts.length }})
        </h3>

        <div v-if="layoutStore.loading" class="flex justify-center py-4">
          <ProgressSpinner style="width: 40px; height: 40px" stroke-width="4" />
        </div>

        <div v-else-if="!layoutStore.hasLayouts" class="text-center text-gray-500 py-4">
          <p class="text-sm mb-3">Brak planów</p>
          <Button
            label="Utwórz nowy"
            icon="pi pi-plus"
            class="w-full"
            size="small"
            @click="() => layoutStore.createLayout('Nowy plan')"
          />
        </div>

        <div v-else class="space-y-2 max-h-48 overflow-y-auto">
          <div
            v-for="layout in layoutStore.layouts"
            :key="layout.id"
            class="p-3 rounded-lg border-2 cursor-pointer transition-all hover:shadow-md"
            :class="
              layoutStore.currentLayout?.id === layout.id
                ? 'border-blue-500 bg-blue-50 dark:bg-blue-900/20'
                : 'border-gray-200 dark:border-gray-700 hover:border-blue-300'
            "
            @click="layoutStore.fetchLayout(layout.id)"
          >
            <div class="font-semibold text-sm text-gray-900 dark:text-gray-100 truncate">
              {{ layout.name }}
            </div>
            <div class="text-xs text-gray-500 dark:text-gray-400 truncate">
              {{ new Date(layout.updated_at).toLocaleDateString('pl-PL') }}
            </div>
          </div>
        </div>
      </div>

      <!-- Current Layout Info -->
      <div v-if="layoutStore.currentLayout" class="px-4 py-4 border-b border-gray-200 dark:border-gray-700">
        <h3 class="font-semibold text-sm text-gray-700 dark:text-gray-300 mb-3 flex items-center gap-2">
          <i class="pi pi-info-circle text-sm"></i>
          Informacje
        </h3>

        <div class="space-y-2 text-xs">
          <div class="flex justify-between">
            <span class="text-gray-600 dark:text-gray-400">Nazwa:</span>
            <span class="font-semibold text-gray-900 dark:text-gray-100">{{ layoutStore.layoutName }}</span>
          </div>
          <div class="flex justify-between">
            <span class="text-gray-600 dark:text-gray-400">Wymiary:</span>
            <span class="font-semibold text-gray-900 dark:text-gray-100">
              {{ layoutStore.layoutData?.width_cm }} × {{ layoutStore.layoutData?.height_cm }} cm
            </span>
          </div>
          <div class="flex justify-between">
            <span class="text-gray-600 dark:text-gray-400">Ścian:</span>
            <span class="font-semibold text-gray-900 dark:text-gray-100">
              {{ layoutStore.layoutData?.walls.length ?? 0 }}
            </span>
          </div>
          <div class="flex justify-between">
            <span class="text-gray-600 dark:text-gray-400">Obiektów:</span>
            <span class="font-semibold text-gray-900 dark:text-gray-100">
              {{ layoutStore.layoutData?.objects.length ?? 0 }}
            </span>
          </div>
          <div class="flex justify-between">
            <span class="text-gray-600 dark:text-gray-400">Drzwi:</span>
            <span class="font-semibold text-gray-900 dark:text-gray-100">
              {{ layoutStore.layoutData?.doors.length ?? 0 }}
            </span>
          </div>
        </div>

        <!-- Actions -->
        <div class="mt-4 space-y-2">
          <Button
            label="Usuń zaznaczone"
            icon="pi pi-trash"
            class="w-full"
            size="small"
            severity="danger"
            text
            :disabled="!layoutStore.selectedObjectId"
            @click="handleDeleteCurrent"
          />
          <Button
            label="Usuń plan"
            icon="pi pi-times-circle"
            class="w-full"
            size="small"
            severity="danger"
            @click="() => handleDeleteLayout(layoutStore.currentLayout!.id)"
          />
        </div>
      </div>

      <!-- Grid & Zoom -->
      <div class="px-4 py-4">
        <h3 class="font-semibold text-sm text-gray-700 dark:text-gray-300 mb-3 flex items-center gap-2">
          <i class="pi pi-sliders-h text-sm"></i>
          Widok
        </h3>

        <div class="space-y-3">
          <div class="flex items-center justify-between">
            <label class="text-sm text-gray-600 dark:text-gray-400">Grid</label>
            <ToggleButton
              v-model="layoutStore.showGrid"
              on-label="ON"
              off-label="OFF"
              severity="success"
            />
          </div>

          <div class="flex items-center gap-2">
            <Button
              icon="pi pi-minus"
              rounded
              text
              severity="secondary"
              size="small"
              @click="layoutStore.zoomOut"
            />
            <span class="text-sm text-gray-600 dark:text-gray-400 flex-1 text-center">
              {{ (layoutStore.scale * 100).toFixed(0) }}%
            </span>
            <Button
              icon="pi pi-plus"
              rounded
              text
              severity="secondary"
              size="small"
              @click="layoutStore.zoomIn"
            />
          </div>

          <Button
            label="Reset zoom"
            icon="pi pi-home"
            class="w-full"
            size="small"
            text
            @click="layoutStore.resetZoom"
          />
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped></style>
