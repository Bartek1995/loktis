<script setup lang="ts">
/**
 * Report View - wyświetla raport z analizy
 * Wersja zmigrowana do czystego Tailwind CSS
 */
import { ref, computed, onMounted, onUnmounted, nextTick, watch } from 'vue';
import { useRouter, useRoute } from 'vue-router';
import { analyzerApi, type AnalysisReport, type POICategoryStats, type TrafficAnalysis, type NatureMetrics, type POIItem } from '@/api/analyzerApi';
import SettingsDrawer from '@/components/SettingsDrawer.vue';
import CoverageDebugPanel from '@/components/CoverageDebugPanel.vue';
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

interface GoogleMarkerEntry {
  marker: google.maps.marker.AdvancedMarkerElement;
  category?: string;
  name?: string;
  subcategory?: string;
  infoWindow?: google.maps.InfoWindow;
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
const googleMapsError = ref('');

// State
const report = ref<AnalysisReport | null>(null);
const originalUrl = ref('');
const isLoading = ref(false);
const error = ref('');
const mapContainer = ref<HTMLElement | null>(null);
const map = ref<L.Map | null>(null);
const googleMap = ref<google.maps.Map | null>(null);
const googleMarkers = ref<GoogleMarkerEntry[]>([]);
const leafletPoiMarkers = ref<L.CircleMarker[]>([]);
const googleMapId = import.meta.env.VITE_GOOGLE_MAPS_MAP_ID || 'DEMO_MAP_ID';

// DEV mode toggle (persisted in localStorage via SettingsDrawer)
const devMode = ref(false);

// Profile switching (rescore)
const availableProfiles = ref<Array<{ key: string; name: string; emoji: string; description: string }>>([]);
const isRescoring = ref(false);
const rescoreError = ref('');
const rescoreCount = ref(0);
const rescoreLimit = ref(3);

const currentProfileKey = computed(() => {
  return report.value?.profile?.key ||
         report.value?.generation_params?.profile?.key ||
         'family';
});

const rescoresRemaining = computed(() => Math.max(0, rescoreLimit.value - rescoreCount.value));

// Fetch available profiles on mount
async function loadAvailableProfiles() {
  try {
    const data = await analyzerApi.getProfiles();
    // Exclude 'custom' — requires user-defined radii
    availableProfiles.value = data.profiles.filter(p => p.key !== 'custom');
  } catch (e) {
    console.warn('Failed to load profiles for switcher', e);
  }
}

async function switchProfile(profileKey: string) {
  if (!report.value?.public_id || isRescoring.value) return;
  if (profileKey === currentProfileKey.value) return;
  if (rescoresRemaining.value <= 0) {
    rescoreError.value = `Osiągnięto limit zmian profilu (${rescoreLimit.value}/${rescoreLimit.value})`;
    setTimeout(() => { rescoreError.value = ''; }, 5000);
    return;
  }

  isRescoring.value = true;
  rescoreError.value = '';

  try {
    const result = await analyzerApi.rescoreReport(report.value.public_id, profileKey);

    // Update report in-place (partial update — scoring, verdict, AI, profile)
    (report.value as any).scoring = result.scoring;
    (report.value as any).verdict = result.verdict;
    (report.value as any).ai_insights = result.ai_insights;
    (report.value as any).profile = result.profile;
    
    // Update generation_params with new profile and radii
    if (report.value.generation_params) {
      report.value.generation_params.profile = result.generation_params.profile;
      report.value.generation_params.radii = result.generation_params.radii;
    }

    // Update rescore tracking
    rescoreCount.value = result.rescore_count;
    rescoreLimit.value = result.rescore_limit;
    report.value.rescore_count = result.rescore_count;
    report.value.rescore_limit = result.rescore_limit;

  } catch (err: any) {
    const errorData = err?.response?.data;
    if (err?.response?.status === 429) {
      rescoreError.value = errorData?.error || 'Limit zmian profilu osiągnięty';
      if (errorData?.rescore_count !== undefined) {
        rescoreCount.value = errorData.rescore_count;
      }
    } else {
      rescoreError.value = errorData?.error || err.message || 'Nie udało się zmienić profilu';
    }
    setTimeout(() => { rescoreError.value = ''; }, 5000);
  } finally {
    isRescoring.value = false;
  }
}

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
  googleMarkers.value.forEach((entry) => {
    const category = entry.category;
    if (category && categoryVisibility.value[category] !== undefined) {
      entry.marker.map = categoryVisibility.value[category] ? googleMap.value : null;
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

// Preferences Impact - shows how user settings affected the score
interface PreferenceImpactItem {
  category: string;
  categoryName: string;
  radius: number;
  score: number;
  poiCount: number;
  nearestDistance: number | null;
  detail: string;
  emoji: string;
}

interface PreferencesImpactData {
  topContributors: PreferenceImpactItem[];
  limitingFactors: PreferenceImpactItem[];
  hasData: boolean;
}

const categoryEmojis: Record<string, string> = {
  shops: '🛒',
  transport: '🚌',
  education: '🎓',
  health: '🏥',
  nature_place: '🌳',
  nature_background: '🌿',
  leisure: '🏃',
  food: '🍕',
  finance: '🏦',
};

const preferencesImpact = computed<PreferencesImpactData | null>(() => {
  const scoring = report.value?.scoring;
  const radii = report.value?.generation_params?.radii;
  
  if (!scoring?.category_scores || !radii) return null;
  
  const items: PreferenceImpactItem[] = [];
  
  for (const [category, catScore] of Object.entries(scoring.category_scores)) {
    if (!catScore || category === 'noise') continue;
    
    const radius = radii[category] || catScore.radius_used || 1000;
    const nearestDist = catScore.nearest_distance_m;
    
    // Generate detail text - consequence-focused, not technical
    let detail = '';
    if (catScore.poi_count > 0) {
      if (nearestDist !== null) {
        detail = `${catScore.poi_count} w zasięgu, najbliżej ${Math.round(nearestDist)}m`;
      } else {
        detail = `${catScore.poi_count} w zasięgu`;
      }
    } else {
      // No POIs found - show category-specific consequence message
      if (category === 'car_access') {
        // Special handling: roads may exist but parking/access not confirmed
        detail = `Brak parkingów/dojazdów w danych (sieć dróg niewyceniona)`;
      } else if (category === 'roads') {
        detail = `Analiza hałasu: brak danych o ruchu`;
      } else {
        detail = `Brak potwierdzonych miejsc w zasięgu ${radius}m`;
      }
    }
    
    items.push({
      category,
      categoryName: getCategoryName(category),
      radius,
      score: Math.round(catScore.score),
      poiCount: catScore.poi_count,
      nearestDistance: nearestDist,
      detail,
      emoji: categoryEmojis[category] || '📍',
    });
  }
  
  // Sort by score - top contributors are high, limiting are low
  const sorted = [...items].sort((a, b) => b.score - a.score);
  
  // Top 3 contributors (score >= 50)
  const topContributors = sorted.filter(i => i.score >= 50).slice(0, 3);
  
  // Limiting factors (score < 50), up to 3
  const limitingFactors = sorted.filter(i => i.score < 50).slice(-3).reverse();
  
  return {
    topContributors,
    limitingFactors,
    hasData: items.length > 0,
  };
});

// AI Narrative Summary - prefers AI insights from backend, fallback to local generation
const narrativeSummary = computed(() => {
  if (!report.value?.scoring || !report.value?.verdict) return null;
  
  // Try AI-generated insights first
  const aiInsights = (report.value as any).ai_insights;
  if (aiInsights?.summary) {
    return {
      mainText: aiInsights.summary,
      quickFacts: aiInsights.quick_facts || [],  // NEW: replaces attention_points
      attentionPoints: aiInsights.attention_points || aiInsights.quick_facts || [],  // Legacy fallback
      verificationChecklist: aiInsights.verification_checklist || [],
      recommendationLine: aiInsights.recommendation_line || '',  // NEW
      targetAudience: aiInsights.target_audience || '',  // NEW
      disclaimer: aiInsights.disclaimer || '',  // NEW: data quality warnings
      isAI: true,
    };
  }
  
  // Fallback: local generation
  const verdict = report.value.verdict;
  const profileName = report.value.generation_params?.profile?.name || 
                      report.value.profile?.name || 'wybrany profil';
  const strengths = report.value.scoring.strengths?.slice(0, 2) || [];
  const weaknesses = report.value.scoring.weaknesses?.slice(0, 1) || [];
  
  let levelText = '';
  if (verdict.level === 'recommended') {
    levelText = 'bardzo dobrze dopasowana';
  } else if (verdict.level === 'conditional') {
    levelText = 'umiarkowanie dopasowana';
  } else {
    levelText = 'słabo dopasowana';
  }
  
  return {
    mainText: `Ta lokalizacja jest ${levelText} do profilu "${profileName}". ${strengths.length > 0 ? 'Mocne strony: ' + strengths.join(', ') + '.' : ''} ${weaknesses.length > 0 ? 'Główny minus: ' + weaknesses[0] + '.' : ''}`.trim(),
    quickFacts: [],
    attentionPoints: [],
    verificationChecklist: [],
    recommendationLine: '',
    targetAudience: '',
    disclaimer: '',
    isAI: false,
  };
});

// Data quality from generation_params (for DEV mode)
// Note: data_quality is a new field from backend, not yet in TypeScript interface
const dataQuality = computed(() => {
  return (report.value as any)?.generation_params?.data_quality || null;
});

// Profile UX context - personalized texts per profile
const profileContext = computed(() => {
  const ux = report.value?.profile?.ux_context ||
             report.value?.generation_params?.profile?.ux_context ||
             (report.value as any)?.profile?.ux_context ||
             {};
  
  const profileName = report.value?.profile?.name ||
                      report.value?.generation_params?.profile?.name ||
                      'wybrany profil';
  
  return {
    reportIntro: ux.report_intro || 'Ocena lokalizacji',
    sectionOkolica: ux.section_okolica || 'Okolica',
    sectionOkolicaSub: ux.section_okolica_sub || 'Analiza lokalizacji i punktów POI',
    sectionPreferences: ux.section_preferences || 'Twoje preferencje – wpływ na ocenę',
    sectionPreferencesSub: ux.section_preferences_sub || 'Jak Twoje ustawienia wpłynęły na wynik',
    praktyceTips: ux.praktyce_tips || [
      'Porównaj z innymi lokalizacjami, które rozważasz',
      'Zwróć uwagę na wskazane kompromisy podczas oględzin',
      'Sprawdź porę dnia i hałas, jeśli to dla Ciebie istotne',
    ],
    whyNotHigherPrefix: ux.why_not_higher_prefix || 'Dlaczego nie wyższa ocena?',
    profileName,
  };
});

// UNIFIED CONFIDENCE - single source of truth
// Prefers data_quality.confidence_pct (from coverage analysis) over legacy verdict.confidence
const unifiedConfidence = computed(() => {
  const dq = dataQuality.value;
  
  // Priority 1: data_quality from generation_params (new system)
  if (dq?.confidence_pct !== undefined) {
    return {
      pct: dq.confidence_pct,
      source: 'data_quality',
      reasons: dq.reasons || [],
    };
  }
  
  // Priority 2: legacy verdict.confidence (fallback)
  if (report.value?.verdict?.confidence !== undefined) {
    return {
      pct: report.value.verdict.confidence,
      source: 'verdict_legacy',
      reasons: [],
    };
  }
  
  return { pct: 70, source: 'default', reasons: [] };
});

// Confidence color helper
const confidenceColor = computed(() => {
  const pct = unifiedConfidence.value.pct;
  if (pct >= 80) return 'emerald';
  if (pct >= 60) return 'amber';
  return 'red';
});

// Has actual data quality issues (errors, not just empty signal)
// SEMANTIC: 'empty' = valid signal (0 in radius), 'error' = data problem
const hasDataQualityIssues = computed(() => {
  const dq = dataQuality.value;
  if (!dq) return false;
  
  // Only show alert for ERRORS, not for empty categories
  const hasErrors = (dq.error_categories?.length || 0) > 0;
  const hasOverpassError = dq.overpass_status === 'error';
  const hasReasons = (dq.reasons?.length || 0) > 0;
  
  return hasErrors || hasOverpassError || hasReasons;
});

// Main limiting factor - explains why score isn't higher
const mainLimitingFactor = computed(() => {
  if (!report.value?.scoring) return null;
  
  const scoring = report.value.scoring;
  const totalScore = scoring.total_score;
  
  // Only show if score is not at max
  if (totalScore >= 90) return null;
  
  // Check for critical caps
  if (scoring.critical_caps_applied?.length > 0) {
    const cappedCategory = scoring.critical_caps_applied[0];
    if (cappedCategory) {
      return {
        reason: `Kategoria "${getCategoryName(cappedCategory)}" nie spełnia minimalnych wymagań profilu`,
        type: 'critical_cap'
      };
    }
  }
  
  // Check for noise penalty
  if (scoring.noise_penalty > 5) {
    return {
      reason: `Podwyższony poziom hałasu w okolicy – może wpływać na komfort, szczególnie przy otwartych oknach`,
      type: 'noise'
    };
  }
  
  // Check for roads penalty
  if (scoring.roads_penalty && scoring.roads_penalty > 5) {
    return {
      reason: `Bliskość dróg i infrastruktury transportowej – może wpływać na komfort i jakość powietrza`,
      type: 'roads'
    };
  }
  
  // Find lowest scoring category
  const limitingFactors = preferencesImpact.value?.limitingFactors;
  if (limitingFactors && limitingFactors.length > 0) {
    const lowest = limitingFactors[0];
    if (lowest && lowest.score < 30) {
      return {
        reason: `Ograniczona dostępność ${lowest.categoryName.toLowerCase()} w okolicy – może wymagać częstszych dojazdów`,
        type: 'category'
      };
    }
  }
  
  return null;
});

// Confidence explanation - explains why confidence may be reduced
const confidenceExplanation = computed(() => {
  if (!report.value?.scoring || !report.value?.verdict) return null;
  
  const confidence = report.value.verdict.confidence;
  const criticalCaps = report.value.scoring.critical_caps_applied || [];
  
  // If critical caps applied, explain the reduction
  if (criticalCaps.length > 0) {
    const cappedCategories = criticalCaps.map((cat: string) => getCategoryName(cat)).join(', ');
    return `Ograniczona przez niespełnione wymagania: ${cappedCategories}`;
  }
  
  // Standard explanations based on confidence level
  if (confidence >= 80) {
    return 'Wysoka zgodność z potrzebami profilu';
  } else if (confidence >= 60) {
    return 'Umiarkowana zgodność – niektóre kategorie wypadają słabiej';
  } else {
    return 'Niska zgodność – zalecana weryfikacja w terenie';
  }
});

// Edit preferences - go back to landing with current params preserved
function editPreferences() {
  if (!report.value) return;
  
  const params = {
    lat: report.value.listing.latitude,
    lng: report.value.listing.longitude,
    address: report.value.listing.location || '',
    price: report.value.listing.price,
    areaSqm: report.value.listing.area_sqm,
    profileKey: report.value.generation_params?.profile?.key || report.value.profile?.key || 'family',
    radiusOverrides: report.value.generation_params?.radii || {},
  };
  
  sessionStorage.setItem('editPreferencesData', JSON.stringify(params));
  router.push({ name: 'landing' });
}

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

function handleGalleryKeydown(e: KeyboardEvent) {
  if (!displayGallery.value) return;
  if (e.key === 'Escape') closeGallery();
  else if (e.key === 'ArrowRight') nextImage();
  else if (e.key === 'ArrowLeft') prevImage();
}

onMounted(() => {
  window.addEventListener('keydown', handleGalleryKeydown);
});
onUnmounted(() => {
  window.removeEventListener('keydown', handleGalleryKeydown);
});

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

const hasRealUrl = computed(() => {
  const url = report.value?.listing?.url;
  return url && !url.startsWith('location://');
});

function openOriginalUrl() {
  if (hasRealUrl.value) {
    window.open(report.value!.listing.url, '_blank');
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

// Field source helpers for property data section
function getFieldSourceClass(source: string | undefined): string {
  switch (source) {
    case 'user': return 'text-emerald-600';
    case 'listing': return 'text-indigo-600';
    case 'computed': return 'text-blue-600';
    case 'merged': return 'text-purple-600';
    default: return 'text-gray-500';
  }
}

function getFieldSourceIcon(source: string | undefined): string {
  switch (source) {
    case 'user': return 'pi pi-check-circle text-xs';
    case 'listing': return 'pi pi-file text-xs';
    case 'computed': return 'pi pi-calculator text-xs';
    case 'merged': return 'pi pi-link text-xs';
    default: return 'pi pi-question-circle text-xs';
  }
}

function getFieldSourceLabel(source: string | undefined): string {
  switch (source) {
    case 'user': return 'podane';
    case 'listing': return 'z ogłoszenia';
    case 'computed': return 'wyliczone';
    case 'merged': return 'mieszane';
    default: return 'nieznane';
  }
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
    car_access: 'Dostęp samochodem',
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
    car_access: 'pi-car',
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
      m => m.name === marker.name && m.subcategory === marker.subcategory
    );
    if (gMarker?.infoWindow) {
      gMarker.marker.map = googleMap.value;
      gMarker.infoWindow.open({
        map: googleMap.value,
        anchor: gMarker.marker,
      });
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

function getBadgeLabel(badge: string): string {
  const labels: Record<string, string> = {
    cafe: 'kawa',
    bakery: 'piekarnia',
    restaurant: 'restauracja',
    fast_food: 'fast food',
    meal_takeaway: 'na wynos',
    bar: 'bar',
    atm: 'bankomat',
    bank: 'bank',
    pharmacy: 'apteka',
    hospital: 'szpital',
    doctor: 'lekarz',
    dentist: 'dentysta',
    health: 'zdrowie',
    gym: 'siłownia',
    stadium: 'stadion',
    amusement_park: 'park rozrywki',
    bowling_alley: 'kręgle',
    movie_theater: 'kino',
    spa: 'spa',
    park: 'park',
    natural_feature: 'teren naturalny',
    campground: 'camping',
    supermarket: 'supermarket',
    convenience_store: 'sklep convenience',
    shopping_mall: 'centrum handlowe',
    store: 'sklep',
    school: 'szkoła',
    primary_school: 'szkoła',
    secondary_school: 'szkoła',
    university: 'uczelnia',
    library: 'biblioteka',
    subway_station: 'metro',
    bus_station: 'dworzec',
    train_station: 'dworzec',
    transit_station: 'węzeł',
    light_rail_station: 'tramwaj',
  };
  return labels[badge] || badge.replace(/_/g, ' ');
}

// Load Google Maps API dynamically
// Google Maps Bootstrap Loader — uses Google's recommended inline bootstrap
function loadGoogleMapsScript(): Promise<void> {
  return new Promise((resolve, reject) => {
    // Already bootstrapped
    if ((window as any).google?.maps?.importLibrary) {
      resolve();
      return;
    }

    const apiKey = import.meta.env.VITE_GOOGLE_MAPS_API_KEY;
    if (!apiKey || apiKey === 'your_google_maps_api_key_here') {
      googleMapsError.value = 'Brak klucza Google Maps API';
      reject(new Error('Missing Google Maps API key'));
      return;
    }

    // Google's inline bootstrap
    ((g: any) => {
      let h: any, a: any, k: any;
      const p = "The Google Maps JavaScript API";
      const c = "google";
      const l = "importLibrary";
      const q = "__ib__";
      const m = document;
      let b = (window as any);
      b = b[c] || (b[c] = {});
      const d = b.maps || (b.maps = {});
      const r = new Set<string>();
      const e = new URLSearchParams();
      const u = () =>
        // @ts-ignore
        h || (h = new Promise(async (f: any, n: any) => {
          await (a = m.createElement("script"));
          e.set("libraries", [...r] + "");
          for (k in g)
            e.set(
              k.replace(/[A-Z]/g, (t: string) => "_" + t[0]!.toLowerCase()),
              g[k] as string,
            );
          e.set("callback", c + ".maps." + q);
          a.src = `https://maps.googleapis.com/maps/api/js?` + e;
          d[q] = f;
          a.onerror = () => (h = n(Error(p + " could not load.")));
          a.nonce = (m.querySelector("script[nonce]") as any)?.nonce || "";
          m.head.append(a);
        }));
      d[l]
        ? console.warn(p + " only loads once. Ignoring:", g)
        : (d[l] = (f: string, ...n: any[]) => (r.add(f), u().then(() => d[l](f, ...n))));
    })({
      key: apiKey,
      v: "weekly",
      language: "pl",
      region: "PL",
    });

    resolve();
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
  
  googleMarkers.value.forEach((entry) => {
    entry.infoWindow?.close();
    entry.marker.map = null;
  });
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
    await loadGoogleMapsScript();
    
    // Import libraries explicitly
    const { Map } = await window.google.maps.importLibrary("maps") as google.maps.MapsLibrary;
    const { AdvancedMarkerElement, PinElement } = await window.google.maps.importLibrary("marker") as google.maps.MarkerLibrary;

    cleanupMaps();

    const lat = report.value.listing.latitude;
    const lon = report.value.listing.longitude;

    googleMap.value = new Map(mapContainer.value, {
      center: { lat, lng: lon },
      zoom: 15,
      mapTypeControl: false,
      streetViewControl: false,
      fullscreenControl: false,
      mapId: googleMapId,
    });

    const mainPin = new PinElement({ background: '#2563EB', borderColor: '#ffffff', glyphColor: '#ffffff' });

    const mainMarker = new AdvancedMarkerElement({
      position: { lat, lng: lon },
      map: googleMap.value,
      title: report.value.listing.title || 'Nieruchomość',
      gmpClickable: true,
      content: mainPin,
    });

    const infoWindow = new window.google.maps.InfoWindow({
      content: `<b>${report.value.listing.title || 'Nieruchomość'}</b>`,
    });
    
    infoWindow.open({
      map: googleMap.value,
      anchor: mainMarker,
    });

    googleMarkers.value.push({
      marker: mainMarker,
      infoWindow,
    });

    if (report.value.neighborhood.markers) {
      report.value.neighborhood.markers.forEach((poi) => {
        const color = poi.color || '#3B82F6';
        const isVisible = categoryVisibility.value[poi.category] !== false;

        const poiPin = new PinElement({
            background: color,
            borderColor: '#ffffff',
            glyphColor: '#ffffff',
            scale: 0.85,
          });

        const poiMarker = new AdvancedMarkerElement({
          position: { lat: poi.lat, lng: poi.lon },
          map: isVisible ? googleMap.value : null,
          title: poi.name,
          gmpClickable: true,
          content: poiPin,
        });

        const poiInfoWindow = new window.google.maps.InfoWindow({
          content: `<b>${poi.name}</b><br><span style="font-size: 12px; color: #666;">${poi.subcategory} (${Math.round(poi.distance || 0)}m)</span>`,
        });

        poiMarker.addListener('gmp-click', () => {
          poiInfoWindow.open({
            map: googleMap.value,
            anchor: poiMarker,
          });
        });

        googleMarkers.value.push({
          marker: poiMarker,
          category: poi.category,
          name: poi.name,
          subcategory: poi.subcategory,
          infoWindow: poiInfoWindow,
        });
      });
    }
  } catch (e) {
    console.error('Error initializing Google Maps:', e);
    googleMapsError.value = 'Wystąpił błąd podczas inicjalizacji mapy';
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

// DEV: Re-analyze with same parameters (for testing)
const isRefreshing = ref(false);
const refreshStatus = ref('');

async function refreshReport() {
  if (!report.value?.listing || isRefreshing.value) return;
  
  const listing = report.value.listing;
  const lat = listing.latitude;
  const lon = listing.longitude;
  
  if (!lat || !lon) {
    alert('Brak współrzędnych lokalizacji');
    return;
  }
  
  isRefreshing.value = true;
  refreshStatus.value = 'Rozpoczynanie analizy...';
  
  try {
    const newReport = await analyzerApi.analyzeLocationStream(
      lat,
      lon,
      listing.price || 0,
      listing.area_sqm || 0,
      listing.location || '',
      500, // default radius
      listing.url?.startsWith('http') ? listing.url : undefined,  // Only real URLs, not location://
      (event) => {
        refreshStatus.value = event.message || event.status;
      },
      report.value.profile?.key || 'family',
      'hybrid'
    );
    
    // Update report in place
    report.value = newReport;
    refreshStatus.value = 'Gotowe!';
    
    // Reinitialize map
    nextTick(initMap);
    
    // Clear status after 2s
    setTimeout(() => {
      refreshStatus.value = '';
    }, 2000);
    
  } catch (err: any) {
    refreshStatus.value = `Błąd: ${err.message}`;
    setTimeout(() => {
      refreshStatus.value = '';
    }, 5000);
  } finally {
    isRefreshing.value = false;
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
        
        await nextTick();
        initMap();
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
      // Initialize rescore tracking from loaded report
      rescoreCount.value = (report.value as any).rescore_count || 0;
      rescoreLimit.value = (report.value as any).rescore_limit || 3;
    } catch (e) {
      error.value = 'Nie udało się pobrać raportu. Sprawdź czy link jest poprawny.';
    } finally {
      isLoading.value = false;
      await nextTick();
      initMap();
    }
    return;
  }
  
  // Case 3: History detail by numeric ID (legacy)
  const id = route.params.id;
  if (id) {
    isLoading.value = true;
    try {
      report.value = await analyzerApi.getHistoryDetail(Number(id));
    } catch (e) {
      error.value = 'Nie udało się pobrać raportu';
    } finally {
      isLoading.value = false;
      await nextTick();
      initMap();
    }
    return;
  }
  
  router.replace({ name: 'landing' });
});

// Load profiles for switcher after report is loaded
watch(hasReport, (val) => {
  if (val) {
    loadAvailableProfiles();
    // Initialize rescore tracking from streaming result
    const r = report.value as any;
    if (r?.rescore_count !== undefined) rescoreCount.value = r.rescore_count;
    if (r?.rescore_limit !== undefined) rescoreLimit.value = r.rescore_limit;
  }
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
        <!-- DEV Mode: Coverage Debug Panel -->
        <CoverageDebugPanel v-if="devMode && dataQuality" :data-quality="dataQuality" />
        
        <!-- USER Mode: Data Quality Alert (only for actual errors, not empty) -->
        <div v-if="!devMode && hasDataQualityIssues" 
             class="p-4 rounded-xl border flex items-start gap-3"
             :class="unifiedConfidence.pct < 60 ? 'bg-red-50 border-red-200' : 'bg-amber-50 border-amber-200'">
          <span class="text-xl">{{ unifiedConfidence.pct < 60 ? '⚠️' : 'ℹ️' }}</span>
          <div>
            <p class="font-semibold mb-1" :class="unifiedConfidence.pct < 60 ? 'text-red-800' : 'text-amber-800'">
              Możliwe niepełne dane (pewność: {{ unifiedConfidence.pct }}%)
            </p>
            <ul v-if="unifiedConfidence.reasons.length" class="text-sm space-y-0.5" :class="unifiedConfidence.pct < 60 ? 'text-red-700' : 'text-amber-700'">
              <li v-for="(reason, idx) in unifiedConfidence.reasons.slice(0, 3)" :key="idx">• {{ reason }}</li>
            </ul>
            <p v-else class="text-sm" :class="unifiedConfidence.pct < 60 ? 'text-red-700' : 'text-amber-700'">
              Niektóre źródła danych mogły być niedostępne
            </p>
          </div>
        </div>
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
                v-if="hasRealUrl"
                @click="openOriginalUrl"
                class="px-4 py-2 rounded-xl border-2 border-slate-200 text-slate-600 font-medium hover:bg-slate-50 transition-colors flex items-center gap-2"
              >
                <i class="pi pi-external-link"></i>
                <span class="hidden sm:inline">Zobacz ogłoszenie</span>
              </button>
              <button 
                @click="editPreferences"
                class="px-4 py-2 rounded-xl border-2 border-blue-200 text-blue-600 font-medium hover:bg-blue-50 transition-colors flex items-center gap-2"
                title="Wróć do konfiguracji z zachowanymi ustawieniami"
              >
                <i class="pi pi-pencil"></i>
                <span class="hidden sm:inline">Zmień preferencje</span>
              </button>
              <button
                @click="refreshReport"
                :disabled="isRefreshing"
                class="flex items-center gap-2 px-4 py-2.5 bg-amber-500 hover:bg-amber-600 disabled:bg-amber-300 text-white rounded-xl font-medium transition-all text-sm shadow-md"
                title="DEV: Odśwież raport z tymi samymi danymi"
              >
                <i :class="isRefreshing ? 'pi pi-spin pi-spinner' : 'pi pi-refresh'"></i>
                <span class="hidden sm:inline">{{ refreshStatus || 'DEV: Odśwież' }}</span>
              </button>
              <button
                class="flex items-center gap-2 px-4 py-2.5 bg-white hover:bg-slate-50 text-slate-700 rounded-xl font-medium transition-all text-sm shadow-md border border-slate-200"
                @click="$router.push({ name: 'landing' })"
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
        
        <!-- TL;DR Section removed - information now consolidated in AI insights -->
        
        <!-- Znane dane nieruchomości - tylko gdy podano jakiekolwiek dane -->
        <div 
          v-if="report!.property_completeness?.has_any" 
          class="relative bg-white rounded-2xl p-6 shadow-lg border border-slate-100 overflow-hidden"
        >
          <div class="absolute top-0 left-0 right-0 h-1 bg-gradient-to-r from-slate-300 to-gray-400"></div>
          
          <div class="flex items-center gap-3 mb-4">
            <div class="w-10 h-10 rounded-xl bg-gradient-to-br from-slate-400 to-gray-500 flex items-center justify-center shadow-md">
              <i class="pi pi-home text-white"></i>
            </div>
            <div>
              <h2 class="text-lg font-bold text-slate-900">Znane dane nieruchomości</h2>
              <!-- Dynamic subtitle based on source -->
              <p class="text-sm text-gray-500">
                <template v-if="report!.property_completeness?.source === 'listing'">Dane z ogłoszenia</template>
                <template v-else-if="report!.property_completeness?.source === 'merged'">Dane mieszane (ogłoszenie + użytkownik)</template>
                <template v-else>Dane podane przez użytkownika</template>
              </p>
            </div>
          </div>
          
          <div class="grid grid-cols-2 md:grid-cols-3 gap-4">
            <!-- Cena -->
            <div v-if="report!.property_completeness?.has_price" class="bg-slate-50 rounded-xl p-4">
              <div class="text-sm text-gray-500 mb-1">Cena</div>
              <div class="text-lg font-bold text-slate-900">
                {{ formatPrice(report!.listing.price) }}
              </div>
              <div 
                class="text-xs mt-1 flex items-center gap-1"
                :class="getFieldSourceClass(report!.property_completeness?.fields?.price?.source)"
              >
                <i :class="getFieldSourceIcon(report!.property_completeness?.fields?.price?.source)"></i>
                {{ getFieldSourceLabel(report!.property_completeness?.fields?.price?.source) }}
              </div>
            </div>
            
            <!-- Metraż -->
            <div v-if="report!.property_completeness?.has_area" class="bg-slate-50 rounded-xl p-4">
              <div class="text-sm text-gray-500 mb-1">Metraż</div>
              <div class="text-lg font-bold text-slate-900">
                {{ report!.listing.area_sqm }} m²
              </div>
              <div 
                class="text-xs mt-1 flex items-center gap-1"
                :class="getFieldSourceClass(report!.property_completeness?.fields?.area_sqm?.source)"
              >
                <i :class="getFieldSourceIcon(report!.property_completeness?.fields?.area_sqm?.source)"></i>
                {{ getFieldSourceLabel(report!.property_completeness?.fields?.area_sqm?.source) }}
              </div>
            </div>
            
            <!-- Cena/m² (zawsze computed) -->
            <div v-if="report!.property_completeness?.has_price_per_sqm" class="bg-blue-50 rounded-xl p-4">
              <div class="text-sm text-gray-500 mb-1">Cena za m²</div>
              <div class="text-lg font-bold text-slate-900">
                {{ formatPrice(report!.listing.price_per_sqm) }}/m²
              </div>
              <div class="text-xs text-blue-600 mt-1 flex items-center gap-1">
                <i class="pi pi-calculator text-xs"></i>
                wyliczone
              </div>
            </div>
          </div>
        </div>
        
        <!-- Profile Switcher -->
        <div v-if="availableProfiles.length > 1 && report!.verdict" class="bg-white rounded-2xl p-5 shadow-lg border border-slate-100">
          <div class="flex items-center justify-between mb-3">
            <h3 class="text-sm font-semibold text-slate-700 flex items-center gap-2">
              <i class="pi pi-users text-indigo-500"></i>
              Zmień profil
            </h3>
            <span 
              class="text-xs px-2.5 py-1 rounded-full font-medium"
              :class="rescoresRemaining > 0 ? 'bg-indigo-50 text-indigo-600' : 'bg-red-50 text-red-600'"
            >
              {{ rescoresRemaining > 0 ? `Pozostało ${rescoresRemaining}/${rescoreLimit}` : 'Limit osiągnięty' }}
            </span>
          </div>
          
          <!-- Profile pills -->
          <div class="flex flex-wrap gap-2">
            <button
              v-for="profile in availableProfiles"
              :key="profile.key"
              @click="switchProfile(profile.key)"
              :disabled="isRescoring || (rescoresRemaining <= 0 && profile.key !== currentProfileKey)"
              class="flex items-center gap-1.5 px-3 py-2 rounded-xl text-sm font-medium transition-all duration-200 border"
              :class="[
                profile.key === currentProfileKey
                  ? 'bg-indigo-500 text-white border-indigo-500 shadow-md shadow-indigo-200'
                  : rescoresRemaining <= 0
                    ? 'bg-slate-50 text-slate-400 border-slate-200 cursor-not-allowed'
                    : 'bg-white text-slate-700 border-slate-200 hover:border-indigo-300 hover:bg-indigo-50 hover:text-indigo-700 cursor-pointer'
              ]"
            >
              <span>{{ profile.emoji }}</span>
              <span>{{ profile.name }}</span>
            </button>
          </div>
          
          <!-- Loading indicator -->
          <div v-if="isRescoring" class="mt-3 flex items-center gap-2 text-sm text-indigo-600">
            <svg class="animate-spin h-4 w-4" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
              <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
              <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
            </svg>
            Przeliczanie scoringu dla nowego profilu...
          </div>
          
          <!-- Error message -->
          <div v-if="rescoreError" class="mt-3 text-sm text-red-600 bg-red-50 rounded-lg px-3 py-2">
            {{ rescoreError }}
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
                  class="px-3 py-1 rounded-full text-xs font-semibold cursor-help"
                  :class="{
                    'bg-emerald-100 text-emerald-700': unifiedConfidence.pct >= 80,
                    'bg-amber-100 text-amber-700': unifiedConfidence.pct >= 60 && unifiedConfidence.pct < 80,
                    'bg-slate-100 text-slate-700': unifiedConfidence.pct < 60
                  }"
                  :title="confidenceExplanation || 'Pewność oznacza, w jakim stopniu lokalizacja spełnia kluczowe potrzeby wybranego profilu'"
                >
                  {{ unifiedConfidence.pct }}% pewności
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
          
          <!-- Najważniejsze w 10 sekund (formerly AI Narrative Summary) -->
          <div v-if="narrativeSummary" class="mt-5 p-4 bg-gradient-to-r from-slate-50 to-gray-50 rounded-xl border border-slate-200">
            <div class="flex items-start gap-3">
              <div class="w-8 h-8 rounded-lg bg-gradient-to-br from-violet-400 to-purple-500 flex items-center justify-center flex-shrink-0">
                <i class="pi pi-bolt text-white text-sm"></i>
              </div>
              <div class="flex-1">
                <h4 class="font-bold text-slate-800 mb-2">Najważniejsze w 10 sekund</h4>
                
                <!-- Quick Facts (NEW - replaces attention_points) -->
                <ul v-if="narrativeSummary.quickFacts?.length" class="space-y-1.5 mb-3">
                  <li 
                    v-for="(fact, idx) in narrativeSummary.quickFacts" 
                    :key="idx"
                    class="flex items-start gap-2 text-sm"
                    :class="fact.startsWith('✅') ? 'text-emerald-700' : fact.startsWith('⚠') ? 'text-amber-700' : 'text-slate-600'"
                  >
                    <span>{{ fact }}</span>
                  </li>
                </ul>
                
                <!-- Main summary text -->
                <p class="text-slate-600 leading-relaxed text-sm">{{ narrativeSummary.mainText }}</p>
                
                <!-- Recommendation Line (NEW - decision CTA) -->
                <div v-if="narrativeSummary.recommendationLine" class="mt-3 p-3 bg-blue-50 border border-blue-200 rounded-lg">
                  <p class="text-blue-800 font-semibold text-sm">{{ narrativeSummary.recommendationLine }}</p>
                </div>
                
                <!-- Target Audience (NEW) -->
                <p v-if="narrativeSummary.targetAudience" class="mt-2 text-xs text-slate-500 italic">
                  {{ narrativeSummary.targetAudience }}
                </p>
                
                <!-- Disclaimer (data quality warnings) -->
                <div v-if="narrativeSummary.disclaimer" class="mt-3 p-3 bg-amber-50 border border-amber-200 rounded-lg">
                  <p class="text-amber-800 text-xs flex items-start gap-2">
                    <span class="mt-0.5">⚠</span>
                    <span>{{ narrativeSummary.disclaimer }}</span>
                  </p>
                </div>
              </div>
            </div>
          </div>
          
          <!-- Verification Checklist (NEW - practical things to check in person) -->
          <div v-if="narrativeSummary?.verificationChecklist?.length" class="mt-4 p-4 bg-emerald-50 border border-emerald-200 rounded-xl">
            <h4 class="font-semibold text-emerald-800 mb-2 flex items-center gap-2">
              <i class="pi pi-check-circle"></i>
              Co sprawdzić osobiście
            </h4>
            <ul class="space-y-2">
              <li 
                v-for="(item, idx) in narrativeSummary.verificationChecklist" 
                :key="idx"
                class="flex items-start gap-2 text-sm text-emerald-700"
              >
                <span class="text-emerald-500 mt-0.5">☑</span>
                <span>{{ item }}</span>
              </li>
            </ul>
          </div>
          
          <!-- How to use this report (MOVED UP - per user feedback) -->
          <div class="mt-4 p-4 bg-slate-50 border border-slate-200 rounded-xl">
            <h4 class="font-semibold text-slate-700 mb-2 flex items-center gap-2">
              <i class="pi pi-info-circle"></i>
              Co sprawdzić podczas wizyty
            </h4>
            <ul class="space-y-1.5 text-sm text-slate-600">
              <li v-for="(tip, idx) in profileContext.praktyceTips" :key="idx" class="flex items-start gap-2">
                <span class="text-slate-400">•</span>
                <span>{{ tip }}</span>
              </li>
            </ul>
          </div>
          
          <!-- Why not higher? Section -->
          <div v-if="mainLimitingFactor" class="mt-4 p-4 bg-amber-50 border border-amber-200 rounded-xl">
            <div class="flex items-start gap-3">
              <div class="w-8 h-8 rounded-lg bg-amber-100 flex items-center justify-center flex-shrink-0">
                <i class="pi pi-question-circle text-amber-600"></i>
              </div>
              <div>
                <h4 class="font-semibold text-amber-800 mb-1">{{ profileContext.whyNotHigherPrefix }}</h4>
                <p class="text-sm text-amber-700">
                  Główne ograniczenie: <strong>{{ mainLimitingFactor.reason }}</strong>
                </p>
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
        
        <!-- Preferences Impact Section -->
        <div v-if="preferencesImpact?.hasData" class="relative bg-white rounded-2xl p-6 shadow-lg border border-slate-100 overflow-hidden">
          <div class="absolute top-0 left-0 right-0 h-1 bg-gradient-to-r from-violet-400 via-purple-500 to-indigo-500"></div>
          
          <div class="flex items-center gap-3 mb-6">
            <div class="w-12 h-12 rounded-xl bg-gradient-to-br from-violet-400 to-purple-600 flex items-center justify-center shadow-lg">
              <i class="pi pi-sliders-h text-xl text-white"></i>
            </div>
            <div>
              <h3 class="font-bold text-xl text-slate-800">{{ profileContext.sectionPreferences }}</h3>
              <p class="text-sm text-slate-500">{{ profileContext.sectionPreferencesSub }}</p>
            </div>
          </div>
          
          <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
            <!-- Top Contributors -->
            <div v-if="preferencesImpact.topContributors.length" class="bg-gradient-to-br from-emerald-50 to-green-50 rounded-xl p-4 border border-emerald-100">
              <h4 class="font-semibold text-sm text-emerald-700 mb-3 flex items-center gap-2">
                <span class="w-5 h-5 rounded-full bg-emerald-500 flex items-center justify-center">
                  <i class="pi pi-arrow-up text-white text-xs"></i>
                </span>
                Najsilniej wpłynęły na ocenę
              </h4>
              <div class="space-y-3">
                <div 
                  v-for="item in preferencesImpact.topContributors" 
                  :key="item.category"
                  class="flex items-start gap-3 p-3 bg-white/70 rounded-lg"
                >
                  <span class="text-xl">{{ item.emoji }}</span>
                  <div class="flex-1 min-w-0">
                    <div class="flex items-center justify-between gap-2">
                      <span class="font-medium text-slate-800">{{ item.categoryName }}</span>
                      <span class="text-xs font-mono px-2 py-0.5 bg-emerald-100 text-emerald-700 rounded">{{ item.radius }}m</span>
                    </div>
                    <div class="text-xs text-slate-500 mt-0.5">
                      {{ item.detail }}
                    </div>
                  </div>
                </div>
              </div>
            </div>
            
            <!-- Limiting Factors -->
            <div v-if="preferencesImpact.limitingFactors.length" class="bg-gradient-to-br from-amber-50 to-orange-50 rounded-xl p-4 border border-amber-100">
              <h4 class="font-semibold text-sm text-amber-700 mb-3 flex items-center gap-2">
                <span class="w-5 h-5 rounded-full bg-amber-500 flex items-center justify-center">
                  <i class="pi pi-arrow-down text-white text-xs"></i>
                </span>
                Największe kompromisy
              </h4>
              <div class="space-y-3">
                <div 
                  v-for="item in preferencesImpact.limitingFactors" 
                  :key="item.category"
                  class="flex items-start gap-3 p-3 bg-white/70 rounded-lg"
                >
                  <span class="text-xl">{{ item.emoji }}</span>
                  <div class="flex-1 min-w-0">
                    <div class="flex items-center justify-between gap-2">
                      <span class="font-medium text-slate-800">{{ item.categoryName }}</span>
                      <span class="text-xs font-mono px-2 py-0.5 bg-amber-100 text-amber-700 rounded">{{ item.radius }}m</span>
                    </div>
                    <div class="text-xs text-slate-500 mt-0.5">
                      {{ item.detail }}
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
        
        <!-- NOTE: 'Jak użyć tego raportu' section moved to top of report near verdict -->
        <!-- Dane z ogłoszenia - tylko gdy źródło to listing/provider (nie user input) i są dane listing-specific -->
        <div 
          v-if="report!.listing?.source !== 'user' && (report!.listing?.description || report!.listing?.images?.length)"
          class="relative bg-white rounded-2xl p-6 shadow-lg border border-slate-100 overflow-hidden"
        >
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
                <h2 class="text-xl font-bold text-slate-800">{{ profileContext.sectionOkolica }}</h2>
                <p class="text-sm text-slate-500">{{ profileContext.sectionOkolicaSub }}</p>
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
                    <!-- DEV only: element count -->
                    <div v-if="devMode" class="text-sm text-slate-600">
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
                        <span
                          v-if="(stats as any).count_secondary"
                          class="text-xs text-slate-400"
                          :title="`+${(stats as any).count_secondary} z innych kategorii`"
                        >
                          +{{ (stats as any).count_secondary }}
                        </span>
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
                      v-for="(item, idx) in (stats as POICategoryStats).items.slice(0, 3)"
                      :key="`${category}-${idx}-${item.name}`"
                      class="flex items-center justify-between py-2 px-3 bg-slate-50 rounded-lg hover:bg-slate-100 transition-colors"
                    >
                      <div class="flex items-start gap-2 min-w-0">
                        <span 
                          class="w-2 h-2 rounded-full flex-shrink-0 mt-1"
                          :style="{ background: getPoiItemColor(category, item.subcategory) }"
                        ></span>
                        <div class="min-w-0">
                          <div class="truncate text-sm text-slate-700">{{ item.name }}</div>
                          <div v-if="item.badges?.length" class="flex flex-wrap gap-1 mt-1">
                            <span
                              v-for="badge in item.badges.slice(0, 3)"
                              :key="badge"
                              class="px-2 py-0.5 text-[10px] rounded-full bg-slate-200 text-slate-600"
                            >
                              {{ getBadgeLabel(badge) }}
                            </span>
                          </div>
                        </div>
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
        
        <!-- Generation Parameters (collapsed) -->
        <details v-if="report!.generation_params" class="bg-white rounded-2xl shadow-lg border border-slate-100 overflow-hidden">
          <summary class="cursor-pointer px-6 py-4 flex items-center gap-3 hover:bg-slate-50 transition-colors">
            <div class="w-10 h-10 rounded-xl bg-gradient-to-br from-slate-400 to-slate-600 flex items-center justify-center shadow">
              <i class="pi pi-cog text-white"></i>
            </div>
            <div class="flex-1">
              <h3 class="font-bold text-slate-800">Parametry analizy</h3>
              <p class="text-xs text-slate-500">Kliknij, aby zobaczyć szczegóły</p>
            </div>
            <i class="pi pi-chevron-down text-slate-400"></i>
          </summary>
          
          <div class="px-6 pb-6 border-t border-slate-100 pt-4">
            <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
              <!-- Profile Info -->
              <div class="bg-slate-50 rounded-xl p-4">
                <h4 class="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-3">Profil</h4>
                <div class="flex items-center gap-3">
                  <span class="text-3xl">{{ report!.generation_params.profile?.emoji || '🏠' }}</span>
                  <div>
                    <p class="font-bold text-slate-800">{{ report!.generation_params.profile?.name || 'Standardowy' }}</p>
                    <p class="text-xs text-slate-500">{{ report!.generation_params.profile?.key || 'urban' }}</p>
                  </div>
                </div>
              </div>
              
              <!-- Coords & Time -->
              <div class="bg-slate-50 rounded-xl p-4">
                <h4 class="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-3">Dane</h4>
                <div class="space-y-2 text-sm">
                  <div class="flex justify-between">
                    <span class="text-slate-500">Współrzędne:</span>
                    <span class="font-mono text-slate-700">
                      {{ report!.generation_params.coords?.lat?.toFixed(5) }}, {{ report!.generation_params.coords?.lon?.toFixed(5) }}
                    </span>
                  </div>
                  <div class="flex justify-between">
                    <span class="text-slate-500">Promień pobierania:</span>
                    <span class="font-medium text-slate-700">{{ report!.generation_params.fetch_radius }}m</span>
                  </div>
                  <div class="flex justify-between">
                    <span class="text-slate-500">Provider:</span>
                    <span class="font-medium text-slate-700">{{ report!.generation_params.poi_provider }}</span>
                  </div>
                </div>
              </div>
            </div>
            
            <!-- Radii per category -->
            <div v-if="report!.generation_params.radii" class="mt-6">
              <h4 class="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-3">Promienie per kategoria</h4>
              <div class="grid grid-cols-2 md:grid-cols-4 gap-2">
                <div 
                  v-for="(radius, category) in report!.generation_params.radii" 
                  :key="category"
                  class="bg-slate-50 rounded-lg p-3 flex items-center gap-2"
                >
                  <span 
                    class="w-3 h-3 rounded-full flex-shrink-0"
                    :style="{ background: getCategoryColor(category as string) }"
                  ></span>
                  <div class="min-w-0 flex-1">
                    <p class="text-xs text-slate-500 truncate">{{ getCategoryName(category as string) }}</p>
                    <p class="font-bold text-sm text-slate-700">{{ radius }}m</p>
                  </div>
                </div>
              </div>
            </div>
            
            <!-- Generation time -->
            <div v-if="report!.generation_params.generated_at" class="mt-4 text-xs text-slate-400 text-right">
              Wygenerowano: {{ new Date(report!.generation_params.generated_at).toLocaleString('pl-PL') }}
            </div>
          </div>
        </details>
      </div>
    </div>
  </div>
  
  <!-- Settings Drawer (DEV mode toggle) -->
  <SettingsDrawer v-model:dev-mode="devMode" />
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
