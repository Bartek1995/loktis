<script setup lang="ts">
/**
 * Report View - wyświetla raport z analizy
 */
import { ref, computed, onMounted, nextTick, watch } from 'vue';
import { useRouter, useRoute } from 'vue-router';
import { analyzerApi, type AnalysisReport, type POICategoryStats } from '@/api/analyzerApi';
import ToggleSwitch from 'primevue/toggleswitch';
import * as L from 'leaflet';
import 'leaflet/dist/leaflet.css';

// Fix Leaflet icons
import markerIcon2x from 'leaflet/dist/images/marker-icon-2x.png';
import markerIcon from 'leaflet/dist/images/marker-icon.png';
import markerShadow from 'leaflet/dist/images/marker-shadow.png';

delete (L.Icon.Default.prototype as any)._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: markerIcon2x,
  iconUrl: markerIcon,
  shadowUrl: markerShadow,
});

// Google Maps types
declare global {
  interface Window {
    google: any;
    initGoogleMaps: () => void;
  }
}

const router = useRouter();
const route = useRoute();

// Map type options
type MapType = 'osm' | 'google';
const mapTypeOptions = [
  { label: 'OpenStreetMap', value: 'osm' },
  { label: 'Google Maps', value: 'google' },
];
const selectedMapType = ref<MapType>('osm');
const googleMapsLoaded = ref(false);
const googleMapsError = ref('');

// State
const report = ref<AnalysisReport | null>(null);
const originalUrl = ref('');
const isLoading = ref(false);
const error = ref('');
const mapContainer = ref<HTMLElement | null>(null);
const map = ref<L.Map | null>(null);
const googleMap = ref<any>(null);
const googleMarkers = ref<any[]>([]);
const leafletPoiMarkers = ref<L.CircleMarker[]>([]);

// Category visibility state (all visible by default)
const categoryVisibility = ref<Record<string, boolean>>({
  shops: true,
  transport: true,
  education: true,
  health: true,
  leisure: true,
  food: true,
  finance: true,
});

// Toggle category visibility
function toggleCategoryVisibility(category: string) {
  categoryVisibility.value[category] = !categoryVisibility.value[category];
  updateMapMarkers();
}

// Update map markers based on visibility
function updateMapMarkers() {
  if (selectedMapType.value === 'google' && googleMap.value) {
    updateGoogleMapMarkers();
  } else if (map.value) {
    updateLeafletMarkers();
  }
}

// Update Leaflet markers visibility
function updateLeafletMarkers() {
  leafletPoiMarkers.value.forEach(marker => {
    const category = (marker as any)._category;
    if (category && categoryVisibility.value[category] !== undefined) {
      if (categoryVisibility.value[category]) {
        marker.addTo(map.value as any);
      } else {
        marker.remove();
      }
    }
  });
}

// Update Google Maps markers visibility
function updateGoogleMapMarkers() {
  googleMarkers.value.forEach(marker => {
    const category = marker._category;
    if (category && categoryVisibility.value[category] !== undefined) {
      marker.setVisible(categoryVisibility.value[category]);
    }
  });
}

// Computed
const hasReport = computed(() => report.value !== null);

const scoreColor = computed(() => {
  const score = report.value?.neighborhood?.score;
  if (score === null || score === undefined) return 'secondary';
  if (score >= 70) return 'success';
  if (score >= 50) return 'info';
  if (score >= 30) return 'warn';
  return 'danger';
});

const scoreLabel = computed(() => {
  const score = report.value?.neighborhood?.score;
  if (score === null || score === undefined) return 'Brak danych';
  if (score >= 70) return 'Bardzo dobra';
  if (score >= 50) return 'Dobra';
  if (score >= 30) return 'Przeciętna';
  return 'Słaba';
});

// Methods
function goBack() {
  router.push({ name: 'landing' });
}

function analyzeAnother() {
  router.push({ name: 'landing' });
}

function openOriginalUrl() {
  if (report.value?.listing?.url) {
    window.open(report.value.listing.url, '_blank');
  }
}

function formatPrice(price: number | null): string {
  if (!price) return '-';
  return new Intl.NumberFormat('pl-PL', {
    style: 'currency',
    currency: 'PLN',
    maximumFractionDigits: 0,
  }).format(price);
}

function formatPricePerSqm(price: number | null): string {
  if (!price) return '-';
  return new Intl.NumberFormat('pl-PL', {
    style: 'currency',
    currency: 'PLN',
    maximumFractionDigits: 0,
  }).format(price) + '/m²';
}

function getCategoryIcon(category: string): string {
  const icons: Record<string, string> = {
    shops: 'pi-shopping-cart',
    transport: 'pi-car',
    education: 'pi-book',
    health: 'pi-heart',
    leisure: 'pi-sun',
    food: 'pi-shopping-bag',
    finance: 'pi-wallet',
  };
  return icons[category] || 'pi-map-marker';
}

function getCategoryName(category: string): string {
  const names: Record<string, string> = {
    shops: 'Sklepy',
    transport: 'Transport',
    education: 'Edukacja',
    health: 'Zdrowie',
    leisure: 'Rekreacja',
    food: 'Gastronomia',
    finance: 'Finanse',
  };
  return names[category] || category;
}

function getCategoryColor(category: string): string {
  const colors: Record<string, string> = {
    shops: '#8B5CF6',      // violet
    transport: '#3B82F6',  // blue
    education: '#F59E0B',  // amber
    health: '#EF4444',     // red
    leisure: '#10B981',    // emerald
    food: '#F97316',       // orange
    finance: '#6366F1',    // indigo
  };
  return colors[category] || '#6B7280';
}

function getRatingSeverity(rating: string): string {
  const map: Record<string, string> = {
    doskonale: 'success',
    dobrze: 'info',
    ok: 'warn',
    daleko: 'danger',
    brak: 'secondary',
  };
  return map[rating] || 'secondary';
}

// Load Google Maps API dynamically
function loadGoogleMapsApi(): Promise<void> {
  return new Promise((resolve, reject) => {
    if (window.google?.maps) {
      googleMapsLoaded.value = true;
      resolve();
      return;
    }
    
    const apiKey = import.meta.env.VITE_GOOGLE_MAPS_API_KEY;
    if (!apiKey || apiKey === 'your_google_maps_api_key_here') {
      googleMapsError.value = 'Brak klucza Google Maps API. Dodaj VITE_GOOGLE_MAPS_API_KEY do pliku .env';
      reject(new Error('Missing Google Maps API key'));
      return;
    }
    
    const script = document.createElement('script');
    script.src = `https://maps.googleapis.com/maps/api/js?key=${apiKey}`;
    script.async = true;
    script.defer = true;
    
    script.onload = () => {
      googleMapsLoaded.value = true;
      resolve();
    };
    
    script.onerror = () => {
      googleMapsError.value = 'Nie udało się załadować Google Maps API';
      reject(new Error('Failed to load Google Maps'));
    };
    
    document.head.appendChild(script);
  });
}

// Cleanup maps
function cleanupMaps() {
  // Cleanup Leaflet POI markers
  leafletPoiMarkers.value.forEach(marker => marker.remove());
  leafletPoiMarkers.value = [];
  
  // Cleanup Leaflet map
  if (map.value) {
    map.value.remove();
    map.value = null;
  }
  
  // Cleanup Google Maps markers
  googleMarkers.value.forEach(marker => marker.setMap(null));
  googleMarkers.value = [];
  googleMap.value = null;
}

// Initialize OpenStreetMap (Leaflet)
function initLeafletMap() {
  if (!report.value?.listing.latitude || !report.value?.listing.longitude || !mapContainer.value) return;
  
  cleanupMaps();
  
  const lat = report.value.listing.latitude;
  const lon = report.value.listing.longitude;
  
  map.value = L.map(mapContainer.value).setView([lat, lon], 15);
  
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '© OpenStreetMap contributors'
  }).addTo(map.value as any);
  
  // Main marker
  L.marker([lat, lon]).addTo(map.value as any)
    .bindPopup('<b>' + (report.value.listing.title || 'Nieruchomość') + '</b>')
    .openPopup();
    
  // Add POI markers
  if (report.value.neighborhood.markers) {
    report.value.neighborhood.markers.forEach(poi => {
      const color = poi.color || 'blue';
      const circle = L.circleMarker([poi.lat, poi.lon], {
        radius: 6,
        fillColor: color,
        color: '#fff',
        weight: 1,
        opacity: 1,
        fillOpacity: 0.8
      });
      
      // Store category for visibility toggling
      (circle as any)._category = poi.category;
      
      // Only add if category is visible
      if (categoryVisibility.value[poi.category] !== false) {
        circle.addTo(map.value as any);
      }
      
      circle.bindPopup(`
        <b>${poi.name}</b><br>
        <span class="text-xs text-gray-500">${poi.subcategory} (${Math.round(poi.distance || 0)}m)</span>
      `);
      
      // Track marker for visibility updates
      leafletPoiMarkers.value.push(circle);
    });
  }
}

// Initialize Google Maps
async function initGoogleMap() {
  if (!report.value?.listing.latitude || !report.value?.listing.longitude || !mapContainer.value) return;
  
  try {
    await loadGoogleMapsApi();
  } catch (e) {
    // Error already set in loadGoogleMapsApi
    return;
  }
  
  cleanupMaps();
  
  const lat = report.value.listing.latitude;
  const lon = report.value.listing.longitude;
  
  googleMap.value = new window.google.maps.Map(mapContainer.value, {
    center: { lat, lng: lon },
    zoom: 15,
    mapTypeId: 'roadmap',
  });
  
  // Main marker
  const mainMarker = new window.google.maps.Marker({
    position: { lat, lng: lon },
    map: googleMap.value,
    title: report.value.listing.title || 'Nieruchomość',
  });
  
  const infoWindow = new window.google.maps.InfoWindow({
    content: `<b>${report.value.listing.title || 'Nieruchomość'}</b>`,
  });
  infoWindow.open(googleMap.value, mainMarker);
  googleMarkers.value.push(mainMarker);
  
  // Add POI markers
  if (report.value.neighborhood.markers) {
    report.value.neighborhood.markers.forEach(poi => {
      const color = poi.color || 'blue';
      const isVisible = categoryVisibility.value[poi.category] !== false;
      
      const marker = new window.google.maps.Marker({
        position: { lat: poi.lat, lng: poi.lon },
        map: googleMap.value,
        visible: isVisible,
        icon: {
          path: window.google.maps.SymbolPath.CIRCLE,
          scale: 8,
          fillColor: color,
          fillOpacity: 0.8,
          strokeColor: '#fff',
          strokeWeight: 1,
        },
      });
      
      // Store category for visibility toggling
      marker._category = poi.category;
      
      const poiInfoWindow = new window.google.maps.InfoWindow({
        content: `<b>${poi.name}</b><br><span style="font-size: 12px; color: #666;">${poi.subcategory} (${Math.round(poi.distance || 0)}m)</span>`,
      });
      
      marker.addListener('click', () => {
        poiInfoWindow.open(googleMap.value, marker);
      });
      
      googleMarkers.value.push(marker);
    });
  }
}

// Main init function that routes to correct map type
function initMap() {
  if (selectedMapType.value === 'google') {
    initGoogleMap();
  } else {
    initLeafletMap();
  }
}

// Watch for map type changes
watch(selectedMapType, () => {
  if (report.value) {
    nextTick(initMap);
  }
});

// Load report
onMounted(async () => {
  // Sprawdź czy raport przyszedł z nowej analizy (przez sessionStorage)
  if (route.query.fromAnalysis === 'true') {
    const storedReport = sessionStorage.getItem('lastReport');
    const storedUrl = sessionStorage.getItem('lastReportUrl');
    if (storedReport) {
      try {
        report.value = JSON.parse(storedReport);
        originalUrl.value = storedUrl || '';
        // Wyczyść po odczytaniu
        sessionStorage.removeItem('lastReport');
        sessionStorage.removeItem('lastReportUrl');
        nextTick(initMap);
        return;
      } catch (e) {
        console.error('Błąd parsowania raportu z sessionStorage', e);
      }
    }
  }
  
  // Sprawdź czy mamy ID w route (z historii)
  const id = route.params.id;
  if (id) {
    isLoading.value = true;
    try {
      report.value = await analyzerApi.getHistoryDetail(Number(id));
      nextTick(initMap);
    } catch (e) {
      error.value = 'Nie udało się pobrać raportu';
    } finally {
      isLoading.value = false;
    }
    return;
  }
  
  // Brak danych - wróć na landing
  router.replace({ name: 'landing' });
});
</script>

<template>
  <div class="min-h-screen bg-gradient-to-br from-surface-50 via-white to-primary-50 dark:from-surface-900 dark:via-surface-800 dark:to-surface-900 p-4 md:p-6">
    <div class="max-w-5xl mx-auto">
    <!-- Loading - Modern animated -->
    <div v-if="isLoading" class="flex flex-col justify-center items-center min-h-96 gap-4">
      <div class="w-20 h-20 rounded-2xl bg-gradient-to-br from-primary-400 to-primary-600 flex items-center justify-center shadow-xl">
        <ProgressSpinner style="width: 40px; height: 40px" strokeWidth="4" fill="transparent" animationDuration=".8s" />
      </div>
      <p class="text-surface-500 font-medium">Ładowanie raportu...</p>
    </div>
    
    <!-- Error -->
    <Message v-else-if="error" severity="error" :closable="false">
      {{ error }}
    </Message>
    
    <!-- Report -->
    <div v-else-if="hasReport" class="flex flex-col gap-6">
      <!-- Header - Modern gradient banner -->
      <div class="relative overflow-hidden bg-gradient-to-br from-white to-surface-50 dark:from-surface-800 dark:to-surface-900 rounded-2xl p-6 shadow-lg border border-surface-100 dark:border-surface-700">
        <!-- Decorative accent -->
        <div class="absolute top-0 left-0 right-0 h-1 bg-gradient-to-r from-primary-400 via-primary-500 to-primary-600"></div>
        
        <div class="flex flex-wrap justify-between items-start gap-4">
          <div class="flex-1 min-w-0">
            <Button icon="pi pi-arrow-left" text rounded @click="goBack" class="mb-3 !-ml-2" />
            <h1 class="text-2xl md:text-3xl font-bold text-surface-900 dark:text-surface-100 mb-2">
              {{ report!.listing.title || 'Analiza ogłoszenia' }}
            </h1>
            <p v-if="report!.listing.location" class="flex items-center gap-2 text-surface-500">
              <span class="inline-flex items-center justify-center w-6 h-6 rounded-full bg-primary-100 dark:bg-primary-900">
                <i class="pi pi-map-marker text-primary-500 text-sm"></i>
              </span>
              {{ report!.listing.location }}
            </p>
          </div>
          <div class="flex gap-2 flex-shrink-0">
            <Button 
              label="Zobacz ogłoszenie" 
              icon="pi pi-external-link" 
              severity="secondary"
              outlined
              class="!rounded-xl"
              @click="openOriginalUrl"
            />
            <Button 
              label="Analizuj kolejne" 
              icon="pi pi-plus"
              class="!rounded-xl !bg-gradient-to-r !from-primary-500 !to-primary-600 !border-0"
              @click="analyzeAnother"
            />
          </div>
        </div>
      </div>
      
      <!-- Errors/Warnings -->
      <Message v-for="err in report!.errors" :key="err" severity="error" :closable="false">
        {{ err }}
      </Message>
      <Message v-for="warn in report!.warnings" :key="warn" severity="warn" :closable="false">
        {{ warn }}
      </Message>
      
      <!-- TL;DR Section - Modern split design -->
      <div class="grid grid-cols-1 md:grid-cols-2 gap-5">
        <!-- Plusy -->
        <div class="relative bg-gradient-to-br from-emerald-50 to-green-50 dark:from-emerald-900/20 dark:to-green-900/20 rounded-2xl p-6 shadow-lg border border-emerald-100 dark:border-emerald-800/50 overflow-hidden">
          <div class="absolute top-0 left-0 right-0 h-1 bg-gradient-to-r from-emerald-400 to-green-500"></div>
          
          <div class="flex items-center gap-3 mb-5">
            <div class="w-12 h-12 rounded-xl bg-gradient-to-br from-emerald-400 to-green-500 flex items-center justify-center shadow-lg">
              <i class="pi pi-check-circle text-xl text-white"></i>
            </div>
            <div>
              <h3 class="font-bold text-lg text-surface-800 dark:text-surface-100">Plusy</h3>
              <p class="text-sm text-emerald-600 dark:text-emerald-400">{{ report!.tldr.pros.length }} zalet</p>
            </div>
          </div>
          
          <ul class="space-y-3">
            <li v-for="pro in report!.tldr.pros" :key="pro" class="flex items-start gap-3 p-3 bg-white/60 dark:bg-surface-800/40 rounded-xl">
              <span class="flex-shrink-0 w-6 h-6 rounded-full bg-emerald-500 flex items-center justify-center mt-0.5">
                <i class="pi pi-check text-white text-xs"></i>
              </span>
              <span class="text-surface-700 dark:text-surface-200">{{ pro }}</span>
            </li>
          </ul>
        </div>
        
        <!-- Ryzyka -->
        <div class="relative bg-gradient-to-br from-orange-50 to-amber-50 dark:from-orange-900/20 dark:to-amber-900/20 rounded-2xl p-6 shadow-lg border border-orange-100 dark:border-orange-800/50 overflow-hidden">
          <div class="absolute top-0 left-0 right-0 h-1 bg-gradient-to-r from-orange-400 to-amber-500"></div>
          
          <div class="flex items-center gap-3 mb-5">
            <div class="w-12 h-12 rounded-xl bg-gradient-to-br from-orange-400 to-amber-500 flex items-center justify-center shadow-lg">
              <i class="pi pi-exclamation-triangle text-xl text-white"></i>
            </div>
            <div>
              <h3 class="font-bold text-lg text-surface-800 dark:text-surface-100">Potencjalne ryzyka</h3>
              <p class="text-sm text-orange-600 dark:text-orange-400">{{ report!.tldr.cons.length }} uwag</p>
            </div>
          </div>
          
          <ul class="space-y-3">
            <li v-for="con in report!.tldr.cons" :key="con" class="flex items-start gap-3 p-3 bg-white/60 dark:bg-surface-800/40 rounded-xl">
              <span class="flex-shrink-0 w-6 h-6 rounded-full bg-orange-500 flex items-center justify-center mt-0.5">
                <i class="pi pi-exclamation-triangle text-white text-xs"></i>
              </span>
              <span class="text-surface-700 dark:text-surface-200">{{ con }}</span>
            </li>
          </ul>
        </div>
      </div>
      
      <!-- Dane z ogłoszenia - Modern stat cards -->
      <div class="relative bg-gradient-to-br from-white to-surface-50 dark:from-surface-800 dark:to-surface-900 rounded-2xl p-6 shadow-lg border border-surface-100 dark:border-surface-700 overflow-hidden">
        <div class="absolute top-0 left-0 right-0 h-1 bg-gradient-to-r from-blue-400 via-indigo-500 to-violet-500"></div>
        
        <div class="flex items-center gap-3 mb-6">
          <div class="w-12 h-12 rounded-xl bg-gradient-to-br from-blue-400 to-indigo-500 flex items-center justify-center shadow-lg">
            <i class="pi pi-file text-xl text-white"></i>
          </div>
          <h3 class="font-bold text-xl text-surface-800 dark:text-surface-100">Dane z ogłoszenia</h3>
        </div>
        
        <!-- Stats Grid -->
        <div class="grid grid-cols-2 md:grid-cols-5 gap-4 mb-6">
          <div class="bg-surface-50 dark:bg-surface-800 rounded-xl p-4 text-center">
            <span class="text-xs font-medium text-surface-500 uppercase tracking-wide">Cena</span>
            <p class="text-xl md:text-2xl font-bold text-surface-800 dark:text-surface-100 mt-1">{{ formatPrice(report!.listing.price) }}</p>
          </div>
          <div class="bg-surface-50 dark:bg-surface-800 rounded-xl p-4 text-center">
            <span class="text-xs font-medium text-surface-500 uppercase tracking-wide">Cena/m²</span>
            <p class="text-xl md:text-2xl font-bold text-surface-800 dark:text-surface-100 mt-1">{{ formatPricePerSqm(report!.listing.price_per_sqm) }}</p>
          </div>
          <div class="bg-surface-50 dark:bg-surface-800 rounded-xl p-4 text-center">
            <span class="text-xs font-medium text-surface-500 uppercase tracking-wide">Metraż</span>
            <p class="text-xl md:text-2xl font-bold text-surface-800 dark:text-surface-100 mt-1">{{ report!.listing.area_sqm ? `${report!.listing.area_sqm} m²` : '-' }}</p>
          </div>
          <div class="bg-surface-50 dark:bg-surface-800 rounded-xl p-4 text-center">
            <span class="text-xs font-medium text-surface-500 uppercase tracking-wide">Pokoje</span>
            <p class="text-xl md:text-2xl font-bold text-surface-800 dark:text-surface-100 mt-1">{{ report!.listing.rooms || '-' }}</p>
          </div>
          <div v-if="report!.listing.floor" class="bg-surface-50 dark:bg-surface-800 rounded-xl p-4 text-center">
            <span class="text-xs font-medium text-surface-500 uppercase tracking-wide">Piętro</span>
            <p class="text-xl md:text-2xl font-bold text-surface-800 dark:text-surface-100 mt-1">{{ report!.listing.floor }}</p>
          </div>
        </div>
        
        <!-- Opis (collapsible) -->
        <div v-if="report!.listing.description" class="mb-4">
          <Fieldset legend="Opis" :toggleable="true" :collapsed="true" class="!rounded-xl !border-surface-200">
            <p class="whitespace-pre-wrap text-sm text-surface-600 dark:text-surface-300">{{ report!.listing.description }}</p>
          </Fieldset>
        </div>
        
        <!-- Zdjęcia -->
        <div v-if="report!.listing.images?.length">
          <h4 class="font-semibold mb-3 text-surface-700 dark:text-surface-200 flex items-center gap-2">
            <i class="pi pi-images text-primary-500"></i>
            Zdjęcia
          </h4>
          <div class="flex gap-3 overflow-x-auto pb-2">
            <img 
              v-for="(img, idx) in report!.listing.images.slice(0, 6)" 
              :key="idx"
              :src="img"
              class="h-28 w-44 rounded-xl object-cover shadow-md hover:shadow-xl hover:scale-105 transition-all cursor-pointer"
              loading="lazy"
            />
          </div>
        </div>
      </div>
      
      <!-- Okolica -->
      <Card>
        <template #title>
          <div class="flex items-center justify-between">
            <div class="flex items-center gap-2">
              <i class="pi pi-map"></i>
              <span>Okolica</span>
            </div>
            <div v-if="report!.neighborhood.has_location" class="flex items-center gap-2">
              <span class="text-sm text-surface-500">Ocena:</span>
              <Tag 
                :value="`${Math.round(report!.neighborhood.score || 0)}/100 - ${scoreLabel}`"
                :severity="scoreColor"
                class="text-lg"
              />
            </div>
          </div>
        </template>
        <template #content>
          <!-- Brak lokalizacji -->
          <div v-if="!report!.neighborhood.has_location" class="text-center py-8">
            <i class="pi pi-map-marker text-4xl text-surface-400 mb-4"></i>
            <p class="text-surface-500">
              Brak dokładnej lokalizacji - analiza okolicy jest ograniczona.
            </p>
          </div>
          
          <!-- Analiza okolicy -->
          <div v-else>
            <p class="mb-4">{{ report!.neighborhood.summary }}</p>
            
            <!-- Map Type Selector -->
            <div class="flex items-center gap-4 mb-4">
              <span class="text-sm text-surface-500">Typ mapy:</span>
              <SelectButton 
                v-model="selectedMapType" 
                :options="mapTypeOptions" 
                optionLabel="label" 
                optionValue="value"
                :allowEmpty="false"
              />
            </div>
            
            <!-- Google Maps Error -->
            <Message v-if="googleMapsError && selectedMapType === 'google'" severity="warn" :closable="false" class="mb-4">
              {{ googleMapsError }}
            </Message>
            
            <!-- Map Container -->
            <div ref="mapContainer" class="w-full h-96 rounded-lg mb-6 border border-surface-200 z-0 relative"></div>
            
            <!-- Kategorie POI -->
            <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
              <div 
                v-for="(stats, category) in report!.neighborhood.poi_stats" 
                :key="category"
                class="group relative bg-gradient-to-br from-white to-surface-50 dark:from-surface-800 dark:to-surface-900 rounded-2xl p-5 shadow-lg hover:shadow-xl transition-all duration-300 border border-surface-200 dark:border-surface-700 hover:scale-[1.02] hover:-translate-y-1"
              >
                <!-- Accent bar top -->
                <div 
                  class="absolute top-0 left-4 right-4 h-1 rounded-b-full opacity-80"
                  :style="{ background: getCategoryColor(category) }"
                ></div>
                
                <!-- Header -->
                <div class="flex items-start gap-4 mb-3">
                  <!-- Icon with gradient background -->
                  <div 
                    class="flex-shrink-0 w-12 h-12 rounded-xl flex items-center justify-center shadow-md"
                    :style="{ background: `linear-gradient(135deg, ${getCategoryColor(category)}20, ${getCategoryColor(category)}40)` }"
                  >
                    <i 
                      :class="['pi', getCategoryIcon(category), 'text-xl']"
                      :style="{ color: getCategoryColor(category) }"
                    ></i>
                  </div>
                  
                  <!-- Title & Count -->
                  <div class="flex-1 min-w-0">
                    <div class="flex items-center justify-between gap-2 mb-1">
                      <h4 class="font-bold text-lg text-surface-900 dark:text-surface-100 truncate">
                        {{ getCategoryName(category) }}
                      </h4>
                      <!-- Rating Badge -->
                      <Tag 
                        v-if="report!.neighborhood.details[category]"
                        :value="report!.neighborhood.details[category].rating"
                        :severity="getRatingSeverity(report!.neighborhood.details[category].rating)"
                        class="!text-xs !font-semibold !px-2 !py-0.5 flex-shrink-0"
                      />
                    </div>
                    <div class="flex items-center gap-2">
                      <span class="text-xl font-bold" :style="{ color: getCategoryColor(category) }">
                        {{ (stats as POICategoryStats).count }}
                      </span>
                      <span class="text-sm text-surface-500">w okolicy</span>
                    </div>
                  </div>
                </div>
                
                <!-- Map Toggle -->
                <div class="flex items-center justify-between mb-4 p-2.5 bg-surface-100 dark:bg-surface-800 rounded-xl">
                  <label :for="`map-${category}`" class="flex items-center gap-2 cursor-pointer">
                    <i class="pi pi-map text-surface-400 text-sm"></i>
                    <span class="text-sm font-medium text-surface-600 dark:text-surface-300">Na mapie</span>
                  </label>
                  <ToggleSwitch 
                    :inputId="`map-${category}`"
                    v-model="categoryVisibility[category]"
                  />
                </div>
                
                <!-- Nearest Distance -->
                <div v-if="(stats as POICategoryStats).nearest" class="mb-3">
                  <div class="flex items-center gap-2 text-sm text-surface-500 mb-2">
                    <i class="pi pi-directions"></i>
                    <span>Najbliżej</span>
                    <span class="font-bold text-surface-700 dark:text-surface-200">
                      {{ Math.round((stats as POICategoryStats).nearest) }}m
                    </span>
                  </div>
                </div>
                
                <!-- Items List -->
                <div v-if="(stats as POICategoryStats).items?.length" class="space-y-2">
                  <div 
                    v-for="(item, idx) in (stats as POICategoryStats).items.slice(0, 3)" 
                    :key="item.name"
                    class="flex items-center justify-between py-2 px-3 bg-surface-50 dark:bg-surface-800/50 rounded-lg hover:bg-surface-100 dark:hover:bg-surface-700 transition-colors"
                  >
                    <div class="flex items-center gap-2 min-w-0">
                      <span 
                        class="w-2 h-2 rounded-full flex-shrink-0"
                        :style="{ background: getCategoryColor(category) }"
                      ></span>
                      <span class="truncate text-sm text-surface-700 dark:text-surface-300">{{ item.name }}</span>
                    </div>
                    <span class="flex-shrink-0 text-xs font-medium px-2 py-1 bg-surface-200 dark:bg-surface-600 rounded-full text-surface-600 dark:text-surface-200">
                      {{ item.distance_m }}m
                    </span>
                  </div>
                </div>
                
                <!-- Empty state -->
                <div v-else class="text-center py-4 text-surface-400">
                  <i class="pi pi-info-circle mb-2"></i>
                  <p class="text-sm">Brak w pobliżu</p>
                </div>
              </div>
            </div>
          </div>
        </template>
      </Card>
    </div>
    </div>
  </div>
</template>

<style scoped>
@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

.spin-animation {
  animation: spin 1s linear infinite;
}
</style>
