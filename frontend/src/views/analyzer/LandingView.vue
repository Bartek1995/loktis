<script setup lang="ts">
/**
 * Loktis - Landing View - strona główna z formularzem analizy lokalizacji
 * loktis.pl - Analiza ryzyka zakupu mieszkania
 * 
 * Redesigned with HomePage style + analyzer functionality
 */
import { ref, computed, watch, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { analyzerApi, getErrorMessage, type HistoryItem } from '@/api/analyzerApi'
import LocationPicker from '@/components/LocationPicker.vue'
import MdiIcon from '@/components/icons/MdiIcon.vue'
import { mdiChevronDown, mdiArrowUp, mdiCheckCircle, mdiMapMarker, mdiChartBar, mdiShieldCheck, mdiAlertCircle, mdiHomeCityOutline, mdiTreeOutline, mdiVolumeHigh, mdiCash, mdiLock, mdiLockOpen } from '@mdi/js'

// Base components
import BaseSection from '@/components/base/BaseSection.vue'
import BaseButton from '@/components/base/BaseButton.vue'
import BaseAccordion from '@/components/base/BaseAccordion.vue'

// Images
import faqImage from '@/assets/img/faq.webp'

const router = useRouter()

// State - location first approach
const selectedLocation = ref<{ lat: number; lng: number; address: string } | null>(null)
const price = ref<number | null>(null)
const areaSqm = ref<number | null>(null)
const referenceUrl = ref('')
const radius = ref(500)
const profileKey = ref<string>('family')  // Nowy system profili
const poiProvider = ref<'overpass' | 'google' | 'hybrid'>('hybrid')

// UI State
const isLoading = ref(false)
const loadingStatus = ref('')
const loadingProgress = ref(0)
const recentAnalyses = ref<HistoryItem[]>([])
const isLoadingRecent = ref(false)
const showAdvanced = ref(false)
const errorMessage = ref('')

// Loading steps for progress animation
const loadingSteps = [
  { status: 'Inicjalizacja...', progress: 10 },
  { status: 'Pobieranie danych...', progress: 25 },
  { status: 'Analizowanie okolicy...', progress: 50 },
  { status: 'Przeliczanie dla profilu...', progress: 70 },
  { status: 'Sprawdzanie POI...', progress: 80 },
  { status: 'Generowanie raportu...', progress: 90 },
]

// Profile options - 7 profili z nowego systemu (6 predefiniowanych + 1 własny)
const profileOptions = [
  { 
    value: 'urban' as const, 
    emoji: '🏙️', 
    name: 'City Life',
    description: 'Transport, gastronomia, życie nocne',
    color: 'from-blue-400 to-indigo-500'
  },
  { 
    value: 'family' as const, 
    emoji: '👨‍👩‍👧‍👦', 
    name: 'Rodzina z dziećmi',
    description: 'Szkoły, zdrowie, park, cisza',
    color: 'from-emerald-400 to-teal-500'
  },
  { 
    value: 'quiet_green' as const, 
    emoji: '🌿', 
    name: 'Spokojnie i zielono',
    description: 'Cisza, zieleń, mniej usług',
    color: 'from-green-400 to-lime-500'
  },
  { 
    value: 'remote_work' as const, 
    emoji: '💻', 
    name: 'Home Office',
    description: 'Cisza w dzień, podstawy w pobliżu',
    color: 'from-violet-400 to-purple-500'
  },
  { 
    value: 'active_sport' as const, 
    emoji: '🏃', 
    name: 'Aktywny sportowo',
    description: 'Trasy, obiekty sportowe, zieleń',
    color: 'from-orange-400 to-amber-500'
  },
  { 
    value: 'car_first' as const, 
    emoji: '🚗', 
    name: 'Pod auto / przedmieścia',
    description: 'Dojazd samochodem, spokój',
    color: 'from-slate-400 to-gray-500'
  },
  { 
    value: 'custom' as const, 
    emoji: '🎛️', 
    name: 'Skompunuj sam',
    description: 'Pełna kontrola nad parametrami',
    color: 'from-pink-400 to-rose-500'
  },
]

// Category configuration - labels and defaults per profile (from profiles.py)
const categoryMeta: Record<string, { label: string; emoji: string; min: number; max: number }> = {
  shops: { label: 'Sklepy', emoji: '🛒', min: 300, max: 1500 },
  transport: { label: 'Transport', emoji: '🚌', min: 300, max: 1500 },
  education: { label: 'Edukacja', emoji: '🎓', min: 500, max: 2500 },
  health: { label: 'Zdrowie', emoji: '🏥', min: 500, max: 3000 },
  nature_place: { label: 'Parki', emoji: '🌳', min: 400, max: 2000 },
  nature_background: { label: 'Zieleń', emoji: '🌿', min: 200, max: 800 },
  leisure: { label: 'Rozrywka', emoji: '🎭', min: 400, max: 1800 },
  food: { label: 'Gastronomia', emoji: '🍕', min: 400, max: 1500 },
  finance: { label: 'Finanse', emoji: '🏦', min: 400, max: 1500 },
}

// Default radius per profile (matching profiles.py)
const profileDefaults: Record<string, Record<string, number>> = {
  urban: {
    transport: 700, food: 800, shops: 600, leisure: 800, health: 1200,
    finance: 800, nature_place: 900, nature_background: 450, education: 900,
  },
  family: {
    education: 1200, health: 1500, nature_place: 900, shops: 700, transport: 900,
    leisure: 700, nature_background: 450, food: 700, finance: 900,
  },
  quiet_green: {
    nature_place: 1200, nature_background: 500, shops: 900, transport: 1200,
    health: 2000, leisure: 1200, food: 1200, education: 1500, finance: 1000,
  },
  remote_work: {
    shops: 700, health: 1500, nature_background: 450, nature_place: 900,
    transport: 1000, food: 900, leisure: 900, education: 1200, finance: 800,
  },
  active_sport: {
    leisure: 1200, nature_place: 1200, nature_background: 500, shops: 800,
    transport: 1000, health: 1800, food: 900, finance: 1000, education: 1500,
  },
  car_first: {
    shops: 1200, health: 2500, education: 2000, transport: 1500, nature_place: 1500,
    nature_background: 600, leisure: 1500, food: 1200, finance: 1200,
  },
  custom: {
    // Neutralne wartości środkowe dla profilu własnego
    shops: 800, transport: 900, education: 1200, health: 1500, nature_place: 1000,
    nature_background: 450, leisure: 900, food: 800, finance: 800,
  },
}

// User's custom radius overrides (reactive)
const radiusOverrides = ref<Record<string, number>>({})
// Track which sliders have been unlocked by the user (for predefined profiles)
const unlockedSliders = ref<Set<string>>(new Set())
const showProfileSettings = ref(false)

// Hover state for profile tooltips
const hoveredProfile = ref<string | null>(null)

// Calculate progress bar percentage for a radius value
function getRadiusPercent(category: string, radiusValue: number): number {
  const meta = categoryMeta[category]
  if (!meta) return 50
  const range = meta.max - meta.min
  const percent = ((radiusValue - meta.min) / range) * 100
  return Math.max(0, Math.min(100, percent))
}

// Get selected profile object
const selectedProfile = computed(() => {
  return profileOptions.find(p => p.value === profileKey.value) || null
})

// Computed: current defaults for selected profile
const currentProfileDefaults = computed(() => profileDefaults[profileKey.value] || profileDefaults.family)

// Check if a slider is locked (predefined profile + not unlocked)
function isSliderLocked(category: string): boolean {
  if (profileKey.value === 'custom') return false
  return !unlockedSliders.value.has(category)
}

// Toggle slider lock state
function toggleSliderLock(category: string): void {
  if (unlockedSliders.value.has(category)) {
    unlockedSliders.value.delete(category)
    // Reset this override when re-locking
    delete radiusOverrides.value[category]
  } else {
    unlockedSliders.value.add(category)
  }
}

// Get effective radius for a category (user override or profile default)
function getEffectiveRadius(category: string): number {
  const defaults = currentProfileDefaults.value
  const profileDefault = defaults ? defaults[category] : undefined
  const familyDefault = profileDefaults.family?.[category] ?? 1000
  return radiusOverrides.value[category] ?? profileDefault ?? familyDefault
}

// Update radius override
function setRadiusOverride(category: string, value: number) {
  radiusOverrides.value[category] = value
}

// Reset all overrides to defaults
function resetRadiusOverrides() {
  radiusOverrides.value = {}
  unlockedSliders.value = new Set()
}

// Watch profile changes - reset overrides and unlocked sliders
watch(profileKey, () => {
  radiusOverrides.value = {}
  unlockedSliders.value = new Set()
  showProfileSettings.value = false
})

// FAQ Data - same format as HomePage
const accordions = ref([
  {
    title: 'Jak działa analiza lokalizacji?',
    description: 'Wskazujesz punkt na mapie, a my analizujemy okolice w promieniu 500-1000m. Sprawdzamy hałas, dostęp do komunikacji, zieleni, sklepów i innych udogodnień używając danych z OpenStreetMap.',
  },
  {
    title: 'Czy cena za m² jest porównywana z rynkiem?',
    description: 'Tak, porównujemy podaną cenę ze średnią dla danej dzielnicy. Otrzymujesz informację czy mieszkanie jest tanie, w normie, czy przepłacone - z konkretnym werdyktem.',
  },
  {
    title: 'Skąd pochodzą dane analizy?',
    description: 'Dane pochodzą z OpenStreetMap i są aktualizowane regularnie. Analizujemy POI (punkty zainteresowania), drogi, zieleń, komunikację miejską i potencjalne źródła hałasu.',
  },
  {
    title: 'Czy analiza jest płatna?',
    description: 'Tak, pełny raport kosztuje 9.99 zł. W tej cenie otrzymujesz kompleksową analizę, która może uchronić Cię przed nietrafioną inwestycją za kilkaset tysięcy złotych.',
  },
])

// Steps data
const steps = ref([
  {
    icon: mdiMapMarker,
    title: 'Wskaż lokalizację',
    description: 'Wpisz adres i podstawowe parametry mieszkania',
    color: 'from-emerald-400 to-emerald-600',
  },
  {
    icon: mdiCash,
    title: 'Opłać raport (9.99zł)',
    description: 'Szybka i bezpieczna płatność BLIKiem lub kartą',
    color: 'from-blue-400 to-blue-600',
  },
  {
    icon: mdiChartBar,
    title: 'Pobierz analizę',
    description: 'Otrzymaj kompleksowy raport PDF z werdyktem eksperckim',
    color: 'from-purple-400 to-purple-600',
  },
])

// Features data
const features = ref([
  {
    icon: mdiAlertCircle,
    title: 'Analiza Ryzyka',
    description: 'Profesjonalna identyfikacja zagrożeń: hałas, smog, patodeweloperka',
    color: 'from-red-400 to-rose-500',
  },
  {
    icon: mdiChartBar,
    title: 'Weryfikacja Ceny',
    description: 'Algorytmiczne porównanie z cenami transakcyjnymi w tej okolicy',
    color: 'from-blue-400 to-indigo-500',
  },
  {
    icon: mdiShieldCheck,
    title: 'Rekomendacja',
    description: 'Jasny werdykt inwestycyjny: KUPUJ / NEGOCJUJ / ODPUŚĆ',
    color: 'from-emerald-400 to-teal-500',
  },
  {
    icon: mdiTreeOutline,
    title: 'Potencjał',
    description: 'Ocena perspektyw wzrostu wartości w oparciu o planowane inwestycje',
    color: 'from-green-400 to-lime-500',
  },
  {
    icon: mdiVolumeHigh,
    title: 'Mapa Akustyczna',
    description: 'Precyzyjna analiza źródeł hałasu: drogi, tory, korytarze powietrzne',
    color: 'from-orange-400 to-amber-500',
  },
  {
    icon: mdiHomeCityOutline,
    title: 'Komfort Życia',
    description: 'Analiza "15-minute city" - dostępność usług i wygoda na co dzień',
    color: 'from-violet-400 to-purple-500',
  },
])

// Computed
const canSubmit = computed(() => {
  // Tylko lokalizacja jest wymagana - cena i metraż są opcjonalne
  return selectedLocation.value !== null && !isLoading.value
})

const pricePerSqm = computed(() => {
  if (price.value && areaSqm.value && areaSqm.value > 0) {
    return Math.round(price.value / areaSqm.value)
  }
  return null
})

// Methods
function handleLocationSelected(data: { lat: number; lng: number; address: string }) {
  selectedLocation.value = data
}

function clearLocation() {
  selectedLocation.value = null
}

async function handleAnalyze() {
  if (!canSubmit.value || !selectedLocation.value) return
  
  isLoading.value = true
  loadingStatus.value = 'Inicjalizacja...'
  loadingProgress.value = 10
  errorMessage.value = ''
  
  try {
    const report = await analyzerApi.analyzeLocationStream(
      selectedLocation.value.lat,
      selectedLocation.value.lng,
      price.value ?? null,  // Opcjonalne - przekazuj null jeśli nie podano
      areaSqm.value ?? null,  // Opcjonalne - przekazuj null jeśli nie podano
      selectedLocation.value.address,
      radius.value,
      referenceUrl.value || undefined,
      (event) => {
        if (event.message) {
          loadingStatus.value = event.message
          const step = loadingSteps.find(s => {
            const prefix = s.status.split('...')[0]
            return prefix && event.message?.includes(prefix)
          })
          if (step) loadingProgress.value = step.progress
          else loadingProgress.value = Math.min(loadingProgress.value + 10, 95)
        }
      },
      profileKey.value,  // Nowy system profili
      poiProvider.value,
      Object.keys(radiusOverrides.value).length > 0 ? radiusOverrides.value : undefined  // User overrides
    )
    
    loadingProgress.value = 100
    
    if (!report) {
      throw new Error('Brak raportu w odpowiedzi')
    }
    
    sessionStorage.setItem('lastReport', JSON.stringify(report))
    sessionStorage.setItem('lastReportUrl', referenceUrl.value || selectedLocation.value.address)
    
    router.push({
      name: 'report',
      query: { fromAnalysis: 'true' },
    })
    
  } catch (error) {
    errorMessage.value = getErrorMessage(error)
  } finally {
    isLoading.value = false
    loadingStatus.value = ''
    loadingProgress.value = 0
  }
}

async function loadRecentAnalyses() {
  isLoadingRecent.value = true
  try {
    recentAnalyses.value = await analyzerApi.getRecentHistory()
  } catch (error) {
    console.warn('Nie udało się pobrać historii:', error)
  } finally {
    isLoadingRecent.value = false
  }
}

function openHistoryItem(item: HistoryItem) {
  router.push({ name: 'history-detail', params: { id: item.id } })
}

function formatPrice(priceValue: number | null): string {
  if (!priceValue) return '-'
  return new Intl.NumberFormat('pl-PL', {
    style: 'currency',
    currency: 'PLN',
    maximumFractionDigits: 0,
  }).format(priceValue)
}

function formatDate(date: string): string {
  return new Date(date).toLocaleDateString('pl-PL', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
  })
}

function getScoreColor(score: number | null): string {
  if (score === null) return 'bg-gray-400'
  if (score >= 70) return 'bg-emerald-500'
  if (score >= 50) return 'bg-amber-500'
  if (score >= 30) return 'bg-orange-500'
  return 'bg-red-500'
}

const scrollToAnalyze = () => {
  document.getElementById('analyze')?.scrollIntoView({ behavior: 'smooth' })
}

const scrollToHowItWorks = () => {
  document.getElementById('how-it-works')?.scrollIntoView({ behavior: 'smooth' })
}

const scrollToTop = () => {
  window.scrollTo({ top: 0, behavior: 'smooth' })
}

// Walking time helper for tooltips
function getWalkingTimeLabel(distanceM: number): string {
  const minutes = Math.round(distanceM / 80); // ~80m per minute walking (4.8km/h)
  if (minutes < 60) return `${minutes} min pieszo`;
  const hours = Math.floor(minutes / 60);
  const mins = minutes % 60;
  return `${hours}h ${mins}min`;
}

// Restore preferences from sessionStorage (when returning from report edit)
function restorePreferencesFromSession() {
  const editData = sessionStorage.getItem('editPreferencesData');
  if (editData) {
    try {
      const params = JSON.parse(editData);
      if (params.lat && params.lng) {
        selectedLocation.value = { 
          lat: params.lat, 
          lng: params.lng, 
          address: params.address || '' 
        };
      }
      if (params.price) price.value = params.price;
      if (params.areaSqm) areaSqm.value = params.areaSqm;
      if (params.profileKey) profileKey.value = params.profileKey;
      if (params.radiusOverrides && Object.keys(params.radiusOverrides).length > 0) {
        radiusOverrides.value = params.radiusOverrides;
        // Unlock all sliders that have overrides
        for (const cat of Object.keys(params.radiusOverrides)) {
          unlockedSliders.value.add(cat);
        }
        showProfileSettings.value = true; // Show sliders if there were overrides
      }
      sessionStorage.removeItem('editPreferencesData');
      // Scroll to analyze section after restoring
      setTimeout(() => scrollToAnalyze(), 100);
    } catch (e) {
      console.warn('Failed to restore preferences from session:', e);
    }
  }
}

// Load recent on mount and restore preferences if coming from report
onMounted(() => {
  restorePreferencesFromSession();
  loadRecentAnalyses();
});
</script>

<template>
  <div class="w-full">
    <!-- Hero section -->
    <section id="hero" class="w-full pb-24 bg-gradient-to-br from-white via-blue-50/40 to-cyan-50/30">
      <BaseSection>
        <div class="col-span-12 lg:col-span-6 mt-12 xl:mt-10 space-y-4 sm:space-y-6 px-6 text-center sm:text-left">
          <span data-aos="fade-right" class="text-base text-gradient font-semibold uppercase">
            Profesjonalny Raport Lokalizacji
          </span>
          <h1
            data-aos="fade-right"
            data-aos-delay="150"
            class="text-[2.5rem] sm:text-5xl xl:text-6xl font-bold leading-tight capitalize sm:pr-8 xl:pr-10"
          >
            Sprawdź <span class="text-header-gradient">ryzyko zakupu</span> zanim wydasz miliony
          </h1>
          <p data-aos="fade-down" data-aos-delay="250" class="paragraph hidden sm:block">
            Inwestycja 9.99 zł w raport, który może uratować Cię przed życiowym błędem. Analiza hałasu, bezpieczeństwa i potencjału inwestycyjnego w 30 sekund.
          </p>
          <div data-aos="fade-up" data-aos-delay="350" class="flex flex-col sm:flex-row space-y-4 sm:space-y-0 sm:space-x-4 mt-2">
            <BaseButton
              @click="scrollToAnalyze"
              class="max-w-full px-8 py-4 bg-gradient-to-r from-[#468ef9] to-[#0c66ee] border border-[#0c66ee] text-white font-semibold shadow-lg hover:shadow-xl hover:scale-105 transition-all"
            >
              Zamów raport (9.99 zł)
            </BaseButton>
            <BaseButton
              class="max-w-full px-6 py-4 bg-inherit text-gradient border border-[#0c66ee] flex items-center justify-center"
              @click="scrollToHowItWorks"
            >
              <span>Jak to działa?</span>
              <MdiIcon :path="mdiChevronDown" :size="20" class="mt-1 text-[#0c66ee]" />
            </BaseButton>
          </div>
        </div>
        <div data-aos="fade-up" class="hidden sm:block col-span-12 lg:col-span-6 mt-12 xl:mt-10">
          <div class="w-full relative">
            <!-- Custom illustration instead of hero image -->
            <div class="relative w-full max-w-lg mx-auto">
              <!-- Decorative circles -->
              <div class="absolute -top-8 -left-8 w-32 h-32 bg-cyan-200 rounded-full blur-2xl opacity-60"></div>
              <div class="absolute -bottom-8 -right-8 w-40 h-40 bg-blue-200 rounded-full blur-2xl opacity-60"></div>
              
              <!-- Main card -->
              <div class="relative bg-white rounded-3xl p-8 shadow-2xl border border-slate-100">
                <div class="grid grid-cols-3 gap-6 mb-6">
                  <div class="flex flex-col items-center gap-2">
                    <div class="w-16 h-16 rounded-2xl bg-gradient-to-br from-emerald-400 to-emerald-600 flex items-center justify-center shadow-lg">
                      <MdiIcon :path="mdiMapMarker" :size="28" class="text-white" />
                    </div>
                    <span class="text-xs text-slate-500 font-medium">Lokalizacja</span>
                  </div>
                  <div class="flex flex-col items-center gap-2">
                    <div class="w-16 h-16 rounded-2xl bg-gradient-to-br from-blue-400 to-blue-600 flex items-center justify-center shadow-lg">
                      <MdiIcon :path="mdiChartBar" :size="28" class="text-white" />
                    </div>
                    <span class="text-xs text-slate-500 font-medium">Analiza</span>
                  </div>
                  <div class="flex flex-col items-center gap-2">
                    <div class="w-16 h-16 rounded-2xl bg-gradient-to-br from-purple-400 to-purple-600 flex items-center justify-center shadow-lg">
                      <MdiIcon :path="mdiShieldCheck" :size="28" class="text-white" />
                    </div>
                    <span class="text-xs text-slate-500 font-medium">Werdykt</span>
                  </div>
                </div>
                
                <div class="p-4 bg-gradient-to-r from-emerald-50 to-teal-50 rounded-xl border border-emerald-100">
                  <div class="flex items-center gap-4">
                    <div class="w-14 h-14 rounded-full bg-gradient-to-br from-emerald-400 to-teal-500 flex items-center justify-center text-white font-bold text-xl shadow-lg">
                      78
                    </div>
                    <div>
                      <p class="font-semibold text-slate-800">Wynik analizy</p>
                      <p class="text-sm text-emerald-600 flex items-center gap-1">
                        <MdiIcon :path="mdiCheckCircle" :size="16" />
                        Dobra lokalizacja
                      </p>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </BaseSection>
    </section>

    <!-- Quick stats section -->
    <section
      class="max-w-screen-xl mx-2 sm:mx-auto px-6 sm:px-10 lg:px-12 py-10 sm:py-12 rounded-[2.25rem] sm:rounded-xl bg-white shadow-xl border border-gray-100/80 overflow-hidden transform lg:-translate-y-12"
    >
      <div class="w-full flex flex-col lg:flex-row items-center justify-center gap-10 lg:gap-20">
        <div data-aos="fade-up" class="text-center px-4 py-3">
          <p class="text-4xl font-bold text-header-gradient">500m</p>
          <p class="text-sm text-gray-600 mt-2">Promień analizy</p>
        </div>
        <div data-aos="fade-up" data-aos-delay="100" class="text-center px-4 py-3">
          <p class="text-4xl font-bold text-header-gradient">20+</p>
          <p class="text-sm text-gray-600 mt-2">Kategorii POI</p>
        </div>
        <div data-aos="fade-up" data-aos-delay="200" class="text-center px-4 py-3">
          <p class="text-4xl font-bold text-header-gradient">&lt;5s</p>
          <p class="text-sm text-gray-600 mt-2">Czas analizy</p>
        </div>
        <div data-aos="fade-up" data-aos-delay="300" class="text-center px-4 py-3">
          <p class="text-4xl font-bold text-header-gradient">100%</p>
          <p class="text-sm text-gray-600 mt-2">Obiektywności</p>
        </div>
      </div>
    </section>

    <!-- Main Analysis Form Section -->
    <section id="analyze" class="w-full my-24 py-16 bg-white">
      <BaseSection>
        <div class="col-span-12">
          <div class="text-center mb-10">
            <span data-aos="fade-up" class="text-base text-gradient font-semibold uppercase">Analiza lokalizacji</span>
            <h2 data-aos="fade-up" data-aos-delay="100" class="text-3xl sm:text-4xl font-semibold mt-2">
              Sprawdź swoją <span class="text-header-gradient">lokalizację</span>
            </h2>
          </div>
          
          <div data-aos="fade-up" data-aos-delay="200" class="max-w-4xl mx-auto bg-white rounded-2xl shadow-2xl p-6 md:p-8 border border-gray-200/60 ring-1 ring-gray-100">
            <!-- Error Message -->
            <div v-if="errorMessage" class="mb-6 p-4 bg-red-50 border border-red-200 rounded-xl text-red-700">
              <div class="flex items-center gap-2">
                <MdiIcon :path="mdiAlertCircle" :size="20" />
                <span>{{ errorMessage }}</span>
              </div>
            </div>
            
            <!-- Step 1: Location -->
            <div class="mb-6">
              <div class="flex items-center gap-3 mb-4">
                <span class="inline-flex items-center justify-center w-10 h-10 rounded-full bg-blue-gradient text-white font-bold shadow-md">1</span>
                <h3 class="font-semibold text-lg text-neutral-800">Wskaż lokalizację</h3>
                <span class="text-red-500 text-sm">*wymagane</span>
              </div>
              
              <div v-if="selectedLocation" class="bg-emerald-50 border border-emerald-200 rounded-xl p-4">
                <div class="flex items-center justify-between">
                  <div class="flex items-center gap-3">
                    <div class="w-12 h-12 rounded-full bg-gradient-to-br from-emerald-400 to-emerald-600 flex items-center justify-center shadow-md">
                      <MdiIcon :path="mdiCheckCircle" :size="24" class="text-white" />
                    </div>
                    <div>
                      <p class="font-medium text-neutral-800">{{ selectedLocation.address }}</p>
                      <p class="text-sm text-gray-500">{{ selectedLocation.lat.toFixed(5) }}, {{ selectedLocation.lng.toFixed(5) }}</p>
                    </div>
                  </div>
                  <button 
                    @click="clearLocation"
                    class="px-4 py-2 text-sm text-gray-500 hover:text-red-500 hover:bg-red-50 rounded-lg transition-colors"
                  >
                    Zmień
                  </button>
                </div>
              </div>
              
              <div v-else class="border-2 border-dashed border-gray-200 rounded-xl p-4 hover:border-blue-300 transition-colors">
                <LocationPicker
                  @location-selected="handleLocationSelected"
                  :show-cancel="false"
                />
              </div>
            </div>
            
            <!-- Step 2 & 3: Price & Area (Opcjonalne) -->
            <div class="mb-6">
              <div class="flex items-center gap-3 mb-2">
                <span class="inline-flex items-center justify-center w-10 h-10 rounded-full bg-gradient-to-r from-slate-400 to-gray-500 text-white font-bold shadow-md">2</span>
                <div>
                  <h3 class="font-semibold text-lg text-neutral-800">Znane dane nieruchomości</h3>
                  <p class="text-sm text-gray-500">Opcjonalne - wzbogacą raport o kontekst cenowy</p>
                </div>
              </div>
              
              <div class="grid grid-cols-1 md:grid-cols-2 gap-4 mt-4">
                <div>
                  <label class="block text-sm font-medium text-gray-600 mb-2">Cena</label>
                  <div class="relative">
                    <input 
                      v-model.number="price"
                      type="number"
                      placeholder="np. 650000"
                      min="0"
                      max="50000000"
                      class="w-full py-3 px-4 pr-16 text-base rounded-xl border-2 border-gray-200 focus:border-[#0c66ee] focus:ring-2 focus:ring-[#0c66ee]/20 outline-none transition-all"
                      :disabled="isLoading"
                    />
                    <span class="absolute right-4 top-1/2 -translate-y-1/2 text-gray-400 font-medium">PLN</span>
                  </div>
                </div>
                
                <div>
                  <label class="block text-sm font-medium text-gray-600 mb-2">Metraż</label>
                  <div class="relative">
                    <input 
                      v-model.number="areaSqm"
                      type="number"
                      placeholder="np. 54"
                      min="1"
                      max="1000"
                      step="0.1"
                      class="w-full py-3 px-4 pr-12 text-base rounded-xl border-2 border-gray-200 focus:border-[#0c66ee] focus:ring-2 focus:ring-[#0c66ee]/20 outline-none transition-all"
                      :disabled="isLoading"
                    />
                    <span class="absolute right-4 top-1/2 -translate-y-1/2 text-gray-400 font-medium">m²</span>
                  </div>
                </div>
              </div>
            </div>
            
            <!-- Price per sqm display -->
            <div v-if="pricePerSqm" class="mb-6 bg-gradient-to-r from-blue-50 to-cyan-50 rounded-xl p-4 border border-blue-100">
              <div class="flex items-center justify-center gap-3">
                <MdiIcon :path="mdiCash" :size="24" class="text-[#0c66ee]" />
                <span class="text-gray-600">Cena za m²:</span>
                <span class="font-bold text-xl text-header-gradient">{{ formatPrice(pricePerSqm) }}/m²</span>
              </div>
            </div>
            
            <!-- Profile Selector -->
            <div class="mb-6">
              <div class="flex items-center gap-3 mb-4">
                <span class="inline-flex items-center justify-center w-10 h-10 rounded-full bg-gradient-to-r from-purple-400 to-violet-500 text-white font-bold shadow-md">3</span>
                <h3 class="font-semibold text-lg text-neutral-800">Twój profil</h3>
              </div>
              
              <div class="grid grid-cols-2 md:grid-cols-3 gap-3">
                <div
                  v-for="profile in profileOptions"
                  :key="profile.value"
                  class="relative"
                  @mouseenter="hoveredProfile = profile.value"
                  @mouseleave="hoveredProfile = null"
                >
                  <button
                    @click="profileKey = profile.value"
                    :class="[
                      'w-full p-4 rounded-xl border-2 transition-all duration-300 text-left group cursor-pointer',
                      profileKey === profile.value 
                        ? 'border-[#0c66ee] bg-blue-50 shadow-md' 
                        : 'border-gray-200 bg-white hover:border-blue-200 hover:shadow-md hover:bg-blue-50/30'
                    ]"
                    :disabled="isLoading"
                  >
                    <div class="flex items-start gap-3">
                      <div 
                        class="w-12 h-12 rounded-xl flex items-center justify-center text-2xl shadow-sm"
                        :class="profileKey === profile.value ? `bg-gradient-to-br ${profile.color} text-white` : 'bg-gray-100'"
                      >
                        {{ profile.emoji }}
                      </div>
                      <div class="flex-1 min-w-0">
                        <p class="font-semibold text-sm" :class="profileKey === profile.value ? 'text-[#0c66ee]' : 'text-neutral-800'">
                          {{ profile.name }}
                        </p>
                        <p class="text-xs text-gray-500 mt-0.5 leading-tight">{{ profile.description }}</p>
                      </div>
                    </div>
                    
                    <!-- Selected indicator -->
                    <div 
                      v-if="profileKey === profile.value"
                      class="absolute top-2 right-2 w-5 h-5 rounded-full bg-[#0c66ee] flex items-center justify-center"
                    >
                      <MdiIcon :path="mdiCheckCircle" :size="14" class="text-white" />
                    </div>
                  </button>
                  
                  <!-- Profile Hover Tooltip with Category Progress Bars -->
                  <Transition name="fade">
                    <div 
                      v-if="hoveredProfile === profile.value && profile.value !== 'custom' && profileDefaults[profile.value]"
                      class="absolute left-1/2 -translate-x-1/2 bottom-full mb-2 z-50 w-72 p-4 bg-white rounded-xl shadow-2xl border border-gray-200 pointer-events-none"
                    >
                      <div class="flex items-center gap-2 mb-3">
                        <span class="text-lg">{{ profile.emoji }}</span>
                        <h4 class="font-semibold text-sm text-gray-800">{{ profile.name }} - zasięgi</h4>
                      </div>
                      <div class="space-y-2">
                        <div 
                          v-for="(radius, cat) in profileDefaults[profile.value]" 
                          :key="cat"
                          class="text-xs"
                        >
                          <div class="flex justify-between text-gray-600 mb-0.5">
                            <span>{{ categoryMeta[cat]?.emoji }} {{ categoryMeta[cat]?.label }}</span>
                            <span class="font-mono text-gray-500">{{ radius }}m</span>
                          </div>
                          <div class="h-1.5 bg-gray-200 rounded-full overflow-hidden">
                            <div 
                              class="h-full rounded-full transition-all"
                              :class="`bg-gradient-to-r ${profile.color}`"
                              :style="{ width: getRadiusPercent(cat as string, radius) + '%' }"
                            />
                          </div>
                        </div>
                      </div>
                      <!-- Arrow indicator -->
                      <div class="absolute left-1/2 -translate-x-1/2 -bottom-2 w-4 h-4 bg-white border-r border-b border-gray-200 rotate-45"></div>
                    </div>
                  </Transition>
                </div>
              </div>
            </div>
            
            <!-- Profile confirmation message -->
            <Transition name="fade">
              <div v-if="profileKey && profileKey !== 'custom' && selectedProfile" class="mb-4 p-3 bg-blue-50 rounded-xl border border-blue-100 flex items-center gap-3">
                <span class="text-blue-500">✓</span>
                <span class="text-sm text-blue-700">
                  Profil <strong>{{ selectedProfile.name }}</strong> ustawił domyślne zasięgi. 
                  <button @click="showProfileSettings = true" class="underline hover:no-underline">Możesz je zmienić.</button>
                </span>
              </div>
            </Transition>
            
            <!-- Profile Settings (Category Radius Sliders) -->
            <div v-if="profileKey" class="mb-6">
              <button 
                @click="showProfileSettings = !showProfileSettings"
                class="flex items-center gap-2 text-sm text-gray-500 hover:text-[#0c66ee] transition-colors"
              >
                <MdiIcon :path="mdiChevronDown" :size="18" :class="{ 'rotate-180': showProfileSettings }" class="transition-transform" />
                ⚙️ Ustawienia profilu
                <span v-if="Object.keys(radiusOverrides).length > 0" class="ml-2 px-2 py-0.5 text-xs bg-blue-100 text-blue-700 rounded-full">
                  {{ Object.keys(radiusOverrides).length }} zmian
                </span>
              </button>
              
              <Transition name="slide">
                <div v-if="showProfileSettings" class="mt-4 p-4 bg-gradient-to-br from-gray-50 to-slate-50 rounded-xl border border-gray-100">
                  <!-- Explanatory text about slider impact -->
                  <div class="mb-4 p-3 bg-amber-50 rounded-lg border border-amber-100 flex items-start gap-2">
                    <i class="pi pi-info-circle text-amber-500 mt-0.5"></i>
                    <p class="text-sm text-amber-700">
                      <strong>Te ustawienia wpływają bezpośrednio na końcową ocenę lokalizacji.</strong>
                      Im mniejszy zasięg, tym bardziej wymagająca ocena.
                    </p>
                  </div>
                  
                  <div class="flex items-center justify-between mb-4">
                    <p class="text-sm font-medium text-gray-600">Dostosuj zasięg wyszukiwania dla każdej kategorii:</p>
                    <button 
                      v-if="Object.keys(radiusOverrides).length > 0"
                      @click="resetRadiusOverrides"
                      class="text-xs text-gray-400 hover:text-red-500 transition-colors"
                    >
                      Resetuj do domyślnych
                    </button>
                  </div>
                  
                  <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                    <div 
                      v-for="(meta, category) in categoryMeta" 
                      :key="category"
                      :class="[
                        'rounded-lg p-3 border shadow-sm transition-all',
                        isSliderLocked(category) 
                          ? 'bg-gray-50 border-gray-200 opacity-80' 
                          : 'bg-white border-gray-100'
                      ]"
                    >
                      <div class="flex items-center justify-between mb-2">
                        <span class="text-sm font-medium text-gray-700">
                          {{ meta.emoji }} {{ meta.label }}
                        </span>
                        <div class="flex items-center gap-2">
                          <span 
                            class="text-xs font-mono text-blue-600 bg-blue-50 px-2 py-0.5 rounded"
                            :title="`${getEffectiveRadius(category)}m ≈ ${getWalkingTimeLabel(getEffectiveRadius(category))}`"
                          >
                            {{ getEffectiveRadius(category) }}m
                            <span class="text-gray-400 font-normal ml-1">({{ getWalkingTimeLabel(getEffectiveRadius(category)) }})</span>
                          </span>
                          <!-- Lock/Unlock button for predefined profiles -->
                          <button 
                            v-if="profileKey !== 'custom'"
                            @click="toggleSliderLock(category)"
                            :title="isSliderLocked(category) ? 'Kliknij aby odblokować' : 'Kliknij aby zablokować'"
                            class="p-1 rounded hover:bg-gray-100 transition-colors"
                          >
                            <MdiIcon 
                              :path="isSliderLocked(category) ? mdiLock : mdiLockOpen" 
                              :size="16" 
                              :class="isSliderLocked(category) ? 'text-gray-400' : 'text-green-500'"
                            />
                          </button>
                        </div>
                      </div>
                      <input 
                        type="range"
                        :min="meta.min"
                        :max="meta.max"
                        :step="50"
                        :value="getEffectiveRadius(category)"
                        @input="(e) => setRadiusOverride(category, parseInt((e.target as HTMLInputElement).value))"
                        :title="`${getEffectiveRadius(category)}m ≈ ${getWalkingTimeLabel(getEffectiveRadius(category))}`"
                        :class="[
                          'w-full h-2 rounded-lg appearance-none cursor-pointer',
                          isSliderLocked(category) 
                            ? 'bg-gray-300 accent-gray-400 cursor-not-allowed' 
                            : 'bg-gray-200 accent-blue-600'
                        ]"
                        :disabled="isLoading || isSliderLocked(category)"
                      />
                      <div class="flex justify-between text-xs text-gray-400 mt-1">
                        <span>{{ meta.min }}m</span>
                        <span>{{ meta.max }}m</span>
                      </div>
                    </div>
                  </div>
                </div>
              </Transition>
            </div>
            <!-- Advanced Options Toggle -->
            <div class="mb-6">
              <button 
                @click="showAdvanced = !showAdvanced"
                class="flex items-center gap-2 text-sm text-gray-500 hover:text-[#0c66ee] transition-colors"
              >
                <MdiIcon :path="mdiChevronDown" :size="18" :class="{ 'rotate-180': showAdvanced }" class="transition-transform" />
                Opcje zaawansowane
              </button>
              
              <Transition name="slide">
                <div v-if="showAdvanced" class="mt-4 p-4 bg-gray-50 rounded-xl space-y-4">
                  <div>
                    <label class="block text-sm font-medium text-gray-600 mb-2">
                      Link do ogłoszenia (opcjonalnie)
                    </label>
                    <input 
                      v-model="referenceUrl"
                      type="url"
                      placeholder="https://www.otodom.pl/pl/oferta/..."
                      class="w-full py-3 px-4 rounded-xl border-2 border-gray-200 focus:border-[#0c66ee] focus:ring-2 focus:ring-[#0c66ee]/20 outline-none transition-all"
                      :disabled="isLoading"
                    />
                    <p class="text-xs text-gray-400 mt-1">Zapisany jako referencja w raporcie</p>
                  </div>
                </div>
              </Transition>
            </div>
            
            <!-- Submit Button -->
            <div class="flex flex-col items-center justify-center">
              <BaseButton
                :disabled="!canSubmit"
                @click="handleAnalyze"
                class="w-full sm:w-auto px-12 py-4 bg-gradient-to-r from-[#468ef9] to-[#0c66ee] border border-[#0c66ee] text-white text-lg font-semibold disabled:opacity-50 disabled:cursor-not-allowed"
              >
                <span class="flex items-center justify-center gap-2">
                  <svg v-if="isLoading" class="animate-spin h-5 w-5" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                    <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                    <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                  </svg>
                  {{ isLoading ? 'Przetwarzanie...' : 'Generuj raport i zapłać (9.99 zł)' }}
                </span>
              </BaseButton>
              <p class="mt-4 text-xs text-center text-gray-400">
                <MdiIcon :path="mdiShieldCheck" :size="14" class="inline mr-1" />
                Bezpieczna płatność przez Stripe / BLIK. Gwarancja satysfakcji.
              </p>
            </div>

            <!-- Loading Status -->
            <Transition name="slide">
              <div v-if="isLoading" class="mt-6">
                <div class="bg-gradient-to-r from-blue-50 to-cyan-50 rounded-2xl p-6 border border-blue-100">
                  <div class="flex items-center gap-4 mb-4">
                    <div class="w-14 h-14 rounded-xl bg-blue-gradient flex items-center justify-center shadow-lg">
                      <svg class="animate-spin h-7 w-7 text-white" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                        <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                        <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                      </svg>
                    </div>
                    <div class="flex-1">
                      <p class="font-bold text-lg text-neutral-800">{{ loadingStatus }}</p>
                      <p class="text-sm text-gray-500">Proszę czekać...</p>
                    </div>
                    <span class="text-2xl font-bold text-header-gradient">{{ loadingProgress }}%</span>
                  </div>
                  
                  <div class="h-3 bg-white rounded-full shadow-inner">
                    <div 
                      class="h-full bg-blue-gradient rounded-full transition-all duration-500"
                      :style="{ width: `${loadingProgress}%` }"
                    ></div>
                  </div>
                </div>
              </div>
            </Transition>
          </div>
        </div>
      </BaseSection>
    </section>

    <!-- Features section -->
    <section id="how-it-works" class="bg-trading-tools relative max-w-full sm:mx-4 my-20 py-16 shadow-xl rounded-2xl">
      <div class="relative max-w-screen-xl px-4 sm:px-8 mx-auto">
        <div class="text-center mb-12">
          <h2 data-aos="flip-down" class="text-3xl sm:text-4xl font-semibold">
            Co <span class="text-header-gradient">sprawdzamy</span>?
          </h2>
          <p data-aos="flip-down" data-aos-delay="100" class="paragraph mt-4 max-w-2xl mx-auto">
            Kompleksowa analiza okolicy w oparciu o dane z OpenStreetMap
          </p>
        </div>
        
        <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          <div 
            v-for="(feature, index) in features" 
            :key="feature.title"
            data-aos="fade-up"
            :data-aos-delay="index * 100"
            class="group bg-white rounded-2xl p-6 shadow-lg hover:shadow-2xl transition-all duration-300 border border-gray-100 hover:-translate-y-2 hover:border-blue-100"
          >
            <div 
              class="w-14 h-14 rounded-xl flex items-center justify-center shadow-lg mb-4 group-hover:scale-110 transition-transform"
              :class="`bg-gradient-to-br ${feature.color}`"
            >
              <MdiIcon :path="feature.icon" :size="26" class="text-white" />
            </div>
            <h3 class="font-bold text-lg mb-2 text-neutral-800">{{ feature.title }}</h3>
            <p class="text-gray-600 text-sm leading-relaxed">{{ feature.description }}</p>
          </div>
        </div>
      </div>
    </section>

    <!-- Pricing Section (New) -->
    <section class="max-w-screen-xl mx-auto px-6 py-16">
        <div class="text-center mb-12">
            <h2 class="text-3xl sm:text-4xl font-semibold mb-4">
                Jeden raport, <span class="text-header-gradient">wszystkie odpowiedzi</span>
            </h2>
            <p class="paragraph max-w-2xl mx-auto">
                Nie kupuj kota w worku. Sprawdź, co naprawdę kryje się w okolicy Twojego przyszłego mieszkania.
            </p>
        </div>

        <div class="max-w-lg mx-auto bg-white rounded-3xl shadow-xl overflow-hidden border border-gray-100 transform hover:-translate-y-1 transition-transform duration-300">
            <div class="bg-gradient-to-br from-blue-600 to-indigo-700 p-8 text-white text-center relative overflow-hidden">
                <div class="absolute top-0 right-0 -mr-8 -mt-8 w-32 h-32 bg-white opacity-10 rounded-full blur-2xl"></div>
                <div class="absolute bottom-0 left-0 -ml-8 -mb-8 w-32 h-32 bg-white opacity-10 rounded-full blur-2xl"></div>
                
                <h3 class="text-2xl font-bold mb-2">Raport Premium</h3>
                <div class="flex items-center justify-center gap-1 my-4">
                    <span class="text-5xl font-bold">9.99</span>
                    <div class="text-left leading-tight opacity-90">
                        <div class="text-lg font-semibold">PLN</div>
                        <div class="text-xs">jednorazowo</div>
                    </div>
                </div>
                <p class="text-blue-100 text-sm">Cena filiżanki kawy za spokój ducha na lata</p>
            </div>
            
            <div class="p-8">
                <ul class="space-y-4">
                    <li class="flex items-start gap-3">
                        <div class="w-6 h-6 rounded-full bg-emerald-100 flex items-center justify-center flex-shrink-0 mt-0.5">
                            <MdiIcon :path="mdiCheckCircle" :size="16" class="text-emerald-600" />
                        </div>
                        <span class="text-gray-700"><strong>Analiza hałasu</strong> - drogi, tory, lotniska</span>
                    </li>
                    <li class="flex items-start gap-3">
                        <div class="w-6 h-6 rounded-full bg-emerald-100 flex items-center justify-center flex-shrink-0 mt-0.5">
                            <MdiIcon :path="mdiCheckCircle" :size="16" class="text-emerald-600" />
                        </div>
                        <span class="text-gray-700"><strong>Bezpieczeństwo</strong> - ocena ryzyka okolicy</span>
                    </li>
                    <li class="flex items-start gap-3">
                        <div class="w-6 h-6 rounded-full bg-emerald-100 flex items-center justify-center flex-shrink-0 mt-0.5">
                            <MdiIcon :path="mdiCheckCircle" :size="16" class="text-emerald-600" />
                        </div>
                        <span class="text-gray-700"><strong>Wycena</strong> - czy cena ofertowa jest uczciwa?</span>
                    </li>
                    <li class="flex items-start gap-3">
                        <div class="w-6 h-6 rounded-full bg-emerald-100 flex items-center justify-center flex-shrink-0 mt-0.5">
                            <MdiIcon :path="mdiCheckCircle" :size="16" class="text-emerald-600" />
                        </div>
                        <span class="text-gray-700"><strong>Infrastruktura</strong> - szkoły, sklepy, parki</span>
                    </li>
                    <li class="flex items-start gap-3">
                        <div class="w-6 h-6 rounded-full bg-emerald-100 flex items-center justify-center flex-shrink-0 mt-0.5">
                            <MdiIcon :path="mdiCheckCircle" :size="16" class="text-emerald-600" />
                        </div>
                        <span class="text-gray-700"><strong>Dostęp dożywotni</strong> do wygenerowanego raportu</span>
                    </li>
                </ul>
                
                <button 
                    @click="scrollToAnalyze"
                    class="w-full mt-8 py-4 rounded-xl bg-gray-900 text-white font-semibold hover:bg-gray-800 transition-colors shadow-lg"
                >
                    Zamów raport teraz
                </button>
                
                <p class="text-center text-xs text-gray-400 mt-4">
                    Gwarantujemy satysfakcję lub zwrot pieniędzy
                </p>
            </div>
        </div>
    </section>

    <!-- Getting started steps section -->
    <section class="bg-partner relative max-w-full sm:mx-6 my-24 shadow-xl sm:rounded-2xl">
      <div class="w-full px-6 sm:px-0 py-16 flex flex-col items-center justify-center space-y-8 text-center">
        <h2 data-aos="flip-down" class="text-3xl sm:text-4xl font-semibold text-neutral-800">
          Jak to działa?
        </h2>
        <p data-aos="flip-down" data-aos-delay="100" class="paragraph max-w-xl">
          Trzy proste kroki do pełnej analizy Twojej wymarzonej lokalizacji
        </p>
        
        <div class="flex flex-col lg:flex-row items-center justify-center gap-8 lg:gap-16 mt-8">
          <div 
            v-for="(step, index) in steps" 
            :key="step.title"
            data-aos="fade-up"
            :data-aos-delay="index * 150"
            class="max-w-[280px] space-y-4 text-center group"
          >
            <div 
              class="w-20 h-20 rounded-2xl mx-auto flex items-center justify-center shadow-xl group-hover:scale-110 group-hover:shadow-2xl transition-all duration-300"
              :class="`bg-gradient-to-br ${step.color}`"
            >
              <MdiIcon :path="step.icon" :size="36" class="text-white" />
            </div>
            <div class="flex items-center justify-center gap-2">
              <span class="inline-flex items-center justify-center w-8 h-8 rounded-full bg-blue-gradient text-white text-sm font-bold">{{ index + 1 }}</span>
              <h3 class="text-xl text-neutral-800 font-semibold">{{ step.title }}</h3>
            </div>
            <p class="text-sm text-gray-700 leading-relaxed">{{ step.description }}</p>
          </div>
        </div>
      </div>
    </section>

    <!-- Recent analyses section -->
    <section v-if="recentAnalyses.length > 0" class="w-full my-24">
      <BaseSection>
        <div data-aos="fade-up" class="col-span-12">
          <div class="max-w-4xl mx-auto bg-white rounded-2xl shadow-xl p-6 md:p-8 border border-gray-200/60">
            <div class="flex items-center gap-3 mb-6">
              <div class="w-12 h-12 rounded-xl bg-gradient-to-br from-violet-400 to-purple-500 flex items-center justify-center shadow-md">
                <MdiIcon :path="mdiChartBar" :size="24" class="text-white" />
              </div>
              <h2 class="text-xl font-bold text-neutral-800">Ostatnie analizy</h2>
            </div>
            
            <div class="space-y-3">
              <div 
                v-for="item in recentAnalyses.slice(0, 5)" 
                :key="item.id"
                @click="openHistoryItem(item)"
                class="group flex items-center gap-4 p-4 bg-gray-50 rounded-xl cursor-pointer hover:bg-blue-50/60 transition-all duration-200 hover:shadow-md hover:-translate-x-1"
              >
                <div 
                  class="w-12 h-12 rounded-xl flex items-center justify-center font-bold text-white shadow-md"
                  :class="getScoreColor(item.neighborhood_score)"
                >
                  {{ item.neighborhood_score !== null ? Math.round(item.neighborhood_score) : '?' }}
                </div>
                
                <div class="flex-1 min-w-0">
                  <p class="font-semibold text-neutral-800 truncate">
                    {{ item.title || item.location || 'Bez tytułu' }}
                  </p>
                  <div class="flex items-center gap-3 text-sm text-gray-500">
                    <span v-if="item.price">{{ formatPrice(item.price) }}</span>
                    <span v-if="item.area_sqm">{{ item.area_sqm }} m²</span>
                    <span v-if="item.rooms">{{ item.rooms }} pok.</span>
                  </div>
                </div>
                
                <div class="text-sm text-gray-400 hidden md:block">
                  {{ formatDate(item.created_at) }}
                </div>
                
                <MdiIcon :path="mdiChevronDown" :size="20" class="text-gray-300 group-hover:text-[#0c66ee] transition-colors -rotate-90" />
              </div>
            </div>
          </div>
        </div>
      </BaseSection>
    </section>

    <!-- FAQ section -->
    <section class="w-full my-24 py-16 bg-white">
      <BaseSection>
        <div data-aos="fade-right" class="col-span-12 lg:col-span-6">
          <div class="w-full">
            <img :src="faqImage" class="w-full" alt="FAQ" />
          </div>
        </div>
        <div data-aos="fade-left" class="col-span-12 lg:col-span-6 px-4 sm:px-6 mt-8">
          <span class="text-base text-gradient font-semibold uppercase mb-4 sm:mb-2">Pomoc</span>
          <h2 class="text-3xl sm:text-4xl font-semibold mb-10 sm:mb-6">Często zadawane pytania</h2>

          <ul class="shadow-box">
            <BaseAccordion v-for="(accordion, index) in accordions" :key="index" :accordion="accordion" />
          </ul>
        </div>
      </BaseSection>
    </section>

    <!-- Footer -->
    <footer class="w-full py-12 bg-white border-t border-gray-200">
      <div class="max-w-screen-xl mx-auto px-4 sm:px-8 text-center">
        <p class="font-bold text-2xl text-header-gradient mb-2">loktis.pl</p>
        <p class="text-sm text-gray-500 mb-6">Analiza ryzyka zakupu mieszkania</p>
        <p class="text-xs text-gray-400">Dane pochodzą z OpenStreetMap • Analiza ma charakter poglądowy</p>
      </div>
    </footer>

    <!-- Back to top button -->
    <div data-aos="flip-down" class="w-full my-10 flex justify-center">
      <button
        @click="scrollToTop"
        class="px-6 py-3 flex items-center space-x-2 bg-white hover:bg-blue-50 hover:shadow-lg hover:-translate-y-1 border border-gray-200 rounded-full text-gray-700 transition-all duration-300"
      >
        <span>Powrót na górę</span>
        <MdiIcon :path="mdiArrowUp" :size="20" />
      </button>
    </div>
  </div>
</template>

<style scoped>
.text-header-gradient {
  background: linear-gradient(169.4deg, #3984f4 -6.01%, #0cd3ff 36.87%, #2f7cf0 78.04%, #0e65e8 103.77%);
  -webkit-background-clip: text;
  background-clip: text;
  -webkit-text-fill-color: transparent;
}

/* Feature card icon glow on hover */
.group:hover .shadow-lg {
  filter: brightness(1.05);
}
</style>
