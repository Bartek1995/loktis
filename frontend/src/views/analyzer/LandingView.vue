<script setup lang="ts">
/**
 * Loktis - Landing View - strona główna z formularzem analizy lokalizacji
 * loktis.pl - Analiza ryzyka zakupu mieszkania
 * 
 * Redesigned with HomePage style + analyzer functionality
 */
import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import { analyzerApi, getErrorMessage, type HistoryItem } from '@/api/analyzerApi'
import LocationPicker from '@/components/LocationPicker.vue'
import MdiIcon from '@/components/icons/MdiIcon.vue'
import { mdiChevronDown, mdiArrowUp, mdiCheckCircle, mdiMapMarker, mdiChartBar, mdiShieldCheck, mdiAlertCircle, mdiHomeCityOutline, mdiTreeOutline, mdiVolumeHigh, mdiCash } from '@mdi/js'

// Base components
import BaseSection from '@/components/base/BaseSection.vue'
import BaseButton from '@/components/base/BaseButton.vue'
import BaseAccordion from '@/components/base/BaseAccordion.vue'

// Images
import faqImage from '@/assets/img/faq.webp'
import ellipse1 from '@/assets/img/pattern/ellipse-1.png'
import ellipse2 from '@/assets/img/pattern/ellipse-2.png'
import ellipse3 from '@/assets/img/pattern/ellipse-3.png'
import starPattern from '@/assets/img/pattern/star.png'

const router = useRouter()

// State - location first approach
const selectedLocation = ref<{ lat: number; lng: number; address: string } | null>(null)
const price = ref<number | null>(null)
const areaSqm = ref<number | null>(null)
const referenceUrl = ref('')
const radius = ref(500)
const userProfile = ref<'family' | 'urban' | 'investor'>('family')
const poiProvider = ref<'overpass' | 'google'>('overpass')

// UI State
const isLoading = ref(false)
const loadingStatus = ref('')
const loadingProgress = ref(0)
const recentAnalyses = ref<HistoryItem[]>([])
const isLoadingRecent = ref(false)
const showAdvanced = ref(false)
const errorMessage = ref('')

const radiusOptions = [
  { label: '500m', value: 500 },
  { label: '1000m', value: 1000 },
]

// Loading steps for progress animation
const loadingSteps = [
  { status: 'Inicjalizacja...', progress: 10 },
  { status: 'Pobieranie danych...', progress: 25 },
  { status: 'Analizowanie okolicy...', progress: 50 },
  { status: 'Przeliczanie dla profilu...', progress: 70 },
  { status: 'Sprawdzanie POI...', progress: 80 },
  { status: 'Generowanie raportu...', progress: 90 },
]

// Profile options
const profileOptions = [
  { 
    value: 'family' as const, 
    emoji: '👨‍👩‍👧', 
    name: 'Rodzina z dziećmi',
    description: 'Priorytet: szkoły, przedszkola, zieleń, cisza',
    color: 'from-emerald-400 to-teal-500'
  },
  { 
    value: 'urban' as const, 
    emoji: '🏙️', 
    name: 'Singiel / Para',
    description: 'Priorytet: transport, gastronomia, rozrywka',
    color: 'from-blue-400 to-indigo-500'
  },
  { 
    value: 'investor' as const, 
    emoji: '📈', 
    name: 'Inwestor',
    description: 'Priorytet: płynność najmu, ROI, lokalizacja',
    color: 'from-amber-400 to-orange-500'
  },
]

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
    title: 'Czy analiza jest darmowa?',
    description: 'Tak! Podstawowa analiza lokalizacji jest całkowicie bezpłatna. Wystarczy wskazać punkt na mapie, podać cenę i metraż, a otrzymasz pełny raport w kilka sekund.',
  },
])

// Steps data
const steps = ref([
  {
    icon: mdiMapMarker,
    title: 'Wskaż lokalizację',
    description: 'Użyj mapy lub wpisz adres interesującego Cię mieszkania',
    color: 'from-emerald-400 to-emerald-600',
  },
  {
    icon: mdiCash,
    title: 'Podaj cenę i metraż',
    description: 'Wpisz cenę ofertową i powierzchnię aby obliczyć cenę za m²',
    color: 'from-blue-400 to-blue-600',
  },
  {
    icon: mdiChartBar,
    title: 'Otrzymaj raport',
    description: 'Szczegółowa analiza okolicy z werdyktem zakupu w sekundy',
    color: 'from-purple-400 to-purple-600',
  },
])

// Features data
const features = ref([
  {
    icon: mdiAlertCircle,
    title: 'Czerwone Flagi',
    description: 'Wykrywamy ryzykowne czynniki: hałas, bliskość dróg, brak zieleni',
    color: 'from-red-400 to-rose-500',
  },
  {
    icon: mdiChartBar,
    title: 'Cena vs Rynek',
    description: 'Porównujemy Twoją cenę ze średnią dzielnicy: tanio / ok / drogo',
    color: 'from-blue-400 to-indigo-500',
  },
  {
    icon: mdiShieldCheck,
    title: 'Werdykt Zakupu',
    description: 'Jasna rekomendacja: POLECAM / UWAŻAJ / ODRADZAM z uzasadnieniem',
    color: 'from-emerald-400 to-teal-500',
  },
  {
    icon: mdiTreeOutline,
    title: 'Analiza POI',
    description: 'Sprawdzamy sklepy, szkoły, komunikację, zieleń i usługi w okolicy',
    color: 'from-green-400 to-lime-500',
  },
  {
    icon: mdiVolumeHigh,
    title: 'Ocena Hałasu',
    description: 'Wykrywamy bliskość ruchliwych dróg, linii kolejowych i lotnisk',
    color: 'from-orange-400 to-amber-500',
  },
  {
    icon: mdiHomeCityOutline,
    title: 'Infrastruktura',
    description: 'Oceniamy dostęp do komunikacji, parkingów i podstawowych usług',
    color: 'from-violet-400 to-purple-500',
  },
])

// Computed
const canSubmit = computed(() => {
  return selectedLocation.value !== null && price.value !== null && areaSqm.value !== null && !isLoading.value
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
  if (!canSubmit.value || !selectedLocation.value || price.value === null || areaSqm.value === null) return
  
  isLoading.value = true
  loadingStatus.value = 'Inicjalizacja...'
  loadingProgress.value = 10
  errorMessage.value = ''
  
  try {
    const report = await analyzerApi.analyzeLocationStream(
      selectedLocation.value.lat,
      selectedLocation.value.lng,
      price.value,
      areaSqm.value,
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
      userProfile.value,
      poiProvider.value
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

// Load recent on mount
loadRecentAnalyses()
</script>

<template>
  <div class="w-full">
    <!-- Hero section -->
    <section id="hero" class="w-full pb-24">
      <BaseSection>
        <div class="col-span-12 lg:col-span-6 mt-12 xl:mt-10 space-y-4 sm:space-y-6 px-6 text-center sm:text-left">
          <span data-aos="fade-right" class="text-base text-gradient font-semibold uppercase">
            Sprawdź przed zakupem
          </span>
          <h1
            data-aos="fade-right"
            data-aos-delay="150"
            class="text-[2.5rem] sm:text-5xl xl:text-6xl font-bold leading-tight capitalize sm:pr-8 xl:pr-10"
          >
            Analiza <span class="text-header-gradient">ryzyka zakupu</span> mieszkania
          </h1>
          <p data-aos="fade-down" data-aos-delay="250" class="paragraph hidden sm:block">
            Wskaż lokalizację na mapie, podaj cenę i metraż – otrzymasz szczegółowy raport z oceną okolicy, analizą ceny i werdyktem zakupowym w kilka sekund.
          </p>
          <div data-aos="fade-up" data-aos-delay="350" class="flex flex-col sm:flex-row space-y-4 sm:space-y-0 sm:space-x-4 mt-2">
            <BaseButton
              @click="scrollToAnalyze"
              class="max-w-full px-8 py-4 bg-gradient-to-r from-[#468ef9] to-[#0c66ee] border border-[#0c66ee] text-white"
            >
              Rozpocznij analizę
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
        <div data-aos="fade-up" class="hidden sm:block col-span-12 lg:col-span-6">
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
        <img :src="ellipse1" class="hidden sm:block absolute bottom-12 xl:bottom-16 left-4 xl:left-0 w-6" />
        <img :src="ellipse2" class="hidden sm:block absolute top-4 sm:top-10 right-64 sm:right-96 xl:right-[32rem] w-6" />
        <img :src="ellipse3" class="hidden sm:block absolute bottom-56 right-24 w-6" />
        <img :src="starPattern" class="hidden sm:block absolute top-20 sm:top-28 right-16 lg:right-0 lg:left-[30rem] w-8" />
      </BaseSection>
    </section>

    <!-- Quick stats section -->
    <section
      class="max-w-screen-xl mx-2 sm:mx-auto px-4 sm:px-6 lg:px-0 py-6 pb-20 sm:py-8 rounded-[2.25rem] sm:rounded-xl bg-white shadow-lg sm:shadow-md transform lg:-translate-y-12"
    >
      <div class="w-full flex flex-col lg:flex-row items-center justify-center gap-8 lg:gap-16">
        <div data-aos="fade-up" class="text-center">
          <p class="text-4xl font-bold text-header-gradient">500m</p>
          <p class="text-sm text-gray-600 mt-1">Promień analizy</p>
        </div>
        <div data-aos="fade-up" data-aos-delay="100" class="text-center">
          <p class="text-4xl font-bold text-header-gradient">20+</p>
          <p class="text-sm text-gray-600 mt-1">Kategorii POI</p>
        </div>
        <div data-aos="fade-up" data-aos-delay="200" class="text-center">
          <p class="text-4xl font-bold text-header-gradient">&lt;5s</p>
          <p class="text-sm text-gray-600 mt-1">Czas analizy</p>
        </div>
        <div data-aos="fade-up" data-aos-delay="300" class="text-center">
          <p class="text-4xl font-bold text-header-gradient">100%</p>
          <p class="text-sm text-gray-600 mt-1">Darmowe</p>
        </div>
      </div>
    </section>

    <!-- Main Analysis Form Section -->
    <section id="analyze" class="w-full my-24">
      <BaseSection>
        <div class="col-span-12">
          <div class="text-center mb-10">
            <span data-aos="fade-up" class="text-base text-gradient font-semibold uppercase">Analiza lokalizacji</span>
            <h2 data-aos="fade-up" data-aos-delay="100" class="text-3xl sm:text-4xl font-semibold mt-2">
              Sprawdź swoją <span class="text-header-gradient">lokalizację</span>
            </h2>
          </div>
          
          <div data-aos="fade-up" data-aos-delay="200" class="max-w-4xl mx-auto bg-white rounded-2xl shadow-xl p-6 md:p-8 border border-gray-100">
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
            
            <!-- Step 2 & 3: Price & Area -->
            <div class="grid grid-cols-1 md:grid-cols-2 gap-6 mb-6">
              <div>
                <div class="flex items-center gap-3 mb-4">
                  <span class="inline-flex items-center justify-center w-10 h-10 rounded-full bg-blue-gradient text-white font-bold shadow-md">2</span>
                  <h3 class="font-semibold text-lg text-neutral-800">Cena</h3>
                  <span class="text-red-500 text-sm">*</span>
                </div>
                <div class="relative">
                  <input 
                    v-model.number="price"
                    type="number"
                    placeholder="np. 650000"
                    min="0"
                    max="50000000"
                    class="w-full py-4 px-5 pr-16 text-lg rounded-xl border-2 border-gray-200 focus:border-[#0c66ee] focus:ring-2 focus:ring-[#0c66ee]/20 outline-none transition-all"
                    :disabled="isLoading"
                  />
                  <span class="absolute right-5 top-1/2 -translate-y-1/2 text-gray-400 font-medium">PLN</span>
                </div>
              </div>
              
              <div>
                <div class="flex items-center gap-3 mb-4">
                  <span class="inline-flex items-center justify-center w-10 h-10 rounded-full bg-blue-gradient text-white font-bold shadow-md">3</span>
                  <h3 class="font-semibold text-lg text-neutral-800">Metraż</h3>
                  <span class="text-red-500 text-sm">*</span>
                </div>
                <div class="relative">
                  <input 
                    v-model.number="areaSqm"
                    type="number"
                    placeholder="np. 54"
                    min="1"
                    max="1000"
                    step="0.1"
                    class="w-full py-4 px-5 pr-12 text-lg rounded-xl border-2 border-gray-200 focus:border-[#0c66ee] focus:ring-2 focus:ring-[#0c66ee]/20 outline-none transition-all"
                    :disabled="isLoading"
                  />
                  <span class="absolute right-5 top-1/2 -translate-y-1/2 text-gray-400 font-medium">m²</span>
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
                <span class="inline-flex items-center justify-center w-10 h-10 rounded-full bg-gradient-to-r from-purple-400 to-violet-500 text-white font-bold shadow-md">4</span>
                <h3 class="font-semibold text-lg text-neutral-800">Twój profil</h3>
              </div>
              
              <div class="grid grid-cols-1 md:grid-cols-3 gap-3">
                <button
                  v-for="profile in profileOptions"
                  :key="profile.value"
                  @click="userProfile = profile.value"
                  :class="[
                    'relative p-4 rounded-xl border-2 transition-all duration-200 text-left group',
                    userProfile === profile.value 
                      ? 'border-[#0c66ee] bg-blue-50 shadow-md' 
                      : 'border-gray-200 bg-white hover:border-gray-300 hover:shadow-sm'
                  ]"
                  :disabled="isLoading"
                >
                  <div class="flex items-start gap-3">
                    <div 
                      class="w-12 h-12 rounded-xl flex items-center justify-center text-2xl shadow-sm"
                      :class="userProfile === profile.value ? `bg-gradient-to-br ${profile.color} text-white` : 'bg-gray-100'"
                    >
                      {{ profile.emoji }}
                    </div>
                    <div class="flex-1 min-w-0">
                      <p class="font-semibold text-sm" :class="userProfile === profile.value ? 'text-[#0c66ee]' : 'text-neutral-800'">
                        {{ profile.name }}
                      </p>
                      <p class="text-xs text-gray-500 mt-0.5 leading-tight">{{ profile.description }}</p>
                    </div>
                  </div>
                  
                  <!-- Selected indicator -->
                  <div 
                    v-if="userProfile === profile.value"
                    class="absolute top-2 right-2 w-5 h-5 rounded-full bg-[#0c66ee] flex items-center justify-center"
                  >
                    <MdiIcon :path="mdiCheckCircle" :size="14" class="text-white" />
                  </div>
                </button>
              </div>
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
                  
                  <div class="flex items-center gap-4">
                    <span class="text-sm font-medium text-gray-600">Zasięg analizy:</span>
                    <div class="flex gap-2">
                      <button
                        v-for="option in radiusOptions"
                        :key="option.value"
                        @click="radius = option.value"
                        :class="[
                          'px-4 py-2 rounded-lg font-medium transition-all',
                          radius === option.value 
                            ? 'bg-blue-gradient text-white shadow-md' 
                            : 'bg-white text-gray-600 border border-gray-200 hover:border-[#0c66ee]'
                        ]"
                      >
                        {{ option.label }}
                      </button>
                    </div>
                  </div>
                  
                  <!-- POI Provider Toggle -->
                  <div class="flex items-center gap-4 pt-2 border-t border-gray-200">
                    <span class="text-sm font-medium text-gray-600">Źródło POI:</span>
                    <div class="flex gap-2">
                      <button
                        @click="poiProvider = 'overpass'"
                        :class="[
                          'px-4 py-2 rounded-lg font-medium transition-all flex items-center gap-2',
                          poiProvider === 'overpass' 
                            ? 'bg-green-500 text-white shadow-md' 
                            : 'bg-white text-gray-600 border border-gray-200 hover:border-green-500'
                        ]"
                      >
                        🗺️ OpenStreetMap
                      </button>
                      <button
                        @click="poiProvider = 'google'"
                        :class="[
                          'px-4 py-2 rounded-lg font-medium transition-all flex items-center gap-2',
                          poiProvider === 'google' 
                            ? 'bg-blue-500 text-white shadow-md' 
                            : 'bg-white text-gray-600 border border-gray-200 hover:border-blue-500'
                        ]"
                      >
                        🔵 Google Places
                      </button>
                    </div>
                  </div>
                </div>
              </Transition>
            </div>
            
            <!-- Submit Button -->
            <div class="flex justify-center">
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
                  {{ isLoading ? 'Analizuję...' : 'Analizuj lokalizację' }}
                </span>
              </BaseButton>
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
    <section id="how-it-works" class="bg-trading-tools relative max-w-full sm:mx-4 my-20 py-16 shadow rounded-2xl">
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
            class="group bg-white rounded-2xl p-6 shadow-lg hover:shadow-xl transition-all duration-300 border border-gray-100 hover:-translate-y-1"
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

    <!-- Getting started steps section -->
    <section class="bg-partner relative max-w-full sm:mx-6 my-24 shadow sm:rounded-2xl">
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
            class="max-w-[280px] space-y-4 text-center"
          >
            <div 
              class="w-20 h-20 rounded-2xl mx-auto flex items-center justify-center shadow-xl"
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
          <div class="max-w-4xl mx-auto bg-white rounded-2xl shadow-xl p-6 md:p-8 border border-gray-100">
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
                class="group flex items-center gap-4 p-4 bg-gray-50 rounded-xl cursor-pointer hover:bg-gray-100 transition-all hover:shadow-md"
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
    <section class="w-full my-24">
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
    <footer class="w-full py-12 border-t border-gray-200">
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
        class="px-6 py-3 flex items-center space-x-2 bg-[#FAFAFA] hover:bg-gray-100 hover:shadow-md border border-[#DDDDDD] rounded-full text-gray-700 transition-all"
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
</style>
