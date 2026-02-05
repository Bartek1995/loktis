<script setup lang="ts">
/**
 * Report View - wyświetla raport z analizy
 * Wersja zmigrowana do czystego Tailwind CSS
 */
import { ref, computed, onMounted, nextTick, watch } from 'vue';
import { useRouter, useRoute } from 'vue-router';
import { analyzerApi, type AnalysisReport, type POICategoryStats, type TrafficAnalysis, type NatureMetrics, type POIItem } from '@/api/analyzerApi';
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
  nature_place: true,
  nature_background: true,
  nature: true,
  leisure: true,
  food: true,
  finance: true,
});

// Watch visibility changes to update map
watch(categoryVisibility, () => {
  updateMapMarkers();
}, { deep: true });

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
  if (score === null || score === undefined) return 'bg-slate-500';
  if (score >= 70) return 'bg-emerald-500';
  if (score >= 50) return 'bg-blue-500';
  if (score >= 30) return 'bg-amber-500';
  return 'bg-red-500';
});

const trafficInfo = computed<TrafficAnalysis | null>(() => {
  return (report.value?.neighborhood?.details?.traffic as TrafficAnalysis) || null;
});

const trafficColor = computed(() => {
  const level = trafficInfo.value?.level;
  if (level === 'Low') return 'bg-emerald-500';
  if (level === 'Moderate') return 'bg-amber-500';
  if (level === 'High') return 'bg-red-500';
  if (level === 'Extreme') return 'bg-red-700'; 
  return 'bg-slate-500';
});

// Nature metrics
const natureMetrics = computed<NatureMetrics | null>(() => {
  return (report.value?.neighborhood?.details?.nature_metrics as NatureMetrics) || null;
});

const greeneryLevelColor = computed(() => {
  const level = natureMetrics.value?.greenery_level;
  if (level === 'wysoka') return { bg: 'bg-emerald-100', text: 'text-emerald-700', border: 'border-emerald-200' };
  if (level === 'średnia') return { bg: 'bg-amber-100', text: 'text-amber-700', border: 'border-amber-200' };
  return { bg: 'bg-slate-100', text: 'text-slate-700', border: 'border-slate-200' };
});

const greeneryLevelEmoji = computed(() => {
  const level = natureMetrics.value?.greenery_level;
  if (level === 'wysoka') return '🌳';
  if (level === 'średnia') return '🌿';
  return '🌵';
});

// Gallery State
const displayGallery = ref(false);
const activeImageIndex = ref(0);

function openGallery(index: number) {
    activeImageIndex.value = index;
    displayGallery.value = true;
}

function closeGallery() {
    displayGallery.value = false;
}

function nextImage() {
    if (report.value?.listing.images) {
        activeImageIndex.value = (activeImageIndex.value + 1) % report.value.listing.images.length;
    }
}

function prevImage() {
    if (report.value?.listing.images) {
        activeImageIndex.value = (activeImageIndex.value - 1 + report.value.listing.images.length) % report.value.listing.images.length;
    }
}

// Collapsible description
const showDescription = ref(false);

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

function getCategoryName(category: string): string {
  const names: Record<string, string> = {
    shops: 'Sklepy',
    transport: 'Transport',
    education: 'Edukacja',
    health: 'Zdrowie',
    nature_place: 'Parki i ogrody',
    nature_background: 'Zieleń w otoczeniu',
    nature: 'Zieleń',
    leisure: 'Sport',
    food: 'Gastronomia',
    finance: 'Finanse',
  };
  return names[category] || category;
}

function getCategoryIcon(category: string): string {
  const icons: Record<string, string> = {
    shops: 'pi-shopping-cart',
    transport: 'pi-car',
    education: 'pi-book',
    health: 'pi-heart',
    nature_place: 'pi-sun',
    nature_background: 'pi-map',
    nature: 'pi-sun',
    leisure: 'pi-stopwatch',
    food: 'pi-apple',
    finance: 'pi-wallet',
  };
  return icons[category] || 'pi-map-marker';
}

function getGreenTypeLabel(greenType: string): string {
  const labels: Record<string, string> = {
    forest: 'Las',
    wood: 'Las',
    meadow: 'Łąka',
    grass: 'Trawniki',
    recreation_ground: 'Teren rekreacyjny',
    park: 'Park',
    garden: 'Ogród',
  };
  return labels[greenType] || greenType;
}

function getWaterTypeLabel(waterType: string): string {
  const labels: Record<string, string> = {
    river: 'Rzeka',
    stream: 'Strumień',
    canal: 'Kanał',
    lake: 'Jezioro',
    pond: 'Staw',
    water: 'Zbiornik',
    beach: 'Plaża',
    reservoir: 'Zbiornik',
  };
  return labels[waterType] || waterType;
}

function getCategoryColor(category: string): string {
  const colors: Record<string, string> = {
    shops: '#F59E0B',
    transport: '#3B82F6',
    education: '#8B5CF6',
    health: '#EF4444',
    nature_place: '#10B981',
    nature_background: '#06B6D4',
    nature: '#10B981',
    leisure: '#F97316',
    food: '#EC4899',
    finance: '#64748B',
  };
  return colors[category] || '#6B7280';
}

function getPoiItemColor(category: string, subcategory: string): string {
  if (category === 'nature_background') {
    const waterTypes = new Set([
      'water', 'beach', 'river', 'stream', 'canal', 'lake', 'pond', 'reservoir'
    ]);
    if (waterTypes.has((subcategory || '').toLowerCase())) {
      return '#F97316';
    }
  }
  return getCategoryColor(category);
}

function findMarkerForItem(category: string, name: string, subcategory: string) {
  const markers = report.value?.neighborhood?.markers || [];
  return (
    markers.find(m => m.category === category && m.name === name && m.subcategory === subcategory) ||
    markers.find(m => m.category === category && m.name === name) ||
    markers.find(m => m.category === category) ||
    null
  );
}

function focusOnPoi(category: string, item: POIItem) {
  const marker = findMarkerForItem(category, item.name, item.subcategory);
  if (!marker) return;

  mapContainer.value?.scrollIntoView({ behavior: 'smooth', block: 'center' });
  categoryVisibility.value[category] = true;
  updateMapMarkers();

  if (selectedMapType.value === 'google' && googleMap.value) {
    googleMap.value.panTo({ lat: marker.lat, lng: marker.lon });
    googleMap.value.setZoom(16);
    const gMarker = googleMarkers.value.find(
      m => m._name === marker.name && m._subcategory === marker.subcategory
    );
    if (gMarker && gMarker._infoWindow) {
      gMarker._infoWindow.open(googleMap.value, gMarker);
    }
  } else if (map.value) {
    map.value.setView([marker.lat, marker.lon], 16, { animate: true });
    const lMarker = leafletPoiMarkers.value.find(
      m => (m as any)._name === marker.name && (m as any)._subcategory === marker.subcategory
    );
    if (lMarker) {
      lMarker.openPopup();
    }
  }
}

function getRatingColor(rating: string): string {
  const map: Record<string, string> = {
    doskonale: 'bg-emerald-500 text-white',
    dobrze: 'bg-blue-500 text-white',
    ok: 'bg-amber-500 text-white',
    daleko: 'bg-red-500 text-white',
    brak: 'bg-slate-400 text-white',
  };
  return map[rating] || 'bg-slate-400 text-white';
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
  leafletPoiMarkers.value.forEach(marker => marker.remove());
  leafletPoiMarkers.value = [];
  
  if (map.value) {
    map.value.remove();
    map.value = null;
  }
  
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
  
  L.marker([lat, lon]).addTo(map.value as any)
    .bindPopup('<b>' + (report.value.listing.title || 'Nieruchomość') + '</b>')
    .openPopup();
    
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
      
      (circle as any)._category = poi.category;
      (circle as any)._name = poi.name;
      (circle as any)._subcategory = poi.subcategory;
      
      if (categoryVisibility.value[poi.category] !== false) {
        circle.addTo(map.value as any);
      }
      
      circle.bindPopup(`
        <b>${poi.name}</b><br>
        <span style="font-size: 12px; color: #666;">${poi.subcategory} (${Math.round(poi.distance || 0)}m)</span>
      `);
      
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
      
      marker._category = poi.category;
      marker._name = poi.name;
      marker._subcategory = poi.subcategory;
      marker._infoWindow = null;
      
      const poiInfoWindow = new window.google.maps.InfoWindow({
        content: `<b>${poi.name}</b><br><span style="font-size: 12px; color: #666;">${poi.subcategory} (${Math.round(poi.distance || 0)}m)</span>`,
      });
      marker._infoWindow = poiInfoWindow;
      
      marker.addListener('click', () => {
        poiInfoWindow.open(googleMap.value, marker);
      });
      
      googleMarkers.value.push(marker);
    });
  }
}

function initMap() {
  if (selectedMapType.value === 'google') {
    initGoogleMap();
  } else {
    initLeafletMap();
  }
}

watch(selectedMapType, () => {
  if (report.value) {
    nextTick(initMap);
  }
});

// Copy public URL to clipboard
function copyPublicUrl() {
  if (report.value?.public_id) {
    const publicUrl = `${window.location.origin}/r/${report.value.public_id}`;
    navigator.clipboard.writeText(publicUrl);
    // TODO: Show toast notification
  }
}

// Load report
onMounted(async () => {
  // Case 1: From fresh analysis (via sessionStorage)
  if (route.query.fromAnalysis === 'true') {
    const storedReport = sessionStorage.getItem('lastReport');
    const storedUrl = sessionStorage.getItem('lastReportUrl');
    if (storedReport) {
      try {
        report.value = JSON.parse(storedReport);
        originalUrl.value = storedUrl || '';
        sessionStorage.removeItem('lastReport');
        sessionStorage.removeItem('lastReportUrl');
        
        // Redirect to public URL if available
        if (report.value?.public_id) {
          router.replace({ name: 'report-public', params: { publicId: report.value.public_id } });
        }
        
        nextTick(initMap);
        return;
      } catch (e) {
        console.error('Błąd parsowania raportu z sessionStorage', e);
      }
    }
  }
  
  // Case 2: Public URL with public_id (hash)
  const publicId = route.params.publicId;
  if (publicId && typeof publicId === 'string') {
    isLoading.value = true;
    try {
      report.value = await analyzerApi.getReportByPublicId(publicId);
      nextTick(initMap);
    } catch (e) {
      error.value = 'Nie udało się pobrać raportu. Sprawdź czy link jest poprawny.';
    } finally {
      isLoading.value = false;
    }
    return;
  }
  
  // Case 3: History detail by numeric ID (legacy)
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
  
  router.replace({ name: 'landing' });
});
</script>

<template>
  <div class="min-h-screen bg-gradient-to-br from-slate-50 via-white to-blue-50 p-4 md:p-6">
    <div class="max-w-5xl mx-auto">
      <!-- Loading -->
      <div v-if="isLoading" class="flex flex-col justify-center items-center min-h-96 gap-4">
        <div class="w-20 h-20 rounded-2xl bg-gradient-to-br from-blue-400 to-blue-600 flex items-center justify-center shadow-xl">
          <i class="pi pi-spin pi-spinner text-3xl text-white"></i>
        </div>
        <p class="text-slate-500 font-medium">Ładowanie raportu...</p>
      </div>
      
      <!-- Error -->
      <div v-else-if="error" class="p-6 bg-red-50 border border-red-200 rounded-xl text-red-700">
        <div class="flex items-center gap-2">
          <i class="pi pi-exclamation-circle text-xl"></i>
          <span class="font-medium">{{ error }}</span>
        </div>
      </div>
      
      <!-- Report -->
      <div v-else-if="hasReport" class="flex flex-col gap-6">
        <!-- Header -->
        <div class="relative overflow-hidden bg-white rounded-2xl p-6 shadow-lg border border-slate-100">
          <div class="absolute top-0 left-0 right-0 h-1 bg-gradient-to-r from-blue-400 via-blue-500 to-blue-600"></div>
          
          <div class="flex flex-wrap justify-between items-start gap-4">
            <div class="flex-1 min-w-0">
              <div class="flex items-center gap-2 mb-2">
                <button @click="goBack" class="p-2 -ml-2 text-slate-400 hover:text-blue-500 transition-colors">
                  <i class="pi pi-arrow-left text-xl"></i>
                </button>
                <h1 class="text-xl md:text-2xl font-bold text-slate-900 leading-tight truncate">
                  {{ report!.listing.title || 'Analiza ogłoszenia' }}
                </h1>
              </div>
              
              <p v-if="report!.listing.location" class="flex items-center gap-2 text-sm text-slate-500 font-medium ml-1">
                <i class="pi pi-map-marker text-blue-500"></i>
                {{ report!.listing.location }}
              </p>
            </div>
            <div class="flex gap-2 flex-shrink-0">
              <button 
                v-if="report!.public_id"
                @click="copyPublicUrl"
                class="px-4 py-2 rounded-xl border-2 border-emerald-200 text-emerald-600 font-medium hover:bg-emerald-50 transition-colors flex items-center gap-2"
                title="Kopiuj link do raportu"
              >
                <i class="pi pi-share-alt"></i>
                <span class="hidden sm:inline">Udostępnij</span>
              </button>
              <button 
                @click="openOriginalUrl"
                class="px-4 py-2 rounded-xl border-2 border-slate-200 text-slate-600 font-medium hover:bg-slate-50 transition-colors flex items-center gap-2"
              >
                <i class="pi pi-external-link"></i>
                <span class="hidden sm:inline">Zobacz ogłoszenie</span>
              </button>
              <button 
                @click="analyzeAnother"
                class="px-4 py-2 rounded-xl bg-gradient-to-r from-blue-500 to-blue-600 text-white font-medium hover:shadow-lg transition-all flex items-center gap-2"
              >
                <i class="pi pi-plus"></i>
                <span class="hidden sm:inline">Analizuj kolejne</span>
              </button>
            </div>
          </div>
        </div>
        
        <!-- Errors/Warnings -->
        <div v-for="err in report!.errors" :key="err" class="p-4 bg-red-50 border border-red-200 rounded-xl text-red-700 flex items-center gap-2">
          <i class="pi pi-exclamation-circle"></i>
          <span>{{ err }}</span>
        </div>
        <div v-for="warn in report!.warnings" :key="warn" class="p-4 bg-amber-50 border border-amber-200 rounded-xl text-amber-700 flex items-center gap-2">
          <i class="pi pi-exclamation-triangle"></i>
          <span>{{ warn }}</span>
        </div>
        
        <!-- TL;DR Section -->
        <div class="grid grid-cols-1 md:grid-cols-2 gap-5">
          <!-- Plusy -->
          <div class="relative bg-gradient-to-br from-emerald-50 to-green-50 rounded-2xl p-6 shadow-lg border border-emerald-100 overflow-hidden">
            <div class="absolute top-0 left-0 right-0 h-1 bg-gradient-to-r from-emerald-400 to-green-500"></div>
            
            <div class="flex items-center gap-3 mb-5">
              <div class="w-12 h-12 rounded-xl bg-gradient-to-br from-emerald-400 to-green-500 flex items-center justify-center shadow-lg">
                <i class="pi pi-check-circle text-xl text-white"></i>
              </div>
              <div>
                <h3 class="font-bold text-lg text-slate-800">Plusy</h3>
                <p class="text-sm text-slate-600">{{ report!.tldr.pros.length }} zalet</p>
              </div>
            </div>
            
            <ul class="space-y-3">
              <li v-for="pro in report!.tldr.pros" :key="pro" class="flex items-start gap-3 p-3 bg-white/60 rounded-xl">
                <span class="flex-shrink-0 w-6 h-6 rounded-full bg-emerald-500 flex items-center justify-center mt-0.5">
                  <i class="pi pi-check text-white text-xs"></i>
                </span>
                <span class="text-slate-700">{{ pro }}</span>
              </li>
            </ul>
          </div>
          
          <!-- Ryzyka -->
          <div class="relative bg-gradient-to-br from-orange-50 to-amber-50 rounded-2xl p-6 shadow-lg border border-orange-100 overflow-hidden">
            <div class="absolute top-0 left-0 right-0 h-1 bg-gradient-to-r from-orange-400 to-amber-500"></div>
            
            <div class="flex items-center gap-3 mb-5">
              <div class="w-12 h-12 rounded-xl bg-gradient-to-br from-orange-400 to-amber-500 flex items-center justify-center shadow-lg">
                <i class="pi pi-exclamation-triangle text-xl text-white"></i>
              </div>
              <div>
                <h3 class="font-bold text-lg text-slate-800">Potencjalne ryzyka</h3>
                <p class="text-sm text-slate-600">{{ report!.tldr.cons.length }} uwag</p>
              </div>
            </div>
            
            <ul class="space-y-3">
              <li v-for="con in report!.tldr.cons" :key="con" class="flex items-start gap-3 p-3 bg-white/60 rounded-xl">
                <span class="flex-shrink-0 w-6 h-6 rounded-full bg-orange-500 flex items-center justify-center mt-0.5">
                  <i class="pi pi-exclamation-triangle text-white text-xs"></i>
                </span>
                <span class="text-slate-700">{{ con }}</span>
              </li>
            </ul>
          </div>
        </div>
        
        <!-- Verdict Section (Persona System) -->
        <div v-if="report!.verdict" class="relative bg-white rounded-2xl p-6 shadow-lg border border-slate-100 overflow-hidden">
          <div 
            class="absolute top-0 left-0 right-0 h-1"
            :class="{
              'bg-gradient-to-r from-emerald-400 to-green-500': report!.verdict.level === 'recommended',
              'bg-gradient-to-r from-amber-400 to-orange-500': report!.verdict.level === 'conditional',
              'bg-gradient-to-r from-red-400 to-rose-500': report!.verdict.level === 'not_recommended'
            }"
          ></div>
          
          <div class="flex flex-wrap items-start gap-6">
            <!-- Verdict Badge -->
            <div class="flex-shrink-0">
              <div 
                class="w-24 h-24 rounded-2xl flex flex-col items-center justify-center shadow-xl text-white"
                :class="{
                  'bg-gradient-to-br from-emerald-400 to-green-500': report!.verdict.level === 'recommended',
                  'bg-gradient-to-br from-amber-400 to-orange-500': report!.verdict.level === 'conditional',
                  'bg-gradient-to-br from-red-400 to-rose-500': report!.verdict.level === 'not_recommended'
                }"
              >
                <span class="text-4xl">{{ report!.verdict.emoji }}</span>
                <span class="text-sm font-bold mt-1">{{ Math.round(report!.verdict.score) }}/100</span>
              </div>
            </div>
            
            <!-- Verdict Content -->
            <div class="flex-1 min-w-0">
              <div class="flex items-center gap-3 mb-3">
                <h2 class="text-2xl font-bold text-slate-900">{{ report!.verdict.label }}</h2>
                <span 
                  class="px-3 py-1 rounded-full text-xs font-semibold"
                  :class="{
                    'bg-emerald-100 text-emerald-700': report!.verdict.confidence >= 80,
                    'bg-amber-100 text-amber-700': report!.verdict.confidence >= 60 && report!.verdict.confidence < 80,
                    'bg-slate-100 text-slate-700': report!.verdict.confidence < 60
                  }"
                >
                  {{ report!.verdict.confidence }}% pewności
                </span>
              </div>
              
              <p class="text-lg text-slate-700 mb-4">{{ report!.verdict.explanation }}</p>
              
              <!-- Key Factors -->
              <div v-if="report!.verdict.key_factors?.length" class="flex flex-wrap gap-2">
                <span 
                  v-for="factor in report!.verdict.key_factors" 
                  :key="factor"
                  class="px-3 py-1.5 bg-slate-100 rounded-lg text-sm text-slate-700 font-medium"
                >
                  {{ factor }}
                </span>
              </div>
            </div>
            
            <!-- Profile Badge (nowy system) -->
            <div v-if="report!.profile || report!.persona" class="flex-shrink-0">
              <div class="bg-slate-50 rounded-xl p-4 border border-slate-200 text-center min-w-[140px]">
                <span class="text-3xl">{{ report!.profile?.emoji || report!.persona?.emoji }}</span>
                <p class="font-semibold text-sm text-slate-800 mt-2">{{ report!.profile?.name || report!.persona?.name }}</p>
                <p class="text-xs text-slate-500 mt-0.5">Twój profil</p>
              </div>
            </div>
          </div>
          
          <!-- Scoring Details (collapsed by default) -->
          <details v-if="report!.scoring" class="mt-6">
            <summary class="cursor-pointer text-sm font-medium text-slate-500 hover:text-slate-700 transition-colors">
              Szczegóły scoringu
            </summary>
            <div class="mt-4 grid grid-cols-2 md:grid-cols-4 gap-3">
              <div class="bg-slate-50 rounded-lg p-3 text-center">
                <span class="text-xs text-slate-500">Bazowy score</span>
                <p class="font-bold text-lg text-slate-800">{{ Math.round(report!.scoring.base_score) }}</p>
              </div>
              <div class="bg-slate-50 rounded-lg p-3 text-center">
                <span class="text-xs text-slate-500">Kara hałasu</span>
                <p class="font-bold text-lg text-slate-800">
                  <template v-if="report!.scoring.noise_penalty !== undefined">
                    -{{ report!.scoring.noise_penalty.toFixed(1) }}
                  </template>
                  <template v-else>-</template>
                </p>
              </div>
              <div class="bg-slate-50 rounded-lg p-3 text-center">
                <span class="text-xs text-slate-500">Mocne strony</span>
                <p class="font-bold text-lg text-emerald-600">{{ report!.scoring.strengths?.length || 0 }}</p>
              </div>
              <div class="bg-slate-50 rounded-lg p-3 text-center">
                <span class="text-xs text-slate-500">Słabe strony</span>
                <p class="font-bold text-lg text-red-500">{{ report!.scoring.weaknesses?.length || 0 }}</p>
              </div>
            </div>
            
            <!-- Strengths & Weaknesses -->
            <div v-if="report!.scoring.strengths?.length || report!.scoring.weaknesses?.length" class="mt-4 grid grid-cols-1 md:grid-cols-2 gap-4">
              <div v-if="report!.scoring.strengths?.length" class="bg-emerald-50 rounded-lg p-4">
                <h4 class="font-semibold text-sm text-emerald-700 mb-2">Mocne strony</h4>
                <ul class="space-y-1">
                  <li v-for="strength in report!.scoring.strengths" :key="strength" class="text-sm text-emerald-600 flex items-center gap-2">
                    <i class="pi pi-check-circle text-xs"></i>
                    {{ strength }}
                  </li>
                </ul>
              </div>
              <div v-if="report!.scoring.weaknesses?.length" class="bg-red-50 rounded-lg p-4">
                <h4 class="font-semibold text-sm text-red-700 mb-2">Słabe strony</h4>
                <ul class="space-y-1">
                  <li v-for="weakness in report!.scoring.weaknesses" :key="weakness" class="text-sm text-red-600 flex items-center gap-2">
                    <i class="pi pi-times-circle text-xs"></i>
                    {{ weakness }}
                  </li>
                </ul>
              </div>
            </div>
            
            <!-- Dealbreaker Warning -->
            <div v-if="report!.scoring.has_dealbreaker" class="mt-4 p-4 bg-red-100 border border-red-200 rounded-lg">
              <div class="flex items-center gap-2 text-red-700">
                <i class="pi pi-exclamation-triangle text-lg"></i>
                <span class="font-semibold">Uwaga: Wykryto krytyczny problem!</span>
              </div>
              <p v-if="report!.scoring.dealbreaker_category" class="text-sm text-red-600 mt-1">
                Kategoria "{{ getCategoryName(report!.scoring.dealbreaker_category) }}" ma zbyt niski wynik dla wybranego profilu.
              </p>
            </div>
          </details>
        </div>
        
        <!-- Dane z ogłoszenia -->
        <div class="relative bg-white rounded-2xl p-6 shadow-lg border border-slate-100 overflow-hidden">
          <div class="absolute top-0 left-0 right-0 h-1 bg-gradient-to-r from-blue-400 via-indigo-500 to-violet-500"></div>
          
          <div class="flex items-center gap-3 mb-6">
            <div class="w-12 h-12 rounded-xl bg-gradient-to-br from-blue-400 to-indigo-500 flex items-center justify-center shadow-lg">
              <i class="pi pi-file text-xl text-white"></i>
            </div>
            <h3 class="font-bold text-xl text-slate-800">Dane z ogłoszenia</h3>
          </div>
          
          <!-- Stats Grid -->
          <div class="grid grid-cols-2 md:grid-cols-5 gap-4 mb-6">
            <div class="bg-slate-50 rounded-xl p-4 text-center">
              <span class="text-xs font-medium text-slate-500 uppercase tracking-wide">Cena</span>
              <p class="text-xl md:text-2xl font-bold text-slate-800 mt-1">{{ formatPrice(report!.listing.price) }}</p>
            </div>
            <div class="bg-slate-50 rounded-xl p-4 text-center">
              <span class="text-xs font-medium text-slate-500 uppercase tracking-wide">Cena/m²</span>
              <p class="text-xl md:text-2xl font-bold text-slate-800 mt-1">{{ formatPricePerSqm(report!.listing.price_per_sqm) }}</p>
            </div>
            <div class="bg-slate-50 rounded-xl p-4 text-center">
              <span class="text-xs font-medium text-slate-500 uppercase tracking-wide">Metraż</span>
              <p class="text-xl md:text-2xl font-bold text-slate-800 mt-1">{{ report!.listing.area_sqm ? `${report!.listing.area_sqm} m²` : '-' }}</p>
            </div>
            <div class="bg-slate-50 rounded-xl p-4 text-center">
              <span class="text-xs font-medium text-slate-500 uppercase tracking-wide">Pokoje</span>
              <p class="text-xl md:text-2xl font-bold text-slate-800 mt-1">{{ report!.listing.rooms || '-' }}</p>
            </div>
            <div v-if="report!.listing.floor" class="bg-slate-50 rounded-xl p-4 text-center">
              <span class="text-xs font-medium text-slate-500 uppercase tracking-wide">Piętro</span>
              <p class="text-xl md:text-2xl font-bold text-slate-800 mt-1">{{ report!.listing.floor }}</p>
            </div>
          </div>
          
          <!-- Opis (collapsible) -->
          <div v-if="report!.listing.description" class="mb-4">
            <button 
              @click="showDescription = !showDescription"
              class="w-full px-4 py-3 bg-slate-50 rounded-xl flex items-center justify-between text-left hover:bg-slate-100 transition-colors"
            >
              <span class="font-medium text-slate-700">Opis ogłoszenia</span>
              <i :class="showDescription ? 'pi pi-chevron-up' : 'pi pi-chevron-down'" class="text-slate-400"></i>
            </button>
            <Transition name="accordion">
              <div v-show="showDescription" class="mt-2 p-4 bg-slate-50 rounded-xl">
                <p class="whitespace-pre-wrap text-sm text-slate-600">{{ report!.listing.description }}</p>
              </div>
            </Transition>
          </div>
          
          <!-- Zdjęcia -->
          <div v-if="report!.listing.images?.length">
            <h4 class="font-semibold mb-3 text-slate-700 flex items-center gap-2">
              <i class="pi pi-images text-blue-500"></i>
              Zdjęcia ({{ report!.listing.images.length }})
            </h4>
            
            <div class="flex gap-3 overflow-x-auto pb-4">
              <div 
                v-for="(img, idx) in report!.listing.images" 
                :key="idx"
                class="relative flex-shrink-0 cursor-pointer group"
                @click="openGallery(idx)"
              >
                <img 
                  :src="img"
                  class="h-32 w-48 rounded-xl object-cover shadow-md group-hover:shadow-xl group-hover:scale-105 transition-all duration-300 border border-slate-100"
                  loading="lazy"
                />
                <div class="absolute inset-0 bg-black/0 group-hover:bg-black/10 rounded-xl transition-colors duration-300 flex items-center justify-center opacity-0 group-hover:opacity-100">
                  <i class="pi pi-search-plus text-white text-2xl drop-shadow-md"></i>
                </div>
              </div>
            </div>

            <!-- Gallery Modal -->
            <Teleport to="body">
              <Transition name="fade">
                <div v-if="displayGallery" class="fixed inset-0 z-50 bg-black/90 flex items-center justify-center" @click.self="closeGallery">
                  <button @click="closeGallery" class="absolute top-4 right-4 p-2 text-white hover:text-slate-300 transition-colors">
                    <i class="pi pi-times text-2xl"></i>
                  </button>
                  <button @click="prevImage" class="absolute left-4 p-3 text-white hover:text-slate-300 transition-colors">
                    <i class="pi pi-chevron-left text-3xl"></i>
                  </button>
                  <img :src="report!.listing.images[activeImageIndex]" class="max-h-[85vh] max-w-[90vw] object-contain" />
                  <button @click="nextImage" class="absolute right-4 p-3 text-white hover:text-slate-300 transition-colors">
                    <i class="pi pi-chevron-right text-3xl"></i>
                  </button>
                  <div class="absolute bottom-4 text-white font-medium">
                    {{ activeImageIndex + 1 }} / {{ report!.listing.images.length }}
                  </div>
                </div>
              </Transition>
            </Teleport>
          </div>
        </div>
        
        <!-- Okolica -->
        <div class="relative bg-white rounded-2xl p-6 shadow-lg border border-slate-100 overflow-hidden">
          <div class="absolute top-0 left-0 right-0 h-1 bg-gradient-to-r from-blue-400 via-blue-500 to-blue-600"></div>

          <div class="flex flex-wrap items-center justify-between gap-4 mb-8">
            <div class="flex items-center gap-3">
              <div class="w-12 h-12 rounded-xl bg-gradient-to-br from-blue-400 to-blue-600 flex items-center justify-center shadow-lg">
                <i class="pi pi-map text-xl text-white"></i>
              </div>
              <div>
                <h2 class="text-xl font-bold text-slate-800">Okolica</h2>
                <p class="text-sm text-slate-500">Analiza lokalizacji i punktów POI</p>
              </div>
            </div>
            
            <div class="flex flex-wrap gap-3">
              <div v-if="report!.neighborhood.has_location" class="flex items-center gap-2 bg-slate-50 px-4 py-2 rounded-xl border border-slate-200">
                <span class="text-sm font-medium text-slate-600">Ocena:</span>
                <span :class="[scoreColor, 'px-3 py-1 rounded-lg text-white text-sm font-bold']">
                  {{ Math.round(report!.neighborhood.score || 0) }}/100
                </span>
              </div>

              <div v-if="trafficInfo" class="flex items-center gap-2 bg-slate-50 px-4 py-2 rounded-xl border border-slate-200" :title="trafficInfo.description">
                <span class="text-sm font-medium text-slate-600">Ruch:</span>
                <span :class="[trafficColor, 'px-3 py-1 rounded-lg text-white text-sm font-bold']">
                  {{ trafficInfo.label }}
                </span>
              </div>
            </div>
          </div>

          <div>
            <!-- Brak lokalizacji -->
            <div v-if="!report!.neighborhood.has_location" class="text-center py-12">
              <div class="w-20 h-20 mx-auto bg-slate-100 rounded-full flex items-center justify-center mb-4">
                <i class="pi pi-map-marker text-3xl text-slate-400"></i>
              </div>
              <h3 class="text-lg font-medium text-slate-900 mb-2">Brak dokładnej lokalizacji</h3>
              <p class="text-slate-500 max-w-md mx-auto">
                Nie udało się ustalić dokładnego adresu nieruchomości, dlatego analiza okolicy jest ograniczona.
              </p>
            </div>
            
            <!-- Analiza okolicy -->
            <div v-else>
              <div class="bg-slate-50 rounded-2xl p-6 mb-8 border border-slate-100">
                <p class="text-lg leading-relaxed text-slate-700">
                  {{ report!.neighborhood.summary }}
                </p>
              </div>
              
              <!-- Nature Metrics Section -->
              <div v-if="natureMetrics" class="mb-8">
                <h3 class="text-lg font-bold text-slate-900 mb-4 flex items-center gap-2">
                  <span class="text-2xl">🌿</span>
                  Zieleń w okolicy
                </h3>
                <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
                  <!-- Greenery Level Badge -->
                  <div 
                    class="rounded-2xl p-5 border-2 transition-all"
                    :class="[greeneryLevelColor.bg, greeneryLevelColor.border]"
                  >
                    <div class="flex items-center gap-3 mb-2">
                      <span class="text-3xl">{{ greeneryLevelEmoji }}</span>
                      <div>
                        <div class="text-xs font-medium text-slate-500 uppercase tracking-wide">Poziom zieleni</div>
                        <div class="text-xl font-bold capitalize" :class="greeneryLevelColor.text">
                          {{ natureMetrics.greenery_level }}
                        </div>
                      </div>
                    </div>
                    <div class="text-sm text-slate-600">
                      {{ natureMetrics.total_green_elements }} elementów w zasięgu
                    </div>
                  </div>
                  
                  <!-- Park Distance -->
                  <div class="bg-white rounded-2xl p-5 border border-slate-200 shadow-sm">
                    <div class="flex items-center gap-3 mb-2">
                      <span class="text-3xl">🏞️</span>
                      <div>
                        <div class="text-xs font-medium text-slate-500 uppercase tracking-wide">Najbliższy park</div>
                        <div class="text-xl font-bold text-slate-900">
                          <template v-if="natureMetrics.nearest_distances?.park">
                            {{ Math.round(natureMetrics.nearest_distances.park) }}m
                          </template>
                          <template v-else>
                            <span class="text-slate-400">Brak w zasięgu</span>
                          </template>
                        </div>
                      </div>
                    </div>
                    <div class="text-sm text-slate-600">
                      {{ natureMetrics.nearest_park_label }}
                    </div>
                  </div>
                  
                  <!-- Water Presence -->
                  <div class="bg-white rounded-2xl p-5 border border-slate-200 shadow-sm">
                    <div class="flex items-center gap-3 mb-2">
                      <span class="text-3xl">{{ natureMetrics.water_present ? '💧' : '🏜️' }}</span>
                      <div>
                        <div class="text-xs font-medium text-slate-500 uppercase tracking-wide">Woda</div>
                        <div class="text-xl font-bold" :class="natureMetrics.water_present ? 'text-blue-600' : 'text-slate-400'">
                          {{ natureMetrics.water_present ? 'Obecna' : 'Brak' }}
                        </div>
                      </div>
                    </div>
                    <div v-if="natureMetrics.water_present && natureMetrics.water_label" class="text-sm text-slate-600 mb-2">
                      {{ natureMetrics.water_label }}
                    </div>
                    <div v-else-if="!natureMetrics.water_present" class="text-sm text-slate-400">
                      Brak zbiorników wodnych w zasięgu
                    </div>
                    <!-- Water types badges -->
                    <div v-if="natureMetrics.water_types_present?.length" class="flex flex-wrap gap-1.5 mt-2">
                      <span 
                        v-for="waterType in natureMetrics.water_types_present" 
                        :key="waterType"
                        class="px-2 py-0.5 bg-blue-50 border border-blue-200 rounded-full text-xs font-medium text-blue-700"
                      >
                        {{ getWaterTypeLabel(waterType) }}
                      </span>
                    </div>
                  </div>
                </div>
                
                <!-- Green Types Present -->
                <div v-if="natureMetrics.green_types_present?.length" class="mt-4">
                  <div class="text-sm font-medium text-slate-600 mb-2">Typy zieleni w okolicy:</div>
                  <div class="flex flex-wrap gap-2">
                    <span 
                      v-for="greenType in natureMetrics.green_types_present" 
                      :key="greenType"
                      class="px-3 py-1.5 bg-emerald-50 border border-emerald-200 rounded-full text-sm font-medium text-emerald-700"
                    >
                      {{ getGreenTypeLabel(greenType) }}
                    </span>
                  </div>
                </div>
              </div>
              
              <!-- Map Type Selector -->
              <div class="flex items-center justify-between mb-6">
                <h3 class="text-lg font-bold text-slate-900">Mapa okolicy</h3>
                <div class="flex items-center gap-2">
                  <span class="text-sm font-medium text-slate-500">Widok:</span>
                  <div class="flex gap-1 bg-slate-100 p-1 rounded-lg">
                    <button
                      v-for="option in mapTypeOptions"
                      :key="option.value"
                      @click="selectedMapType = option.value as MapType"
                      :class="[
                        'px-3 py-1.5 rounded-md text-sm font-medium transition-colors',
                        selectedMapType === option.value 
                          ? 'bg-white text-slate-800 shadow-sm' 
                          : 'text-slate-600 hover:text-slate-800'
                      ]"
                    >
                      {{ option.label }}
                    </button>
                  </div>
                </div>
              </div>
              
              <!-- Google Maps Error -->
              <div v-if="googleMapsError && selectedMapType === 'google'" class="p-4 bg-amber-50 border border-amber-200 rounded-xl text-amber-700 mb-4 flex items-center gap-2">
                <i class="pi pi-exclamation-triangle"></i>
                <span>{{ googleMapsError }}</span>
              </div>
              
              <!-- Map Container -->
              <div ref="mapContainer" class="w-full h-96 rounded-xl mb-6 border border-slate-200 z-0 relative"></div>
              
              <!-- Kategorie POI -->
              <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
                <div 
                  v-for="(stats, category) in report!.neighborhood.poi_stats" 
                  :key="category"
                  class="group relative bg-white rounded-2xl p-5 shadow-lg hover:shadow-xl transition-all duration-300 border border-slate-200 hover:scale-[1.02] hover:-translate-y-1"
                >
                  <!-- Accent bar top -->
                  <div 
                    class="absolute top-0 left-4 right-4 h-1 rounded-b-full opacity-80"
                    :style="{ background: getCategoryColor(category) }"
                  ></div>
                  
                  <!-- Header -->
                  <div class="flex items-start gap-4 mb-3">
                    <div 
                      class="flex-shrink-0 w-12 h-12 rounded-xl flex items-center justify-center shadow-md"
                      :style="{ background: `linear-gradient(135deg, ${getCategoryColor(category)}20, ${getCategoryColor(category)}40)` }"
                    >
                      <i 
                        :class="['pi', getCategoryIcon(category), 'text-xl']"
                        :style="{ color: getCategoryColor(category) }"
                      ></i>
                    </div>
                    
                    <div class="flex-1 min-w-0">
                      <div class="flex items-center justify-between gap-2 mb-1">
                        <h4 class="font-bold text-lg text-slate-900 truncate">
                          {{ getCategoryName(category) }}
                        </h4>
                        <span 
                          v-if="report!.neighborhood.details[category]"
                          :class="[getRatingColor(report!.neighborhood.details[category].rating), 'text-xs font-semibold px-2 py-0.5 rounded-md']"
                        >
                          {{ report!.neighborhood.details[category].rating }}
                        </span>
                      </div>
                      <div class="flex items-center gap-2">
                        <span class="text-xl font-bold" :style="{ color: getCategoryColor(category) }">
                          {{ (stats as POICategoryStats).count }}
                        </span>
                        <span class="text-sm text-slate-500">w okolicy</span>
                      </div>
                    </div>
                  </div>
                  
                  <!-- Map Toggle -->
                  <div class="flex items-center justify-between mb-4 p-2.5 bg-slate-100 rounded-xl">
                    <label :for="`map-${category}`" class="flex items-center gap-2 cursor-pointer">
                      <i class="pi pi-map text-slate-400 text-sm"></i>
                      <span class="text-sm font-medium text-slate-600">Na mapie</span>
                    </label>
                    <button 
                      :id="`map-${category}`"
                      @click="toggleCategoryVisibility(category)"
                      :class="[
                        'w-12 h-6 rounded-full transition-colors relative',
                        categoryVisibility[category] ? 'bg-blue-500' : 'bg-slate-300'
                      ]"
                    >
                      <span 
                        :class="[
                          'absolute top-1 w-4 h-4 bg-white rounded-full transition-transform shadow-sm',
                          categoryVisibility[category] ? 'left-7' : 'left-1'
                        ]"
                      ></span>
                    </button>
                  </div>
                  
                  <!-- Nearest Distance -->
                  <div v-if="(stats as POICategoryStats).nearest" class="mb-3">
                    <div class="flex items-center gap-2 text-sm text-slate-500 mb-2">
                      <i class="pi pi-directions"></i>
                      <span>Najbliżej</span>
                      <span class="font-bold text-slate-700">
                        {{ Math.round((stats as POICategoryStats).nearest) }}m
                      </span>
                    </div>
                  </div>
                  
                  <!-- Items List -->
                  <div v-if="(stats as POICategoryStats).items?.length" class="space-y-2">
                    <div 
                      v-for="item in (stats as POICategoryStats).items.slice(0, 3)" 
                      :key="item.name"
                      class="flex items-center justify-between py-2 px-3 bg-slate-50 rounded-lg hover:bg-slate-100 transition-colors"
                    >
                      <div class="flex items-center gap-2 min-w-0">
                        <span 
                          class="w-2 h-2 rounded-full flex-shrink-0"
                          :style="{ background: getPoiItemColor(category, item.subcategory) }"
                        ></span>
                        <span class="truncate text-sm text-slate-700">{{ item.name }}</span>
                      </div>
                      <div class="flex items-center gap-2">
                        <button
                          type="button"
                          class="w-7 h-7 rounded-full bg-white border border-slate-200 text-slate-500 hover:text-blue-600 hover:border-blue-300 transition-colors flex items-center justify-center"
                          title="Pokaż na mapie"
                          @click="focusOnPoi(category, item)"
                        >
                          <i class="pi pi-map-marker text-xs"></i>
                        </button>
                        <span class="flex-shrink-0 text-xs font-medium px-2 py-1 bg-slate-200 rounded-full text-slate-600">
                          {{ item.distance_m }}m
                        </span>
                      </div>
                    </div>
                  </div>
                  
                  <!-- Empty state -->
                  <div v-else class="text-center py-4 text-slate-400">
                    <i class="pi pi-info-circle mb-2"></i>
                    <p class="text-sm">Brak w pobliżu</p>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* Accordion animation */
.accordion-enter-active,
.accordion-leave-active {
  transition: all 0.3s ease;
  max-height: 500px;
}

.accordion-enter-from,
.accordion-leave-to {
  opacity: 0;
  max-height: 0;
}

/* Fade animation */
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.3s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
