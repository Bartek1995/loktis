<script setup lang="ts">
/// <reference types="google.maps" />
/**
 * LocationPicker - Komponent do wyboru lokalizacji
 * Używa Google Maps AutocompleteService (Data-only) + Custom UI
 * Fallback do Nominatim (OSM)
 */
import { ref, onMounted, onUnmounted, computed, watch, markRaw, nextTick } from 'vue';

const props = defineProps<{
  initialLat?: number;
  initialLng?: number;
  initialAddress?: string;
  locationHint?: string;
  showCancel?: boolean;
}>();

const emit = defineEmits<{
  (e: 'location-selected', data: { lat: number; lng: number; address: string }): void;
  (e: 'cancel'): void;
}>();

// Interface for suggestions
interface LocationSuggestion {
  id: string;
  title: string;
  subtitle: string;
  source: 'google' | 'nominatim';
  original?: any;
}

// State
const searchQuery = ref(props.initialAddress || props.locationHint || '');
const selectedLat = ref<number | null>(props.initialLat || null);
const selectedLng = ref<number | null>(props.initialLng || null);
const selectedAddress = ref(props.initialAddress || '');

const isMapReady = ref(false);
const mapLoadError = ref(false);

const isSearching = ref(false);
const suggestions = ref<LocationSuggestion[]>([]);
const showSuggestions = ref(false);
const searchTimeout = ref<number | null>(null);

const mapContainer = ref<HTMLElement | null>(null);
const searchInput = ref<HTMLInputElement | null>(null);

let map: google.maps.Map | null = null;
let marker: google.maps.Marker | null = null;
let autocompleteService: google.maps.places.AutocompleteService | null = null;
let geocoder: google.maps.Geocoder | null = null;

// Google Maps Bootstrap Loader
(g=>{var h,a,k,p="The Google Maps JavaScript API",c="google",l="importLibrary",q="__ib__",m=document,b=window;b=b[c]||(b[c]={});var d=b.maps||(b.maps={}),r=new Set,e=new URLSearchParams,u=()=>h||(h=new Promise(async(f,n)=>{await (a=m.createElement("script"));e.set("libraries",[...r]+"");for(k in g)e.set(k.replace(/[A-Z]/g,t=>"_"+t[0].toLowerCase()),g[k]);e.set("callback",c+".maps."+q);a.src=`https://maps.${c}apis.com/maps/api/js?`+e;d[q]=f;a.onerror=()=>h=n(Error(p+" could not load."));a.nonce=m.querySelector("script[nonce]")?.nonce||"";m.head.append(a)}));d[l]?console.warn(p+" only loads once. Ignoring:",g):d[l]=(f,...n)=>r.add(f)&&u().then(()=>d[l](f,...n))})({
  key: import.meta.env.VITE_GOOGLE_MAPS_API_KEY,
  v: "weekly",
  language: "pl",
  region: "PL"
});

// Initialize map & services
onMounted(async () => {
  // Global auth failure handler
  (window as any).gm_authFailure = () => {
    console.error('Google Maps Auth Failure');
    mapLoadError.value = true;
    isMapReady.value = false;
  };

  try {
    // Import required libraries dynamically
    const { Map } = await google.maps.importLibrary("maps") as google.maps.MapsLibrary;
    const { AutocompleteService } = await google.maps.importLibrary("places") as google.maps.PlacesLibrary;
    const { Marker } = await google.maps.importLibrary("marker") as google.maps.MarkerLibrary;
    // Geocoder is in the main library usually, or needs specific import? 
    // Docs say Geocoder class is in 'geocoding' library in some contexts? 
    // Checking docs: Geocoder is in google.maps.Geocoder (core). 
    // But let's try importing it via namespaces if available, or just rely on global if loaded.
    // Actually, Geocoding service is part of the core, but in dynamic import it might be better to verify.
    // Let's rely on global google.maps.Geocoder after 'maps' import, or await importLibrary("geocoding") if valid (it is not a standard library name in old docs, but 'geocoding' is listed in some new docs? No, usually core).
    // Safer: check global after awaiting maps.
    
    // Init services
    if (AutocompleteService) {
      autocompleteService = new AutocompleteService();
    } else {
      console.warn('Google Maps Places library not available');
    }
    
    geocoder = new google.maps.Geocoder();
    
    await nextTick(); // Wait for DOM

    // Init Map
    if (mapContainer.value) {
        const initialCoords = {
            lat: props.initialLat || 52.2297,
            lng: props.initialLng || 21.0122
        };

        map = new Map(mapContainer.value, {
            center: initialCoords,
            zoom: 13,
            styles: [{ featureType: 'poi', elementType: 'labels', stylers: [{ visibility: 'off' }] }],
            mapTypeControl: false,
            streetViewControl: false,
            fullscreenControl: false,
        });

        map.addListener('click', (e: google.maps.MapMouseEvent) => {
            if (e.latLng) {
                setLocation(e.latLng.lat(), e.latLng.lng());
                reverseGeocode(e.latLng.lat(), e.latLng.lng());
            }
        });

        if (props.initialLat && props.initialLng) {
            setLocation(props.initialLat, props.initialLng);
        }
        
        isMapReady.value = true;
    }
  } catch (error) {
    console.error('Error initializing Google Maps:', error);
    mapLoadError.value = true;
  }
});

// Helper: Ensure we use the imported Marker classes or global ones correctly
// Note: We need to update setLocation to use the imported Marker class if we store it, 
// OR just use google.maps.Marker (which should be populated by importLibrary("marker") legacy behavior?)
// Actually "marker" library in importLibrary returns { AdvancedMarkerElement, PinElement, Marker }.
// We should assign Marker to a ref or let variable.
// I will update the top level variables.


// Unified Search Function
async function handleInput() {
  if (searchTimeout.value) clearTimeout(searchTimeout.value);
  
  if (!searchQuery.value || searchQuery.value.length < 3) {
    suggestions.value = [];
    showSuggestions.value = false;
    return;
  }

  searchTimeout.value = window.setTimeout(async () => {
    if (!alive.value) return;
    isSearching.value = true;
    suggestions.value = [];
    
    try {
      // 1. Try Google Autocomplete first (if available)
      if (autocompleteService && !mapLoadError.value) {
        try {
          const googleResults = await getGooglePredictions(searchQuery.value);
          if (!alive.value) return;
          suggestions.value = [...suggestions.value, ...googleResults];
        } catch (e) {
          console.warn("Google Autocomplete failed, falling back", e);
        }
      }

      // 2. Add Nominatim results (fallback or supplement)
      if (suggestions.value.length < 3) {
         const nominatimResults = await getNominatimPredictions(searchQuery.value);
         if (!alive.value) return;
         suggestions.value = [...suggestions.value, ...nominatimResults];
      }
      
      if (!alive.value) return;
      showSuggestions.value = suggestions.value.length > 0;
    } catch (e) {
      console.error("Search failed", e);
    } finally {
      if (alive.value) {
        isSearching.value = false;
      }
    }
  }, 300);
}

function getGooglePredictions(input: string): Promise<LocationSuggestion[]> {
  return new Promise((resolve, reject) => {
    if (!autocompleteService) return reject("No service");
    
    autocompleteService.getPlacePredictions(
      { input, componentRestrictions: { country: 'pl' }, types: ['geocode', 'establishment'] },
      (predictions, status) => {
        if (status !== google.maps.places.PlacesServiceStatus.OK || !predictions) {
          return resolve([]);
        }
        
        const mapped = predictions.map(p => markRaw({
          id: p.place_id,
          title: p.structured_formatting.main_text,
          subtitle: p.structured_formatting.secondary_text,
          source: 'google' as const
          // Removed 'original' to prevent Vue reactivity deep-watch crash on Google objects
        }));
        resolve(mapped);
      }
    );
  });
}

async function getNominatimPredictions(input: string): Promise<LocationSuggestion[]> {
  try {
    const response = await fetch(
      `https://nominatim.openstreetmap.org/search?format=json&q=${encodeURIComponent(input)}&countrycodes=pl&limit=5`,
      { headers: { 'Accept-Language': 'pl' } }
    );
    if (!response.ok) return [];
    
    const data = await response.json();
    return data.map((item: any) => ({
      id: item.place_id,
      title: item.display_name.split(',')[0],
      subtitle: item.display_name,
      source: 'nominatim' as const,
      original: item
    }));
  } catch (e) {
    return [];
  }
}

async function selectSuggestion(suggestion: LocationSuggestion) {
  searchQuery.value = suggestion.subtitle || suggestion.title;
  showSuggestions.value = false;
  
  if (!alive.value) return;

  if (suggestion.source === 'google') {
    // Resolve Google Place ID
    if (!geocoder) return;
    try {
      const response = await geocoder.geocode({ placeId: suggestion.id });
      if (!alive.value) return;
      
      if (response.results[0]?.geometry?.location) {
        const loc = response.results[0].geometry.location;
        selectedAddress.value = response.results[0].formatted_address;
        setLocation(loc.lat(), loc.lng());
      }
    } catch (e) {
      console.error("Geocoding failed", e);
      if (!alive.value) return;
      // Fallback: search query text on Nominatim if Google details fail
      const fallback = await getNominatimPredictions(suggestion.title);
      if (!alive.value) return;
      if (fallback.length > 0) selectSuggestion(fallback[0]);
    }
  } else {
    // Nominatim
    const lat = parseFloat(suggestion.original.lat);
    const lng = parseFloat(suggestion.original.lon);
    selectedAddress.value = suggestion.original.display_name;
    setLocation(lat, lng);
  }
}

function setLocation(lat: number, lng: number) {
  selectedLat.value = lat;
  selectedLng.value = lng;

  if (map && !mapLoadError.value) {
    try {
      if (marker) {
        marker.setPosition({ lat, lng });
      } else {
        marker = new google.maps.Marker({
          position: { lat, lng },
          map: map,
          animation: google.maps.Animation.DROP
        });
      }
      map.panTo({ lat, lng });
      map.setZoom(15);
    } catch (e) {
      console.error("Map interaction failed", e);
    }
  }
}

async function reverseGeocode(lat: number, lng: number) {
  if (!geocoder) return;
  try {
    const response = await geocoder.geocode({ location: { lat, lng } });
    if (response.results[0]) {
      selectedAddress.value = response.results[0].formatted_address;
      searchQuery.value = selectedAddress.value;
    }
  } catch (e) {
    selectedAddress.value = `${lat.toFixed(5)}, ${lng.toFixed(5)}`;
  }
}

function confirmSelection() {
  if (selectedLat.value !== null && selectedLng.value !== null) {
    emit('location-selected', {
      lat: selectedLat.value,
      lng: selectedLng.value,
      address: selectedAddress.value || `${selectedLat.value.toFixed(5)}, ${selectedLng.value.toFixed(5)}`
    });
  }
}

const hasSelection = computed(() => selectedLat.value !== null && selectedLng.value !== null);

const alive = ref(true);

onUnmounted(() => {
  alive.value = false;
  if (searchTimeout.value) clearTimeout(searchTimeout.value);
  if (marker) marker.setMap(null);
  marker = null;
  map = null;
});
</script>

<template>
  <div class="location-picker relative">
    <!-- Search bar with custom dropdown -->
    <div class="search-section mb-4 relative z-50">
      <div class="relative">
        <i class="pi pi-search absolute left-3 top-1/2 -translate-y-1/2 text-surface-400"></i>
        <input
          ref="searchInput"
          v-model="searchQuery"
          type="text"
          placeholder="Wyszukaj adres..."
          class="w-full pl-10 pr-10 py-3 rounded-xl border-2 border-surface-200 focus:border-primary-400 focus:outline-none transition-colors text-surface-800 dark:text-surface-100 dark:bg-surface-800 dark:border-surface-600"
          @input="handleInput"
          @focus="showSuggestions = suggestions.length > 0"
        />
        <i v-if="isSearching" class="pi pi-spin pi-spinner absolute right-3 top-1/2 -translate-y-1/2 text-primary-500"></i>
      </div>
      
      <!-- Custom Suggestions Dropdown -->
      <div v-if="showSuggestions" class="absolute left-0 right-0 mt-2 bg-white dark:bg-surface-800 border border-surface-200 dark:border-surface-600 rounded-xl shadow-xl max-h-60 overflow-y-auto z-50">
        <div 
          v-for="item in suggestions" 
          :key="item.id"
          class="p-3 hover:bg-surface-100 dark:hover:bg-surface-700 cursor-pointer border-b border-surface-100 dark:border-surface-700 last:border-b-0 flex items-start gap-3 transition-colors"
          @click="selectSuggestion(item)"
        >
          <i :class="item.source === 'google' ? 'pi pi-google' : 'pi pi-map-marker'" class="mt-1 text-surface-400"></i>
          <div>
            <div class="font-medium text-surface-800 dark:text-surface-100">{{ item.title }}</div>
            <div class="text-xs text-surface-500">{{ item.subtitle }}</div>
          </div>
        </div>
      </div>
      
      <p class="text-xs text-surface-400 mt-1">
        Wpisz adres (Google Maps + OpenStreetMap)
      </p>
    </div>

    <!-- Error message if map fails -->
    <div v-if="mapLoadError" class="mb-4 p-4 bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-700 rounded-xl">
      <div class="flex items-center gap-2 text-amber-700 dark:text-amber-400 mb-2">
        <i class="pi pi-exclamation-triangle"></i>
        <span class="font-medium">Podgląd mapy niedostępny</span>
      </div>
      <p class="text-sm text-surface-600 dark:text-surface-300">
        Wystąpił problem z Google Maps. Wyszukiwanie adresu nadal działa (korzystamy z alternatywnych źródeł).
      </p>
    </div>

    <!-- Map -->
    <!-- Map Wrapper (Isolacja DOM dla Google Maps) -->
    <div 
      v-show="!mapLoadError"
      class="relative rounded-xl border border-surface-200 dark:border-surface-600 shadow-sm overflow-hidden" 
      style="height: 350px;"
    >
      <!-- TO jest JEDYNY element, którego dotyka Google Maps -->
      <div ref="mapContainer" class="h-full w-full"></div>

      <!-- Vue overlay - NIE jako dziecko mapContainer, ale obok -->
      <div 
        v-if="!isMapReady" 
        class="absolute inset-0 flex items-center justify-center bg-surface-100 dark:bg-surface-700 z-10"
      >
        <div class="text-center">
          <i class="pi pi-spin pi-spinner text-3xl text-primary-500 mb-2"></i>
          <p class="text-surface-500">Ładowanie mapy...</p>
        </div>
      </div>
    </div>

    <!-- Selected location info -->
    <div v-if="hasSelection" class="selection-info mt-4 p-4 bg-emerald-50 dark:bg-emerald-900/20 rounded-xl border border-emerald-200 dark:border-emerald-700">
      <div class="flex items-center gap-2 text-emerald-700 dark:text-emerald-400">
        <i class="pi pi-check-circle"></i>
        <span class="font-medium">Wybrana lokalizacja:</span>
      </div>
      <p class="text-sm text-surface-600 dark:text-surface-300 mt-1 ml-6">
        {{ selectedAddress || `${selectedLat?.toFixed(5)}, ${selectedLng?.toFixed(5)}` }}
      </p>
    </div>

    <!-- Actions -->
    <div class="flex justify-end gap-3 mt-4">
      <Button
        v-if="showCancel !== false"
        label="Anuluj"
        severity="secondary"
        outlined
        @click="emit('cancel')"
      />
      <Button
        label="Potwierdź lokalizację"
        icon="pi pi-check"
        :disabled="!hasSelection"
        @click="confirmSelection"
      />
    </div>
  </div>
</template>

<style scoped>
.location-picker {
  max-width: 100%;
}

.map-container {
  z-index: 0;
}
</style>
