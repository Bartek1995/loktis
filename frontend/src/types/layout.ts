export interface Layout {
  id: number
  name: string
  layout_data: LayoutData
  created_at: string
  updated_at: string
}

export interface LayoutData {
  width_cm: number
  height_cm: number
  walls: Wall[]
  objects: FloorObject[]
  doors: Door[]
  grid_cells?: GridCells
}

export interface Wall {
  id?: string
  x1: number
  y1: number
  x2: number
  y2: number
  thickness?: number
}

export interface FloorObject {
  id?: string
  x: number
  y: number
  w: number
  h: number
  type: string
  name?: string
  rotation?: number
}

export interface Door {
  id?: string
  x: number
  y: number
  w: number
  h: number
  swing?: 'left' | 'right' | 'double'
}

export interface GridCells {
  width: number
  height: number
  occupied: boolean[][]
}
