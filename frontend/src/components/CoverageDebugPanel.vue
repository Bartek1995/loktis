<script setup lang="ts">
interface CategoryCoverage {
  source: string
  // SEMANTIC STATUS:
  // - "ok": >= 3 kept, normal data
  // - "partial": 1-2 kept, sparse but valid
  // - "empty": 0 kept, provider OK → SIGNAL (valid result, not error!)
  // - "error": provider failure → DATA QUALITY ISSUE
  status: string
  raw_count: number
  kept_count: number
  radius_m: number
  rejects: Record<string, number>  // {"radius": 30, "membership": 4}
  provider_errors: string[]
  had_provider_error?: boolean
}

interface DataQuality {
  confidence_pct: number
  reasons: string[]
  overpass_status: string
  overpass_had_retry?: boolean
  fallback_started: string[]  // Categories where fallback was initiated
  fallback_contributed: string[]  // Categories where fallback added POIs
  cache_used: boolean
  empty_categories: string[]  // Signal zeros (valid, not error)
  error_categories: string[]  // Data quality issues
  coverage: Record<string, CategoryCoverage>
}

defineProps<{
  dataQuality: DataQuality | null
}>()

function getStatusColor(status: string): string {
  switch (status) {
    case 'ok': return 'bg-emerald-100 text-emerald-700'
    case 'partial': return 'bg-amber-100 text-amber-700'
    case 'empty': return 'bg-slate-200 text-slate-600'  // Neutral - not error!
    case 'error': return 'bg-red-200 text-red-800'
    default: return 'bg-slate-100 text-slate-700'
  }
}

function getStatusTooltip(status: string): string {
  switch (status) {
    case 'ok': return 'Dobre pokrycie (≥3 POI)'
    case 'partial': return 'Częściowe pokrycie (1-2 POI)'
    case 'empty': return 'Brak w promieniu (sygnał, nie błąd)'
    case 'error': return 'Błąd źródła danych'
    default: return status
  }
}

function getConfidenceColor(pct: number): string {
  if (pct >= 80) return 'text-emerald-400'
  if (pct >= 60) return 'text-amber-400'
  return 'text-red-400'
}

function getCategoryLabel(cat: string): string {
  const labels: Record<string, string> = {
    shops: 'Sklepy',
    transport: 'Transport',
    education: 'Edukacja',
    health: 'Zdrowie',
    nature_place: 'Zieleń',
    nature_background: 'Tło zieleni',
    leisure: 'Rekreacja',
    food: 'Gastronomia',
    finance: 'Finanse',
    roads: 'Drogi',
    car_access: 'Dostęp auto',
  }
  return labels[cat] || cat
}

function formatRejects(rejects: Record<string, number>): string {
  if (!rejects || Object.keys(rejects).length === 0) return '-'
  return Object.entries(rejects).map(([k, v]) => `${k}:${v}`).join(' ')
}
</script>

<template>
  <div v-if="dataQuality" class="bg-slate-900 text-slate-100 rounded-xl p-4 mb-6 font-mono text-xs">
    <!-- Header -->
    <div class="flex items-center justify-between mb-4">
      <div class="flex items-center gap-2">
        <span class="text-amber-400">🛠️</span>
        <span class="font-bold text-amber-400">DEV: Data Coverage</span>
      </div>
      <div class="flex items-center gap-4">
        <span :class="getConfidenceColor(dataQuality.confidence_pct)">
          Confidence: {{ dataQuality.confidence_pct }}%
        </span>
        <span class="text-slate-500">
          Cache: {{ dataQuality.cache_used ? '✓' : '✗' }}
        </span>
        <span :class="dataQuality.overpass_status === 'ok' ? 'text-emerald-400' : 'text-amber-400'">
          Overpass: {{ dataQuality.overpass_status }}
          <span v-if="dataQuality.overpass_had_retry" class="text-amber-400">(retry)</span>
        </span>
      </div>
    </div>
    
    <!-- Reasons (if any) - these are DATA QUALITY issues -->
    <div v-if="dataQuality.reasons?.length" class="mb-4 p-2 bg-red-900/30 rounded border border-red-700">
      <div class="text-red-400 font-semibold mb-1">⚠️ Data quality issues:</div>
      <ul>
        <li v-for="(reason, idx) in dataQuality.reasons" :key="idx" class="text-red-300">
          • {{ reason }}
        </li>
      </ul>
    </div>
    
    <!-- Coverage Table -->
    <table class="w-full">
      <thead>
        <tr class="text-slate-400 border-b border-slate-700">
          <th class="text-left py-1 px-2">Category</th>
          <th class="text-left py-1 px-2">Source</th>
          <th class="text-left py-1 px-2">Status</th>
          <th class="text-right py-1 px-2">Raw→Kept</th>
          <th class="text-right py-1 px-2">Radius</th>
          <th class="text-left py-1 px-2">Rejects</th>
        </tr>
      </thead>
      <tbody>
        <tr 
          v-for="(cov, cat) in dataQuality.coverage" 
          :key="cat"
          class="border-b border-slate-800 hover:bg-slate-800/50"
        >
          <td class="py-1 px-2 font-semibold">{{ getCategoryLabel(cat as string) }}</td>
          <td class="py-1 px-2">{{ cov.source }}</td>
          <td class="py-1 px-2">
            <span 
              :class="['px-2 py-0.5 rounded text-xs cursor-help', getStatusColor(cov.status)]"
              :title="getStatusTooltip(cov.status)"
            >
              {{ cov.status }}
            </span>
          </td>
          <td class="py-1 px-2 text-right">
            <span class="text-slate-500">{{ cov.raw_count }}</span>
            <span class="text-slate-600 mx-1">→</span>
            <span :class="cov.kept_count > 0 ? 'text-emerald-400' : (cov.status === 'error' ? 'text-red-400' : 'text-slate-400')">
              {{ cov.kept_count }}
            </span>
          </td>
          <td class="py-1 px-2 text-right text-slate-400">{{ cov.radius_m }}m</td>
          <td class="py-1 px-2 text-slate-500">{{ formatRejects(cov.rejects) }}</td>
        </tr>
      </tbody>
    </table>
    
    <!-- Fallback Info (improved) -->
    <div class="mt-3 flex flex-wrap gap-4 text-slate-400">
      <!-- Fallback started -->
      <div v-if="dataQuality.fallback_started?.length">
        <span class="text-slate-500">Fallback started:</span>
        <span 
          v-for="cat in dataQuality.fallback_started" 
          :key="cat" 
          class="ml-2 px-2 py-0.5 bg-blue-900/50 text-blue-300 rounded text-xs"
        >
          {{ cat }}
        </span>
      </div>
      
      <!-- Fallback contributed -->
      <div v-if="dataQuality.fallback_contributed?.length">
        <span class="text-slate-500">Fallback contributed:</span>
        <span 
          v-for="cat in dataQuality.fallback_contributed" 
          :key="cat" 
          class="ml-2 px-2 py-0.5 bg-emerald-900/50 text-emerald-300 rounded text-xs"
        >
          {{ cat }}
        </span>
      </div>
    </div>
    
    <!-- Quick summary -->
    <div class="mt-3 pt-3 border-t border-slate-700 flex gap-4 text-xs">
      <span v-if="dataQuality.error_categories?.length" class="text-red-400">
        ⚠️ Errors: {{ dataQuality.error_categories.join(', ') }}
      </span>
      <span v-if="dataQuality.empty_categories?.length" class="text-slate-500">
        ∅ Empty (signal): {{ dataQuality.empty_categories.join(', ') }}
      </span>
      <span v-if="!dataQuality.error_categories?.length && !dataQuality.empty_categories?.length" class="text-emerald-400">
        ✓ All categories have data
      </span>
    </div>
  </div>
</template>
