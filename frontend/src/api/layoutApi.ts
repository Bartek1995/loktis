import axios from 'axios'
import type { Layout, LayoutData } from '../types/layout'

const API_BASE = 'http://localhost:8000/api'

const api = axios.create({
  baseURL: API_BASE,
  headers: {
    'Content-Type': 'application/json',
  },
})

export const layoutApi = {
  // List all layouts
  listLayouts: () => api.get<Layout[]>('/layouts/'),

  // Get single layout
  getLayout: (id: number) => api.get<Layout>(`/layouts/${id}/`),

  // Create new layout
  createLayout: (data: { name: string; layout_data: LayoutData }) =>
    api.post<Layout>('/layouts/', data),

  // Update layout
  updateLayout: (id: number, data: { name?: string; layout_data?: LayoutData }) =>
    api.put<Layout>(`/layouts/${id}/`, data),

  // Partial update
  patchLayout: (id: number, data: Partial<Layout>) =>
    api.patch<Layout>(`/layouts/${id}/`, data),

  // Delete layout
  deleteLayout: (id: number) => api.delete(`/layouts/${id}/`),

  // Search layouts
  searchLayouts: (query: string) => 
    api.get<Layout[]>('/layouts/', { params: { search: query } }),
}

export default api
