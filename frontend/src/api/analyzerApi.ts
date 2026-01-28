/**
 * API Client dla Analizatora Ogłoszeń
 */
import axios, { type AxiosInstance, type AxiosError } from 'axios';

// Konfiguracja bazowa
const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000/api';

const apiClient: AxiosInstance = axios.create({
  baseURL: API_BASE_URL,
  timeout: 60000, // 60 sekund - analiza może trwać
  headers: {
    'Content-Type': 'application/json',
  },
});

// Typy odpowiedzi
export interface TLDRData {
  pros: string[];
  cons: string[];
}

export interface ListingData {
  url: string;
  title: string;
  price: number | null;
  price_per_sqm: number | null;
  area_sqm: number | null;
  rooms: number | null;
  floor: string;
  location: string;
  description: string;
  images: string[];
  latitude: number | null;
  longitude: number | null;
  has_precise_location: boolean;
  errors: string[];
}

export interface POIItem {
  name: string;
  distance_m: number;
  subcategory: string;
}

export interface POICategoryStats {
  name: string;
  count: number;
  nearest: number;
  items: POIItem[];
}

export interface NeighborhoodData {
  has_location: boolean;
  score: number | null;
  summary: string;
  details: Record<string, {
    count: number;
    nearest_m: number | null;
    names: string[];
    rating: string;
  }>;
  poi_stats: Record<string, POICategoryStats>;
  markers: Array<{
    lat: number;
    lon: number;
    name: string;
    category: string;
    subcategory: string;
    color: string;
    distance: number | null;
  }>;
}

export interface AnalysisReport {
  success: boolean;
  errors: string[];
  warnings: string[];
  tldr: TLDRData;
  listing: ListingData;
  neighborhood: NeighborhoodData;
  checklist: string[];
  limitations: string[];
}

export interface ValidationResult {
  valid: boolean;
  error: string | null;
  allowed_domains: string[];
}

export interface ProviderInfo {
  name: string;
  domain: string;
  example: string;
}

export interface ProvidersResponse {
  providers: ProviderInfo[];
  allowed_domains: string[];
}

export interface HistoryItem {
  id: number;
  url: string;
  title: string;
  price: number | null;
  price_per_sqm: number | null;
  area_sqm: number | null;
  rooms: number | null;
  floor: string;
  location: string;
  neighborhood_score: number | null;
  pros: string[];
  cons: string[];
  source_provider: string;
  created_at: string;
}

// API functions
export const analyzerApi = {
  /**
   * Analizuje ogłoszenie z podanego URL
   */
  async analyze(url: string, useCache = true): Promise<AnalysisReport> {
    const response = await apiClient.post<AnalysisReport>('/analyze/', {
      url,
      use_cache: useCache,
    });
    return response.data;
  },

  /**
   * Analizuje ogłoszenie ze strumieniowaniem statusu (NDJSON)
   */
  async analyzeStream(
    url: string, 
    radius: number, 
    onStatus: (event: { status: string; message?: string; result?: AnalysisReport; error?: string }) => void
  ): Promise<AnalysisReport> {
    const response = await fetch(`${API_BASE_URL}/analyze/`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ url, radius, use_cache: true }),
    });

    if (!response.body) throw new Error('Brak odpowiedzi ze serwera');

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || ''; 
        
        for (const line of lines) {
          if (!line.trim()) continue;
          try {
            const event = JSON.parse(line);
            onStatus(event);
            
            if (event.status === 'complete') {
              return event.result;
            }
            if (event.status === 'error') {
              throw new Error(event.error || 'Wystąpił błąd analizy');
            }
          } catch (e) {
            console.warn('Błąd parsowania linii streamu:', e);
          }
        }
      }
    } finally {
      reader.cancel();
    }
    
    throw new Error('Strumień zakończony bez wyniku');
  },

  /**
   * Waliduje URL przed wysłaniem
   */
  async validateUrl(url: string): Promise<ValidationResult> {
    const response = await apiClient.post<ValidationResult>('/validate-url/', { url });
    return response.data;
  },

  /**
   * Pobiera listę obsługiwanych providerów
   */
  async getProviders(): Promise<ProvidersResponse> {
    const response = await apiClient.get<ProvidersResponse>('/providers/');
    return response.data;
  },

  /**
   * Pobiera historię analiz
   */
  async getHistory(page = 1): Promise<{ results: HistoryItem[]; count: number }> {
    const response = await apiClient.get('/history/', { params: { page } });
    return response.data;
  },

  /**
   * Pobiera ostatnie analizy
   */
  async getRecentHistory(): Promise<HistoryItem[]> {
    const response = await apiClient.get<HistoryItem[]>('/history/recent/');
    return response.data;
  },

  /**
   * Pobiera szczegóły analizy z historii
   */
  async getHistoryDetail(id: number): Promise<AnalysisReport> {
    const response = await apiClient.get(`/history/${id}/report/`);
    return response.data;
  },
};

// Error handling helper
export function getErrorMessage(error: unknown): string {
  if (axios.isAxiosError(error)) {
    const axiosError = error as AxiosError<{ error?: string; errors?: string[] }>;
    
    if (axiosError.response?.status === 429) {
      return axiosError.response.data?.error || 'Zbyt wiele requestów. Poczekaj chwilę.';
    }
    
    if (axiosError.response?.data?.error) {
      return axiosError.response.data.error;
    }
    
    if (axiosError.response?.data?.errors?.length) {
      return axiosError.response.data.errors.join(', ');
    }
    
    if (axiosError.message) {
      return axiosError.message;
    }
  }
  
  if (error instanceof Error) {
    return error.message;
  }
  
  return 'Wystąpił nieznany błąd';
}

export default analyzerApi;
