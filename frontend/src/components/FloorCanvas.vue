<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useLayoutStore } from '../stores/layoutStore'
import type { Wall } from '../types/layout'

const layoutStore = useLayoutStore()

const svgCanvas = ref<SVGElement | null>(null)
const startX = ref(0)
const startY = ref(0)
const panX = ref(0)
const panY = ref(0)
const isDragging = ref(false)

const SCALE_PX_PER_CM = 2 // 1cm = 2px
const GRID_SIZE = 50 // 50px = 5cm

const canvasWidth = computed(() => (layoutStore.layoutData?.width_cm ?? 500) * SCALE_PX_PER_CM)
const canvasHeight = computed(() => (layoutStore.layoutData?.height_cm ?? 400) * SCALE_PX_PER_CM)

const transformStyle = computed(() => {
  return `translate(${panX.value}px, ${panY.value}px) scale(${layoutStore.scale})`
})

const onMouseDown = (e: MouseEvent) => {
  if (layoutStore.mode === 'select') {
    isDragging.value = true
    startX.value = e.clientX - panX.value
    startY.value = e.clientY - panY.value
  }
}

const onMouseMove = (e: MouseEvent) => {
  if (!isDragging.value) return
  panX.value = e.clientX - startX.value
  panY.value = e.clientY - startY.value
}

const onMouseUp = () => {
  isDragging.value = false
}

const onWheel = (e: WheelEvent) => {
  e.preventDefault()
  if (e.deltaY < 0) {
    layoutStore.zoomIn()
  } else {
    layoutStore.zoomOut()
  }
}

const handleCanvasClick = (e: MouseEvent) => {
  if (layoutStore.mode === 'wall') {
    const rect = svgCanvas.value?.getBoundingClientRect()
    if (rect) {
      const x = (e.clientX - rect.left - panX.value) / layoutStore.scale
      const y = (e.clientY - rect.top - panY.value) / layoutStore.scale
      // Simplified: just add a small wall
      const wall: Wall = {
        x1: Math.round(x / GRID_SIZE) * GRID_SIZE,
        y1: Math.round(y / GRID_SIZE) * GRID_SIZE,
        x2: Math.round(x / GRID_SIZE) * GRID_SIZE + GRID_SIZE,
        y2: Math.round(y / GRID_SIZE) * GRID_SIZE,
      }
      layoutStore.addWall(wall)
    }
  }
}

const deleteKeyListener = (e: KeyboardEvent) => {
  if (e.key === 'Delete' && layoutStore.selectedObjectId) {
    layoutStore.removeElement(layoutStore.selectedObjectId)
    layoutStore.selectElement(null)
  }
  if (e.key === 's' && e.ctrlKey) {
    e.preventDefault()
    layoutStore.saveLayout()
  }
}

onMounted(() => {
  window.addEventListener('mousemove', onMouseMove)
  window.addEventListener('mouseup', onMouseUp)
  window.addEventListener('keydown', deleteKeyListener)
})

watch(
  () => layoutStore.scale,
  () => {
    // Zoom changed
  }
)
</script>

<template>
  <div class="flex-1 flex flex-col gap-3 overflow-hidden rounded-lg border border-surface-200 dark:border-surface-700 bg-surface-50 dark:bg-surface-900">
    <!-- Toolbar -->
    <div class="flex items-center gap-2 p-3 border-b border-surface-200 dark:border-surface-700">
      <Button
        icon="pi pi-plus"
        rounded
        text
        @click="layoutStore.zoomIn"
        v-tooltip="'Przybliż (Scroll)'"
      />
      <Button
        icon="pi pi-minus"
        rounded
        text
        @click="layoutStore.zoomOut"
        v-tooltip="'Oddal'"
      />
      <Button
        icon="pi pi-home"
        rounded
        text
        @click="layoutStore.resetZoom"
        v-tooltip="'Resetuj zoom'"
      />
      <Divider layout="vertical" class="my-0" />
      <span class="text-sm text-muted-color">Zoom: {{ (layoutStore.scale * 100).toFixed(0) }}%</span>

      <Divider layout="vertical" class="my-0" />
      <ToggleButton
        v-model="layoutStore.showGrid"
        icon="pi pi-table"
        on-label="Grid: ON"
        off-label="Grid: OFF"
        :style="{ width: '100px' }"
      />

      <Divider layout="vertical" class="my-0" />
      <span class="text-sm text-muted-color flex-1">Tryb: <strong>{{ layoutStore.mode }}</strong></span>
    </div>

    <!-- Canvas Area -->
    <div class="flex-1 overflow-auto cursor-move" @mousedown="onMouseDown" @wheel="onWheel">
      <svg
        ref="svgCanvas"
        :viewBox="`0 0 ${canvasWidth} ${canvasHeight}`"
        :width="canvasWidth * layoutStore.scale"
        :height="canvasHeight * layoutStore.scale"
        class="bg-white dark:bg-surface-800 border border-surface-300 dark:border-surface-700 select-none"
        :style="{ transform: transformStyle, transformOrigin: '0 0', transition: 'transform 0.1s' }"
        @click="handleCanvasClick"
      >
        <!-- Grid -->
        <defs>
          <pattern id="smallGrid" :width="GRID_SIZE" :height="GRID_SIZE" patternUnits="userSpaceOnUse">
            <path
              :d="`M ${GRID_SIZE} 0 L 0 0 0 ${GRID_SIZE}`"
              fill="none"
              stroke="#e0e0e0"
              stroke-width="0.5"
            />
          </pattern>
          <pattern id="grid" :width="GRID_SIZE * 5" :height="GRID_SIZE * 5" patternUnits="userSpaceOnUse">
            <rect :width="GRID_SIZE * 5" :height="GRID_SIZE * 5" fill="url(#smallGrid)" />
            <path :d="`M ${GRID_SIZE * 5} 0 L 0 0 0 ${GRID_SIZE * 5}`" fill="none" stroke="#bdbdbd" stroke-width="1" />
          </pattern>
        </defs>

        <!-- Background grid -->
        <rect
          v-if="layoutStore.showGrid"
          :width="canvasWidth"
          :height="canvasHeight"
          fill="url(#grid)"
        />

        <!-- Walls -->
        <line
          v-for="(wall, idx) in layoutStore.layoutData?.walls"
          :key="`wall-${idx}`"
          :x1="wall.x1"
          :y1="wall.y1"
          :x2="wall.x2"
          :y2="wall.y2"
          stroke="#333"
          :stroke-width="wall.thickness ?? 8"
          stroke-linecap="round"
          @click.stop="layoutStore.selectElement(wall.id!)"
          :class="{ 'opacity-70': layoutStore.selectedObjectId === wall.id }"
          class="cursor-pointer hover:opacity-50 transition-opacity"
        />

        <!-- Objects -->
        <g v-for="(obj, idx) in layoutStore.layoutData?.objects" :key="`obj-${idx}`">
          <rect
            :x="obj.x"
            :y="obj.y"
            :width="obj.w"
            :height="obj.h"
            :transform="`rotate(${obj.rotation ?? 0} ${obj.x + obj.w / 2} ${obj.y + obj.h / 2})`"
            :fill="layoutStore.selectedObjectId === obj.id ? '#42b883' : '#3498db'"
            fill-opacity="0.8"
            stroke="#2c3e50"
            stroke-width="2"
            rx="4"
            @click.stop="layoutStore.selectElement(obj.id!)"
            class="cursor-pointer hover:fill-opacity-100 transition-all"
          />
          <text
            :x="obj.x + obj.w / 2"
            :y="obj.y + obj.h / 2"
            text-anchor="middle"
            dominant-baseline="middle"
            class="pointer-events-none"
            font-size="12"
            fill="white"
            font-weight="bold"
          >
            {{ obj.type }}
          </text>
        </g>

        <!-- Doors -->
        <g v-for="(door, idx) in layoutStore.layoutData?.doors" :key="`door-${idx}`">
          <rect
            :x="door.x"
            :y="door.y"
            :width="door.w"
            :height="door.h"
            :fill="layoutStore.selectedObjectId === door.id ? '#e74c3c' : '#f39c12'"
            fill-opacity="0.7"
            stroke="#2c3e50"
            stroke-width="2"
            @click.stop="layoutStore.selectElement(door.id!)"
            class="cursor-pointer hover:fill-opacity-100 transition-all"
          />
        </g>
      </svg>
    </div>

    <!-- Status Bar -->
    <div class="p-3 border-t border-surface-200 dark:border-surface-700 text-xs text-muted-color">
      <span>Ścian: {{ layoutStore.layoutData?.walls.length ?? 0 }}</span>
      <span class="mx-2">|</span>
      <span>Obiektów: {{ layoutStore.layoutData?.objects.length ?? 0 }}</span>
      <span class="mx-2">|</span>
      <span>Drzwi: {{ layoutStore.layoutData?.doors.length ?? 0 }}</span>
    </div>
  </div>
</template>

<style scoped>
svg {
  cursor: crosshair;
}
</style>
