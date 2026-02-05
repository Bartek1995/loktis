"""
Hybrid POI Provider - 3-warstwowa strategia pobierania POI.

Warstwy:
1. Overpass (base) - pełne pokrycie, gęstość, scoring (0$)
2. Google Enrichment - rating/reviews dla top-k POI per kategoria
3. Google Fallback - uzupełnienie brakujących kategorii

Optymalizuje koszt: ~$0.77 → ~$0.15-0.40 per analiza.
"""
import logging
from typing import Dict, List, Any, Tuple, Optional
from dataclasses import dataclass

from .overpass_client import OverpassClient, POI, MAX_POIS_PER_CATEGORY
from .google_places_client import GooglePlacesClient
from .nature_metrics import NatureMetrics

logger = logging.getLogger(__name__)


@dataclass
class EnrichmentConfig:
    """Konfiguracja enrichment per kategoria."""
    top_k: int = 3
    enrich: bool = True
    min_reviews_to_show: int = 20
    max_distance_m: int = 100  # Max odległość POI-Google do akceptacji
    search_radius_m: int = 100  # Promień wyszukiwania nearby


# Domyślna konfiguracja enrichment per kategoria
# max_distance_m zwiększone bo OSM i Google mają często przesunięcia 50-100m
DEFAULT_ENRICHMENT_CONFIG = {
    'shops': EnrichmentConfig(top_k=5, enrich=True, max_distance_m=120, search_radius_m=120),
    'education': EnrichmentConfig(top_k=3, enrich=True, max_distance_m=250, search_radius_m=200),
    'health': EnrichmentConfig(top_k=3, enrich=True, max_distance_m=180, search_radius_m=150),
    'food': EnrichmentConfig(top_k=3, enrich=True, max_distance_m=150, search_radius_m=120),
    'transport': EnrichmentConfig(top_k=3, enrich=False),  # OSM wystarczy
    'nature_place': EnrichmentConfig(top_k=2, enrich=True, max_distance_m=200, search_radius_m=150),  # Parki
    'nature_background': EnrichmentConfig(top_k=0, enrich=False),  # Metryki, nie POI
    'leisure': EnrichmentConfig(top_k=3, enrich=True, max_distance_m=150, search_radius_m=150),
    'finance': EnrichmentConfig(top_k=2, enrich=False),
}

# Typy Google do fallbacku per kategoria (minimalne)
FALLBACK_TYPES = {
    'shops': ['supermarket', 'convenience_store'],
    'education': ['school'],
    'health': ['pharmacy', 'hospital'],
    'transport': ['bus_station', 'transit_station'],
    'food': ['restaurant', 'cafe'],
    'finance': ['bank', 'atm'],
}

# Próg coverage - poniżej tego uruchamiamy fallback
COVERAGE_THRESHOLD = 2

# Nazwy generic - nie enrichmentuj domyślnie (chyba że mało alternatyw i blisko)
GENERIC_NAMES = frozenset({
    'plac zabaw', 'boisko', 'park', 'skwer', 'zieleń',
    'przystanek', 'przystanek autobusowy', 'przystanek tramwajowy',
    'sklep', 'kiosk', 'parking', 'garaż',
    'obiekt bez nazwy', 'unknown',
})

# Progi dla "smart generic" - próbuj enrichment dla generic jeśli:
GENERIC_NEARBY_THRESHOLD_M = 120  # POI jest bardzo blisko
GENERIC_FEW_ALTERNATIVES = 3      # Mało alternatyw w kategorii


class HybridPOIProvider:
    """
    Provider POI łączący Overpass i Google Places.
    
    Strategia:
    1. Overpass jako źródło prawdy (pełne pokrycie)
    2. Google enrichment dla top-k POI (rating/reviews)
    3. Google fallback gdy kategoria ma < COVERAGE_THRESHOLD wyników
    """
    
    def __init__(
        self,
        overpass_client: Optional[OverpassClient] = None,
        google_client: Optional[GooglePlacesClient] = None,
        enrichment_config: Optional[Dict[str, EnrichmentConfig]] = None
    ):
        self.overpass = overpass_client or OverpassClient()
        self.google = google_client or GooglePlacesClient()
        self.config = enrichment_config or DEFAULT_ENRICHMENT_CONFIG
    
    def get_pois_hybrid(
        self,
        lat: float,
        lon: float,
        radius_m: int = 500,
        enable_enrichment: bool = True,
        enable_fallback: bool = True
    ) -> Tuple[Dict[str, List[POI]], Dict[str, Any]]:
        """
        Pobiera POI używając strategii 3-warstwowej.
        
        Returns:
            tuple: (pois_by_category, metrics)
        """
        # === WARSTWA 1: Overpass jako base ===
        logger.info(f"Hybrid: Layer 1 - Overpass base ({lat}, {lon}) r={radius_m}")
        pois, metrics = self.overpass.get_pois_around(lat, lon, radius_m)
        
        # Policz coverage per kategoria
        coverage = {cat: len(items) for cat, items in pois.items()}
        logger.debug(f"Hybrid: Overpass coverage: {coverage}")
        
        # === WARSTWA 3: Fallback dla brakujących kategorii ===
        # (Robimy przed enrichment żeby mieć pełną listę do wzbogacenia)
        if enable_fallback:
            missing_categories = self._find_missing_categories(coverage)
            if missing_categories:
                logger.info(f"Hybrid: Layer 3 - Fallback for: {missing_categories}")
                self._apply_fallback(pois, lat, lon, radius_m, missing_categories)
        
        # === WARSTWA 2: Google enrichment dla top-k ===
        if enable_enrichment and self.google.api_key:
            logger.info(f"Hybrid: Layer 2 - Enrichment for top-k POIs")
            enriched_count = self._enrich_top_k(pois, lat, lon)
            logger.info(f"Hybrid: Enriched {enriched_count} POIs with ratings")

        # Final dedup po enrichment/fallback
        self._dedupe_pois(pois)
        
        return pois, metrics
    
    def _find_missing_categories(self, coverage: Dict[str, int]) -> List[str]:
        """Znajduje kategorie z niewystarczającym coverage."""
        missing = []
        for cat, count in coverage.items():
            if cat in FALLBACK_TYPES and count < COVERAGE_THRESHOLD:
                missing.append(cat)
        return missing
    
    def _apply_fallback(
        self,
        pois: Dict[str, List[POI]],
        lat: float,
        lon: float,
        radius_m: int,
        categories: List[str]
    ) -> None:
        """
        Uzupełnia brakujące kategorie przez Google Nearby Search.
        Tylko dla kategorii z FALLBACK_TYPES.
        """
        if not self.google.api_key:
            logger.warning("Hybrid: Google API key not configured, skipping fallback")
            return
        
        for category in categories:
            types = FALLBACK_TYPES.get(category, [])
            if not types:
                continue
            
            logger.debug(f"Hybrid: Fallback search for {category}: {types}")
            
            for gtype in types:
                try:
                    results = self.google._search_nearby(lat, lon, radius_m, gtype)
                    
                    for place in results[:5]:  # Max 5 per type
                        poi = self.google._create_poi_from_place(place, category, lat, lon)
                        if poi and not self._is_duplicate(poi, pois[category]):
                            poi.tags['source'] = 'google_fallback'
                            pois[category].append(poi)
                            
                except Exception as e:
                    logger.warning(f"Hybrid: Fallback error for {gtype}: {e}")
            
            # Sortuj po dystansie
            pois[category].sort(key=lambda p: p.distance_m)
    
    def _enrich_top_k(
        self,
        pois: Dict[str, List[POI]],
        lat: float,
        lon: float
    ) -> int:
        """
        Wzbogaca top-k POI per kategoria o rating i reviews z Google.
        Używa Find Place + Place Details z cache 7 dni.
        Deduplikuje po place_id.
        
        Returns:
            int: Liczba wzbogaconych POI
        """
        from ..cache import google_details_cache, TTLCache
        
        enriched_count = 0
        seen_place_ids = set()  # Deduplikacja w ramach jednej analizy
        
        for category, items in pois.items():
            config = self.config.get(category)
            if not config or not config.enrich or config.top_k <= 0:
                continue
            
            # Weź tylko top-k najbliższych
            top_k = items[:config.top_k]
            category_count = len(items)  # Ile mamy w tej kategorii
            
            for poi in top_k:
                # Pomiń jeśli już ma rating (np. z Google fallback)
                if poi.tags.get('rating'):
                    continue
                
                # Smart generic names handling
                name_lower = poi.name.lower().strip()
                is_generic = name_lower in GENERIC_NAMES or poi.tags.get('_nameless')
                
                if is_generic:
                    # Próbuj enrichment mimo generic jeśli: blisko + mało alternatyw
                    should_try_anyway = (
                        poi.distance_m <= GENERIC_NEARBY_THRESHOLD_M and 
                        category_count <= GENERIC_FEW_ALTERNATIVES
                    )
                    if not should_try_anyway:
                        logger.debug(f"Skipping generic name: {poi.name} (dist={poi.distance_m:.0f}m, alts={category_count})")
                        continue
                    else:
                        logger.debug(f"Trying generic: {poi.name} (close + few alternatives)")
                
                # Używamy per-category search radius
                search_radius = config.search_radius_m
                
                try:
                    # Sprawdź cache najpierw (jeśli mamy place_id)
                    existing_place_id = poi.tags.get('place_id')
                    cache_key = f"details:{existing_place_id}" if existing_place_id else None
                    details = None
                    
                    # Sprawdź czy ten place_id już był wzbogacony w tej sesji
                    if existing_place_id and existing_place_id in seen_place_ids:
                        logger.debug(f"Skipping already enriched place_id: {existing_place_id}")
                        continue
                    
                    # Sprawdź cache
                    if cache_key:
                        details = google_details_cache.get(cache_key)
                        if details:
                            logger.debug(f"Cache hit for {poi.name}")
                    
                    # Jeśli nie w cache, pobierz z API
                    if details is None:
                        # OPTYMALIZACJA: jeśli mamy place_id, użyj tylko _get_place_details (1 req)
                        # zamiast find_place_details który robi nearby+details (2 req)
                        if existing_place_id:
                            logger.debug(f"Direct details lookup for {poi.name} (place_id known)")
                            details = self.google._get_place_details(
                                existing_place_id, 
                                ['rating', 'user_ratings_total', 'geometry', 'place_id']
                            )
                            if details:
                                details['place_id'] = existing_place_id  # Upewnij się że place_id jest w response
                        else:
                            # Brak place_id - pełne wyszukiwanie nearby+details (2 req)
                            details = self.google.find_place_details(
                                name=poi.name,
                                lat=poi.lat,
                                lon=poi.lon,
                                search_radius=search_radius
                            )
                        
                        # Ustal finalne place_id
                        final_place_id = None
                        if details:
                            final_place_id = details.get('place_id') or existing_place_id
                        
                        # Zapisz w cache (pozytywny lub negatywny)
                        if final_place_id:
                            cache_key = f"details:{final_place_id}"
                            google_details_cache.set(cache_key, details or {'_not_found': True})
                            poi.tags['place_id'] = final_place_id
                        elif not details:
                            # Negative cache: POI nie znaleziony w Google (24h)
                            neg_key = f"notfound:{poi.name}:{round(poi.lat,3)}:{round(poi.lon,3)}"
                            google_details_cache.set(neg_key, {'_not_found': True}, ttl=86400)
                    
                    # Sprawdź czy to negative cache hit
                    if details and details.get('_not_found'):
                        continue
                    
                    if details:
                        # Walidacja odległości: sprawdź czy Google zwrócił POI w pobliżu
                        google_geom = details.get('geometry', {}).get('location', {})
                        google_lat = google_geom.get('lat')
                        google_lon = google_geom.get('lng')
                        
                        if google_lat and google_lon:
                            from .overpass_client import OverpassClient
                            distance_to_google = OverpassClient()._haversine_distance(
                                poi.lat, poi.lon, google_lat, google_lon
                            )
                            # Używamy per-category max distance
                            if distance_to_google > config.max_distance_m:
                                logger.debug(
                                    f"Rejecting enrichment for {poi.name}: "
                                    f"Google result {distance_to_google:.0f}m away (max {config.max_distance_m}m)"
                                )
                                continue
                        
                        final_place_id = poi.tags.get('place_id') or details.get('place_id')
                        if final_place_id and final_place_id in seen_place_ids:
                            logger.debug(f"Skipping duplicate place_id after lookup: {final_place_id}")
                            continue

                        rating = details.get('rating')
                        reviews = details.get('user_ratings_total', 0)
                        
                        # Dopisz do tags
                        poi.tags['rating'] = rating
                        poi.tags['reviews_count'] = reviews
                        poi.tags['user_ratings_total'] = reviews
                        poi.tags['enriched'] = True
                        
                        # Ustal finalne place_id i dodaj do seen (ZAWSZE po enrichment)
                        final_place_id = poi.tags.get('place_id') or details.get('place_id')
                        if final_place_id:
                            poi.tags['place_id'] = final_place_id
                            seen_place_ids.add(final_place_id)
                        
                        # Oznacz jako "mało opinii" jeśli poniżej progu
                        if reviews < config.min_reviews_to_show:
                            poi.tags['low_reviews'] = True
                        
                        enriched_count += 1
                        logger.debug(
                            f"Enriched: {poi.name} dist={poi.distance_m:.0f}m "
                            f"place_id={final_place_id} rating={rating} reviews={reviews}"
                        )
                        
                except Exception as e:
                    logger.warning(f"Hybrid: Enrichment error for {poi.name}: {e}")
        
        return enriched_count
    
    def _is_duplicate(self, new_poi: POI, existing: List[POI]) -> bool:
        """
        Sprawdza czy POI już istnieje.
        Priorytet: place_id > (nazwa + dystans < 50m).
        """
        new_place_id = new_poi.tags.get('place_id')
        
        for poi in existing:
            # Sprawdź po place_id (najbardziej niezawodne)
            if new_place_id and poi.tags.get('place_id') == new_place_id:
                return True
            
            # Fallback: nazwa + bliska odległość
            if (poi.name.lower() == new_poi.name.lower() and 
                abs(poi.distance_m - new_poi.distance_m) < 50):
                return True
        
        return False

    def _dedupe_pois(self, pois: Dict[str, List[POI]]) -> None:
        """Deduplikuje POI po place_id lub (nazwa + bucket dystansu)."""
        for category, items in pois.items():
            seen_place_ids = set()
            seen_fallback = set()
            unique_items = []
            
            for poi in items:
                place_id = poi.tags.get('place_id')
                if place_id:
                    if place_id in seen_place_ids:
                        continue
                    seen_place_ids.add(place_id)
                else:
                    fallback_key = (poi.name.lower(), round((poi.distance_m or 0) / 20) * 20)
                    if fallback_key in seen_fallback:
                        continue
                    seen_fallback.add(fallback_key)
                
                unique_items.append(poi)
            
            unique_items.sort(key=lambda p: p.distance_m)
            pois[category] = unique_items[:MAX_POIS_PER_CATEGORY]
