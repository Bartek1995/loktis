<script setup lang="ts">
/**
 * Loktis - Landing View - strona główna z formularzem analizy lokalizacji
 * loktis.pl - Analiza ryzyka zakupu mieszkania
 * 
 * NOWY MODEL: User wskazuje lokalizację + podaje cenę/metraż
 * Link do ogłoszenia jest OPCJONALNY (tylko referencja)
 * 
 * Redesigned with modern aesthetics, using STANDARD Tailwind colors only
 */
import { ref, computed } from 'vue';
import { useRouter } from 'vue-router';
import { useToast } from 'primevue/usetoast';
import { analyzerApi, getErrorMessage, type HistoryItem } from '@/api/analyzerApi';
import LocationPicker from '@/components/LocationPicker.vue';

const router = useRouter();
const toast = useToast();

// State - location first approach
const selectedLocation = ref<{ lat: number; lng: number; address: string } | null>(null);
const price = ref<number | null>(null);
const areaSqm = ref<number | null>(null);
const referenceUrl = ref('');
const radius = ref(500);

// UI State
const isLoading = ref(false);
const loadingStatus = ref('');
const loadingProgress = ref(0);
const recentAnalyses = ref<HistoryItem[]>([]);
const isLoadingRecent = ref(false);
const showAdvanced = ref(false);

const radiusOptions = [
  { label: '500m', value: 500 },
  { label: '1000m', value: 1000 },
];

// Loading steps for progress animation
const loadingSteps = [
  { status: 'Inicjalizacja...', progress: 10 },
  { status: 'Pobieranie danych...', progress: 25 },
  { status: 'Analizowanie okolicy...', progress: 50 },
  { status: 'Sprawdzanie POI...', progress: 75 },
  { status: 'Generowanie raportu...', progress: 90 },
];

// FAQ Data
const faqItems = ref([
  { title: 'Jak działa analiza lokalizacji?', description: 'Wskazujesz punkt na mapie, a my analizujemy okolice w promieniu 500-1000m. Sprawdzamy hałas, dostęp do komunikacji, zieleni, sklepów i innych udogodnień.', open: false },
  { title: 'Czy cena za m² jest porównywana z rynkiem?', description: 'Tak, porównujemy podaną cenę ze średnią dla danej dzielnicy. Otrzymujesz informację czy mieszkanie jest tanie, w normie, czy przepłacone.', open: false },
  { title: 'Skąd pochodzą dane?', description: 'Dane pochodzą z OpenStreetMap i są aktualizowane regularnie. Analiza ma charakter poglądowy i nie zastępuje profesjonalnej wyceny.', open: false },
]);

// Computed
const canSubmit = computed(() => {
  return selectedLocation.value !== null && price.value !== null && areaSqm.value !== null && !isLoading.value;
});

const pricePerSqm = computed(() => {
  if (price.value && areaSqm.value && areaSqm.value > 0) {
    return Math.round(price.value / areaSqm.value);
  }
  return null;
});

// Methods
function handleLocationSelected(data: { lat: number; lng: number; address: string }) {
  selectedLocation.value = data;
}

function clearLocation() {
  selectedLocation.value = null;
}

function toggleFaq(index: number) {
  faqItems.value[index].open = !faqItems.value[index].open;
}

async function handleAnalyze() {
  if (!canSubmit.value || !selectedLocation.value) return;
  
  isLoading.value = true;
  loadingStatus.value = 'Inicjalizacja...';
  loadingProgress.value = 10;
  
  try {
    const report = await analyzerApi.analyzeLocationStream(
      selectedLocation.value.lat,
      selectedLocation.value.lng,
      price.value!,
      areaSqm.value!,
      selectedLocation.value.address,
      radius.value,
      referenceUrl.value || undefined,
      (event) => {
        if (event.message) {
          loadingStatus.value = event.message;
          const step = loadingSteps.find(s => event.message?.includes(s.status.split('...')[0]));
          if (step) loadingProgress.value = step.progress;
          else loadingProgress.value = Math.min(loadingProgress.value + 10, 95);
        }
      }
    );
    
    loadingProgress.value = 100;
    
    if (!report) {
      throw new Error('Brak raportu w odpowiedzi');
    }
    
    sessionStorage.setItem('lastReport', JSON.stringify(report));
    sessionStorage.setItem('lastReportUrl', referenceUrl.value || selectedLocation.value.address);
    
    router.push({
      name: 'report',
      query: { fromAnalysis: 'true' },
    });
    
  } catch (error) {
    toast.add({
      severity: 'error',
      summary: 'Błąd analizy',
      detail: getErrorMessage(error),
      life: 5000,
    });
  } finally {
    isLoading.value = false;
    loadingStatus.value = '';
    loadingProgress.value = 0;
  }
}

async function loadRecentAnalyses() {
  isLoadingRecent.value = true;
  try {
    recentAnalyses.value = await analyzerApi.getRecentHistory();
  } catch (error) {
    console.warn('Nie udało się pobrać historii:', error);
  } finally {
    isLoadingRecent.value = false;
  }
}

function openHistoryItem(item: HistoryItem) {
  router.push({ name: 'history-detail', params: { id: item.id } });
}

function formatPrice(price: number | null): string {
  if (!price) return '-';
  return new Intl.NumberFormat('pl-PL', {
    style: 'currency',
    currency: 'PLN',
    maximumFractionDigits: 0,
  }).format(price);
}

function formatDate(date: string): string {
  return new Date(date).toLocaleDateString('pl-PL', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function getScoreColor(score: number | null): string {
  if (score === null) return '#6B7280';
  if (score >= 70) return '#10B981';
  if (score >= 50) return '#F59E0B';
  if (score >= 30) return '#F97316';
  return '#EF4444';
}

// Load recent on mount
loadRecentAnalyses();
</script>

<template>
  <div class="min-h-screen bg-gradient-to-br from-slate-50 via-white to-blue-50">
    
    <!-- Hero Section -->
    <section class="w-full pb-16 pt-8">
      <div class="max-w-6xl mx-auto px-4 sm:px-6">
        <div class="grid grid-cols-1 lg:grid-cols-2 gap-8 items-center">
          
          <!-- Hero Text -->
          <div class="space-y-6 text-center lg:text-left">
            <span class="inline-block text-sm font-semibold uppercase tracking-wide text-blue-600">
              Sprawdź przed zakupem
            </span>
            
            <h1 class="text-4xl sm:text-5xl font-bold leading-tight text-slate-800">
              Analiza <span class="text-transparent bg-clip-text bg-gradient-to-r from-blue-500 to-cyan-500">ryzyka zakupu</span> mieszkania
            </h1>
            
            <p class="text-lg text-slate-600 max-w-xl">
              Wskaż lokalizację, podaj cenę i metraż – otrzymasz szczegółową ocenę okolicy i ryzyk zakupu
            </p>
            
            <div class="flex flex-col sm:flex-row gap-4 justify-center lg:justify-start">
              <a 
                href="#analyze" 
                class="inline-flex items-center justify-center px-8 py-4 bg-gradient-to-r from-blue-500 to-blue-600 text-white font-semibold rounded-full shadow-lg hover:shadow-xl hover:scale-105 transition-all duration-300"
              >
                Rozpocznij analizę
                <i class="pi pi-arrow-right ml-2"></i>
              </a>
              <a 
                href="#how-it-works" 
                class="inline-flex items-center justify-center px-6 py-4 border-2 border-blue-500 text-blue-600 font-semibold rounded-full hover:bg-blue-50 transition-all duration-300"
              >
                Jak to działa?
              </a>
            </div>
          </div>
          
          <!-- Hero illustration -->
          <div class="hidden lg:flex items-center justify-center">
            <div class="relative w-full max-w-md">
              <!-- Decorative circles -->
              <div class="absolute -top-8 -left-8 w-32 h-32 bg-cyan-200 rounded-full blur-2xl opacity-60"></div>
              <div class="absolute -bottom-8 -right-8 w-40 h-40 bg-blue-200 rounded-full blur-2xl opacity-60"></div>
              
              <!-- Icon showcase -->
              <div class="relative bg-white rounded-3xl p-8 shadow-2xl border border-slate-100">
                <div class="grid grid-cols-3 gap-6">
                  <div class="flex flex-col items-center gap-2">
                    <div class="w-16 h-16 rounded-2xl bg-gradient-to-br from-emerald-400 to-emerald-600 flex items-center justify-center shadow-lg">
                      <i class="pi pi-map-marker text-2xl text-white"></i>
                    </div>
                    <span class="text-xs text-slate-500 font-medium">Lokalizacja</span>
                  </div>
                  <div class="flex flex-col items-center gap-2">
                    <div class="w-16 h-16 rounded-2xl bg-gradient-to-br from-blue-400 to-blue-600 flex items-center justify-center shadow-lg">
                      <i class="pi pi-chart-bar text-2xl text-white"></i>
                    </div>
                    <span class="text-xs text-slate-500 font-medium">Analiza</span>
                  </div>
                  <div class="flex flex-col items-center gap-2">
                    <div class="w-16 h-16 rounded-2xl bg-gradient-to-br from-purple-400 to-purple-600 flex items-center justify-center shadow-lg">
                      <i class="pi pi-check-circle text-2xl text-white"></i>
                    </div>
                    <span class="text-xs text-slate-500 font-medium">Werdykt</span>
                  </div>
                </div>
                
                <div class="mt-6 p-4 bg-slate-50 rounded-xl">
                  <div class="flex items-center gap-3">
                    <div class="w-12 h-12 rounded-full bg-gradient-to-br from-amber-400 to-orange-500 flex items-center justify-center text-white font-bold">
                      78
                    </div>
                    <div>
                      <p class="font-semibold text-slate-800">Wynik analizy</p>
                      <p class="text-sm text-emerald-500">Dobra lokalizacja ✓</p>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
    
    <!-- Main Analysis Form Section -->
    <section id="analyze" class="w-full py-12">
      <div class="max-w-5xl mx-auto px-4 sm:px-6">
        <div class="bg-white rounded-2xl shadow-xl p-6 md:p-8 border border-slate-100">
          <div class="flex flex-col gap-6">
            
            <!-- Step 1: Location -->
            <div>
              <div class="flex items-center gap-2 mb-3">
                <span class="inline-flex items-center justify-center w-8 h-8 rounded-full bg-blue-500 text-white text-sm font-bold">1</span>
                <h3 class="font-semibold text-slate-800">Wskaż lokalizację</h3>
                <span class="text-red-500">*</span>
              </div>
              
              <div v-if="selectedLocation" class="bg-emerald-50 border border-emerald-200 rounded-xl p-4">
                <div class="flex items-center justify-between">
                  <div class="flex items-center gap-3">
                    <div class="w-10 h-10 rounded-full bg-emerald-500 flex items-center justify-center">
                      <i class="pi pi-check text-white"></i>
                    </div>
                    <div>
                      <p class="font-medium text-slate-800">{{ selectedLocation.address }}</p>
                      <p class="text-sm text-slate-500">{{ selectedLocation.lat.toFixed(5) }}, {{ selectedLocation.lng.toFixed(5) }}</p>
                    </div>
                  </div>
                  <Button 
                    icon="pi pi-times" 
                    severity="secondary" 
                    text 
                    rounded 
                    @click="clearLocation"
                    v-tooltip="'Zmień lokalizację'"
                  />
                </div>
              </div>
              
              <div v-else class="border-2 border-dashed border-slate-200 rounded-xl p-4 hover:border-blue-300 transition-colors">
                <LocationPicker
                  @location-selected="handleLocationSelected"
                  :show-cancel="false"
                />
              </div>
            </div>
            
            <!-- Step 2: Price & Area -->
            <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <div class="flex items-center gap-2 mb-3">
                  <span class="inline-flex items-center justify-center w-8 h-8 rounded-full bg-blue-500 text-white text-sm font-bold">2</span>
                  <h3 class="font-semibold text-slate-800">Cena</h3>
                  <span class="text-red-500">*</span>
                </div>
                <div class="relative">
                  <InputNumber 
                    v-model="price"
                    placeholder="np. 650 000"
                    :min="0"
                    :max="50000000"
                    locale="pl-PL"
                    class="w-full"
                    inputClass="!py-3 !text-lg !pr-16"
                    :disabled="isLoading"
                  />
                  <span class="absolute right-4 top-1/2 -translate-y-1/2 text-slate-400 font-medium">PLN</span>
                </div>
              </div>
              
              <div>
                <div class="flex items-center gap-2 mb-3">
                  <span class="inline-flex items-center justify-center w-8 h-8 rounded-full bg-blue-500 text-white text-sm font-bold">3</span>
                  <h3 class="font-semibold text-slate-800">Metraż</h3>
                  <span class="text-red-500">*</span>
                </div>
                <div class="relative">
                  <InputNumber 
                    v-model="areaSqm"
                    placeholder="np. 54"
                    :min="1"
                    :max="1000"
                    :minFractionDigits="0"
                    :maxFractionDigits="1"
                    class="w-full"
                    inputClass="!py-3 !text-lg !pr-12"
                    :disabled="isLoading"
                  />
                  <span class="absolute right-4 top-1/2 -translate-y-1/2 text-slate-400 font-medium">m²</span>
                </div>
              </div>
            </div>
            
            <!-- Price per sqm display -->
            <div v-if="pricePerSqm" class="bg-blue-50 rounded-xl p-4 flex items-center justify-center gap-3">
              <i class="pi pi-calculator text-blue-600"></i>
              <span class="text-slate-600">Cena za m²:</span>
              <span class="font-bold text-lg text-blue-600">{{ formatPrice(pricePerSqm) }}/m²</span>
            </div>
            
            <!-- Advanced Options Toggle -->
            <div>
              <button 
                @click="showAdvanced = !showAdvanced"
                class="flex items-center gap-2 text-sm text-slate-500 hover:text-blue-600 transition-colors"
              >
                <i :class="showAdvanced ? 'pi pi-chevron-up' : 'pi pi-chevron-down'"></i>
                Opcje zaawansowane
              </button>
              
              <Transition name="slide">
                <div v-if="showAdvanced" class="mt-4 space-y-4">
                  <div>
                    <label class="block text-sm font-medium text-slate-600 mb-2">
                      <i class="pi pi-link mr-1"></i>
                      Link do ogłoszenia (opcjonalnie)
                    </label>
                    <InputText 
                      v-model="referenceUrl"
                      placeholder="https://www.otodom.pl/pl/oferta/..."
                      class="w-full"
                      :disabled="isLoading"
                    />
                    <p class="text-xs text-slate-400 mt-1">Zapisany jako referencja w raporcie</p>
                  </div>
                  
                  <div class="flex items-center gap-3">
                    <span class="text-sm font-medium text-slate-600">
                      <i class="pi pi-compass mr-1"></i>
                      Zasięg analizy:
                    </span>
                    <SelectButton 
                      v-model="radius" 
                      :options="radiusOptions" 
                      optionLabel="label" 
                      optionValue="value" 
                      :allowEmpty="false"
                    />
                  </div>
                </div>
              </Transition>
            </div>
            
            <!-- Submit Button -->
            <div class="flex justify-end">
              <Button
                :label="isLoading ? 'Analizuję...' : 'Analizuj lokalizację'"
                :icon="isLoading ? 'pi pi-spin pi-spinner' : 'pi pi-search'"
                :disabled="!canSubmit"
                @click="handleAnalyze"
                class="!py-4 !px-10 !text-lg !font-semibold !rounded-full !shadow-lg"
              />
            </div>

            <!-- Loading Status -->
            <Transition name="fade">
              <div v-if="isLoading" class="mt-2">
                <div class="bg-blue-50 rounded-2xl p-6 border border-blue-100">
                  <div class="flex items-center gap-4 mb-4">
                    <div class="w-14 h-14 rounded-xl bg-blue-500 flex items-center justify-center shadow-lg">
                      <ProgressSpinner style="width: 28px; height: 28px" strokeWidth="4" fill="transparent" animationDuration=".7s" />
                    </div>
                    <div class="flex-1">
                      <p class="font-bold text-lg text-slate-800">{{ loadingStatus }}</p>
                      <p class="text-sm text-slate-500">Proszę czekać...</p>
                    </div>
                    <span class="text-2xl font-bold text-blue-600">{{ loadingProgress }}%</span>
                  </div>
                  
                  <div class="h-3 bg-slate-200 rounded-full overflow-hidden">
                    <div 
                      class="h-full bg-gradient-to-r from-blue-400 to-blue-600 rounded-full transition-all duration-500"
                      :style="{ width: `${loadingProgress}%` }"
                    ></div>
                  </div>
                </div>
              </div>
            </Transition>
          </div>
        </div>
      </div>
    </section>
    
    <!-- Features Section -->
    <section id="how-it-works" class="w-full py-16">
      <div class="max-w-5xl mx-auto px-4 sm:px-6">
        <h2 class="text-3xl font-bold text-center mb-12 text-slate-800">
          Co <span class="text-blue-600">sprawdzamy</span>?
        </h2>
        
        <div class="grid grid-cols-1 md:grid-cols-3 gap-6">
          <div class="group bg-white rounded-2xl p-6 shadow-lg hover:shadow-xl transition-all duration-300 border border-slate-100 hover:-translate-y-1">
            <div class="w-14 h-14 rounded-xl bg-gradient-to-br from-red-400 to-rose-500 flex items-center justify-center shadow-lg mb-4 group-hover:scale-110 transition-transform">
              <i class="pi pi-exclamation-triangle text-2xl text-white"></i>
            </div>
            <h3 class="font-bold text-lg mb-2 text-slate-800">Czerwone Flagi</h3>
            <p class="text-slate-500">
              Wykrywamy ryzykowne czynniki: hałas, bliskość dróg, brak zieleni
            </p>
          </div>
          
          <div class="group bg-white rounded-2xl p-6 shadow-lg hover:shadow-xl transition-all duration-300 border border-slate-100 hover:-translate-y-1">
            <div class="w-14 h-14 rounded-xl bg-gradient-to-br from-blue-400 to-indigo-500 flex items-center justify-center shadow-lg mb-4 group-hover:scale-110 transition-transform">
              <i class="pi pi-chart-bar text-2xl text-white"></i>
            </div>
            <h3 class="font-bold text-lg mb-2 text-slate-800">Cena vs Rynek</h3>
            <p class="text-slate-500">
              Porównujemy Twoją cenę ze średnią dzielnicy: tanio / ok / drogo
            </p>
          </div>
          
          <div class="group bg-white rounded-2xl p-6 shadow-lg hover:shadow-xl transition-all duration-300 border border-slate-100 hover:-translate-y-1">
            <div class="w-14 h-14 rounded-xl bg-gradient-to-br from-emerald-400 to-teal-500 flex items-center justify-center shadow-lg mb-4 group-hover:scale-110 transition-transform">
              <i class="pi pi-check-circle text-2xl text-white"></i>
            </div>
            <h3 class="font-bold text-lg mb-2 text-slate-800">Werdykt Zakupu</h3>
            <p class="text-slate-500">
              Jasna rekomendacja: POLECAM / UWAŻAJ / ODRADZAM z uzasadnieniem
            </p>
          </div>
        </div>
      </div>
    </section>
    
    <!-- Recent analyses -->
    <section v-if="recentAnalyses.length > 0" class="w-full py-12">
      <div class="max-w-5xl mx-auto px-4 sm:px-6">
        <div class="bg-white rounded-2xl shadow-xl p-6 border border-slate-100">
          <div class="flex items-center gap-3 mb-6">
            <div class="w-10 h-10 rounded-xl bg-gradient-to-br from-violet-400 to-purple-500 flex items-center justify-center">
              <i class="pi pi-history text-white"></i>
            </div>
            <h2 class="text-xl font-bold text-slate-800">Ostatnie analizy</h2>
          </div>
          
          <div class="space-y-3">
            <div 
              v-for="item in recentAnalyses.slice(0, 5)" 
              :key="item.id"
              @click="openHistoryItem(item)"
              class="group flex items-center gap-4 p-4 bg-slate-50 rounded-xl cursor-pointer hover:bg-slate-100 transition-all hover:shadow-md"
            >
              <div 
                class="w-12 h-12 rounded-xl flex items-center justify-center font-bold text-white shadow-md"
                :style="{ background: getScoreColor(item.neighborhood_score) }"
              >
                {{ item.neighborhood_score !== null ? Math.round(item.neighborhood_score) : '?' }}
              </div>
              
              <div class="flex-1 min-w-0">
                <p class="font-semibold text-slate-800 truncate">
                  {{ item.title || item.location || 'Bez tytułu' }}
                </p>
                <div class="flex items-center gap-3 text-sm text-slate-500">
                  <span v-if="item.price">{{ formatPrice(item.price) }}</span>
                  <span v-if="item.area_sqm">{{ item.area_sqm }} m²</span>
                  <span v-if="item.rooms">{{ item.rooms }} pok.</span>
                </div>
              </div>
              
              <div class="text-sm text-slate-400 hidden md:block">
                {{ formatDate(item.created_at) }}
              </div>
              
              <i class="pi pi-chevron-right text-slate-300 group-hover:text-blue-500 transition-colors"></i>
            </div>
          </div>
        </div>
      </div>
    </section>
    
    <!-- FAQ Section -->
    <section class="w-full py-16">
      <div class="max-w-3xl mx-auto px-4 sm:px-6">
        <h2 class="text-3xl font-bold text-center mb-8 text-slate-800">
          Często zadawane <span class="text-blue-600">pytania</span>
        </h2>
        
        <ul class="space-y-4">
          <li
            v-for="(faq, index) in faqItems"
            :key="index"
            class="bg-white rounded-xl shadow-sm overflow-hidden transition-all duration-300"
            :class="{ 'shadow-md': faq.open }"
          >
            <button
              @click="toggleFaq(index)"
              class="w-full px-6 py-5 flex items-center justify-between text-left transition-colors hover:bg-slate-50"
            >
              <span class="font-semibold text-slate-800">
                {{ faq.title }}
              </span>
              <span
                class="ml-4 shrink-0 w-8 h-8 flex items-center justify-center rounded-full bg-slate-100 transition-transform duration-300"
                :class="{ 'rotate-180': faq.open }"
              >
                <i class="pi pi-chevron-down text-sm text-slate-500"></i>
              </span>
            </button>
            
            <Transition name="accordion">
              <div v-show="faq.open" class="px-6 pb-5">
                <p class="text-slate-600 leading-relaxed">
                  {{ faq.description }}
                </p>
              </div>
            </Transition>
          </li>
        </ul>
      </div>
    </section>
    
    <!-- Footer -->
    <footer class="text-center p-8 border-t border-slate-100">
      <p class="font-semibold text-blue-600 text-xl mb-2">loktis.pl</p>
      <p class="text-sm text-slate-400">Dane pochodzą z OpenStreetMap • Analiza ma charakter poglądowy</p>
    </footer>
  </div>
</template>

<style scoped>
/* Transitions */
.fade-enter-active,
.fade-leave-active {
  transition: all 0.3s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
  transform: translateY(-10px);
}

.slide-enter-active,
.slide-leave-active {
  transition: all 0.3s ease;
}

.slide-enter-from,
.slide-leave-to {
  opacity: 0;
  max-height: 0;
  overflow: hidden;
}

.slide-enter-to,
.slide-leave-from {
  max-height: 200px;
}

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
</style>
