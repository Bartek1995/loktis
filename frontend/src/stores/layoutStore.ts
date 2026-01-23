import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { Layout, LayoutData, Wall, FloorObject, Door } from '../types/layout'
import { layoutApi } from '../api/layoutApi'

export const useLayoutStore = defineStore('layout', () => {
  // State
  const layouts = ref<Layout[]>([])
  const currentLayout = ref<Layout | null>(null)
  const loading = ref(false)
  const error = ref<string | null>(null)

  // Current editing state
  const mode = ref<'wall' | 'object' | 'door' | 'select'>('wall')
  const selectedObjectId = ref<string | null>(null)
  const gridSize = ref(50) // pixels per 5cm
  const showGrid = ref(true)
  const scale = ref(1)

  // Getters
  const hasLayouts = computed(() => layouts.value.length > 0)
  const layoutName = computed(() => currentLayout.value?.name ?? 'Bez nazwy')
  const layoutData = computed(() => currentLayout.value?.layout_data)

  // Actions
  async function fetchLayouts() {
    loading.value = true
    error.value = null
    try {
      const { data } = await layoutApi.listLayouts()
      layouts.value = data
    } catch (err: any) {
      error.value = err.message ?? 'Błąd przy ładowaniu planów'
      console.error('Fetch layouts error:', err)
    } finally {
      loading.value = false
    }
  }

  async function fetchLayout(id: number) {
    loading.value = true
    error.value = null
    try {
      const { data } = await layoutApi.getLayout(id)
      currentLayout.value = data
    } catch (err: any) {
      error.value = err.message ?? 'Błąd przy ładowaniu planu'
      console.error('Fetch layout error:', err)
    } finally {
      loading.value = false
    }
  }

  async function createLayout(name: string, width: number = 500, height: number = 400) {
    error.value = null
    try {
      const layoutData: LayoutData = {
        width_cm: width,
        height_cm: height,
        walls: [],
        objects: [],
        doors: [],
      }
      const { data } = await layoutApi.createLayout({ name, layout_data: layoutData })
      layouts.value.push(data)
      currentLayout.value = data
      return data
    } catch (err: any) {
      error.value = err.message ?? 'Błąd przy tworzeniu planu'
      console.error('Create layout error:', err)
      throw err
    }
  }

  async function saveLayout() {
    if (!currentLayout.value) {
      error.value = 'Brak aktywnego planu'
      return
    }
    error.value = null
    try {
      const { data } = await layoutApi.updateLayout(currentLayout.value.id, {
        name: currentLayout.value.name,
        layout_data: currentLayout.value.layout_data,
      })
      currentLayout.value = data
      const idx = layouts.value.findIndex(l => l.id === data.id)
      if (idx >= 0) {
        layouts.value[idx] = data
      }
    } catch (err: any) {
      error.value = err.message ?? 'Błąd przy zapisie planu'
      console.error('Save layout error:', err)
      throw err
    }
  }

  async function deleteLayout(id: number) {
    error.value = null
    try {
      await layoutApi.deleteLayout(id)
      layouts.value = layouts.value.filter(l => l.id !== id)
      if (currentLayout.value?.id === id) {
        currentLayout.value = null
      }
    } catch (err: any) {
      error.value = err.message ?? 'Błąd przy usuwaniu planu'
      console.error('Delete layout error:', err)
      throw err
    }
  }

  // Editing actions
  function addWall(wall: Wall) {
    if (!currentLayout.value?.layout_data.walls) return
    if (!wall.id) wall.id = `wall-${Date.now()}`
    currentLayout.value.layout_data.walls.push(wall)
  }

  function addObject(obj: FloorObject) {
    if (!currentLayout.value?.layout_data.objects) return
    if (!obj.id) obj.id = `obj-${Date.now()}`
    currentLayout.value.layout_data.objects.push(obj)
  }

  function addDoor(door: Door) {
    if (!currentLayout.value?.layout_data.doors) return
    if (!door.id) door.id = `door-${Date.now()}`
    currentLayout.value.layout_data.doors.push(door)
  }

  function removeElement(id: string) {
    if (!currentLayout.value?.layout_data) return
    currentLayout.value.layout_data.walls = 
      currentLayout.value.layout_data.walls.filter(w => w.id !== id)
    currentLayout.value.layout_data.objects = 
      currentLayout.value.layout_data.objects.filter(o => o.id !== id)
    currentLayout.value.layout_data.doors = 
      currentLayout.value.layout_data.doors.filter(d => d.id !== id)
  }

  function setMode(newMode: 'wall' | 'object' | 'door' | 'select') {
    mode.value = newMode
    selectedObjectId.value = null
  }

  function selectElement(id: string | null) {
    selectedObjectId.value = id
    if (id) mode.value = 'select'
  }

  function toggleGrid() {
    showGrid.value = !showGrid.value
  }

  function zoomIn() {
    scale.value = Math.min(scale.value + 0.2, 3)
  }

  function zoomOut() {
    scale.value = Math.max(scale.value - 0.2, 0.5)
  }

  function resetZoom() {
    scale.value = 1
  }

  return {
    // State
    layouts,
    currentLayout,
    loading,
    error,
    mode,
    selectedObjectId,
    gridSize,
    showGrid,
    scale,

    // Getters
    hasLayouts,
    layoutName,
    layoutData,

    // Actions
    fetchLayouts,
    fetchLayout,
    createLayout,
    saveLayout,
    deleteLayout,
    addWall,
    addObject,
    addDoor,
    removeElement,
    setMode,
    selectElement,
    toggleGrid,
    zoomIn,
    zoomOut,
    resetZoom,
  }
})
