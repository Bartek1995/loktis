"""
Hybrid POI Provider - 3-warstwowa strategia pobierania POI.

Warstwy:
1. Overpass (base) - pełne pokrycie, gęstość, scoring (0$)
2. Google Enrichment - rating/reviews dla top-k POI per kategoria
3. Google Fallback - uzupełnienie brakujących kategorii

Optymalizuje koszt: ~$0.77 → ~$0.15-0.40 per analiza.
"""
import logging
from typing import Dict, List, Any, Tuple, Optional, Iterable
from dataclasses import dataclass

from .overpass_client import OverpassClient, POI, MAX_POIS_PER_CATEGORY
from .google_places_client import GooglePlacesClient, google_types_to_badges, google_types_to_secondary
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
    'education': EnrichmentConfig(top_k=3, enrich=True, max_distance_m=120, search_radius_m=120),
    'health': EnrichmentConfig(top_k=3, enrich=True, max_distance_m=120, search_radius_m=120),
    'food': EnrichmentConfig(top_k=3, enrich=True, max_distance_m=150, search_radius_m=150),
    'transport': EnrichmentConfig(top_k=3, enrich=False),  # OSM wystarczy
    'nature_place': EnrichmentConfig(top_k=2, enrich=True, max_distance_m=150, search_radius_m=150),  # Parki
    'nature_background': EnrichmentConfig(top_k=0, enrich=False),  # Metryki, nie POI
    'leisure': EnrichmentConfig(top_k=3, enrich=True, max_distance_m=80, search_radius_m=80),
    'finance': EnrichmentConfig(top_k=2, enrich=False),
}

# Typy Google do fallbacku per kategoria (minimalne)
FALLBACK_TYPES = {
    'shops': ['supermarket', 'convenience_store', 'store'],
    'education': ['school'],
    'health': ['pharmacy', 'hospital', 'doctor', 'dentist', 'health'],
    'transport': ['bus_station', 'transit_station', 'train_station'],
    'food': ['restaurant', 'cafe', 'bakery', 'meal_takeaway'],
    'finance': ['bank', 'atm'],
    'nature_place': ['park'],
    'car_access': ['parking', 'gas_station'],
}

# Startup validation: every fallback type must be a valid Google type
def _validate_fallback_types():
    from .google_places_client import VALID_GOOGLE_TYPES
    for cat, types in FALLBACK_TYPES.items():
        for t in types:
            if t not in VALID_GOOGLE_TYPES:
                raise ValueError(
                    f"FALLBACK_TYPES['{cat}'] contains '{t}' which is NOT a valid Google Places API type. "
                    f"Check VALID_GOOGLE_TYPES in google_places_client.py."
                )

# Run on import (fail fast)
_validate_fallback_types()

# Progi coverage per kategoria
DEFAULT_COVERAGE_THRESHOLD = 2
COVERAGE_THRESHOLDS = {
    'food': 3,
    'finance': 2,
    'health': 2,
    'education': 2,
    'shops': 5,
    'transport': 2,
    'nature_place': 2,
}

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
        radius_by_category: Optional[Dict[str, int]] = None,
        enable_enrichment: bool = True,
        enable_fallback: bool = True,
        trace_ctx: 'AnalysisTraceContext | None' = None,
    ) -> Tuple[Dict[str, List[POI]], Dict[str, Any]]:
        """
        Pobiera POI używając strategii 3-warstwowej.
        
        Args:
            radius_m: Globalny promień pobierania (max)
            radius_by_category: Per-category radius limits (for filtering/fallback)
            trace_ctx: Optional trace context for structured logging
        
        Returns:
            tuple: (pois_by_category, metrics)
        """
        from .poi_filter import filter_by_radius, filter_by_membership
        from ..diagnostics import get_diag_logger, AnalysisTraceContext
        ctx = trace_ctx or AnalysisTraceContext()
        slog = get_diag_logger(__name__, ctx)
        
        # Domyślny radius_by_category = globalny promień dla wszystkich
        effective_radius = radius_by_category or {}
        
        # === WARSTWA 1: Overpass jako base ===
        slog.info(stage="geo", provider="overpass", op="layer1_base", message="Overpass base fetch", meta={"radius": radius_m})
        pois, metrics = self.overpass.get_pois_around(lat, lon, radius_m, trace_ctx=ctx)
        
        # Filtruj POI per-kategoria PRZED liczeniem coverage
        if effective_radius:
            pois = filter_by_radius(pois, effective_radius, default_radius=radius_m)
        
        # Policz coverage per kategoria (po filtrze!) + checkpoint
        coverage = {cat: len(items) for cat, items in pois.items()}
        for cat, items in pois.items():
            slog.checkpoint(stage="geo", category=cat, count_raw=coverage.get(cat, 0), count_kept=len(items), provider="overpass")
        
        # === WARSTWA 3: Fallback dla brakujących kategorii ===
        # (Robimy przed enrichment żeby mieć pełną listę do wzbogacenia)
        if enable_fallback:
            missing_categories = self._find_missing_categories(coverage)
            if missing_categories:
                slog.degraded(kind="FALLBACK_USED", provider="google", reason=f"Missing categories: {missing_categories}", stage="geo", impact="supplementing with Google data")
                self._apply_fallback(pois, lat, lon, effective_radius, radius_m, missing_categories, trace_ctx=ctx)
                # Re-filter after fallback (fallback already uses category radius)
                if effective_radius:
                    pois = filter_by_radius(pois, effective_radius, default_radius=radius_m)
        
        # === WARSTWA 2: Google enrichment dla top-k ===
        if enable_enrichment and self.google.api_key:
            slog.info(stage="geo", provider="google", op="layer2_enrichment", message="Enriching top-k POIs")
            enriched_count = self._enrich_top_k(pois, lat, lon, trace_ctx=ctx)
            slog.info(stage="geo", provider="google", op="enrichment_done", meta={"enriched_count": enriched_count})

        # Final dedup po enrichment/fallback
        self._dedupe_pois(pois)

        # Globalny merge/dedupe po place_id/osm_uid/grid
        pois = self._merge_places(pois)
        
        # === FINAL FILTERS (before returning) ===
        # 1. Filter by category membership (removes "Budynek" from food etc.)
        pois = filter_by_membership(pois)
        
        # 2. Filter by radius (after merge some distances may have been updated)
        if effective_radius:
            pois = filter_by_radius(pois, effective_radius, default_radius=radius_m)
        
        # Final checkpoint per category
        for cat, items in pois.items():
            slog.checkpoint(stage="geo", category=cat, count_raw=coverage.get(cat, 0), count_kept=len(items), provider="hybrid", op="final_counts")
        
        return pois, metrics
    
    def _find_missing_categories(self, coverage: Dict[str, int]) -> List[str]:
        """Znajduje kategorie z niewystarczającym coverage."""
        missing = []
        for cat in FALLBACK_TYPES:
            count = coverage.get(cat, 0)
            threshold = COVERAGE_THRESHOLDS.get(cat, DEFAULT_COVERAGE_THRESHOLD)
            if count < threshold:
                missing.append(cat)
        return missing
    
    def _apply_fallback(
        self,
        pois: Dict[str, List[POI]],
        lat: float,
        lon: float,
        radius_by_category: Dict[str, int],
        default_radius: int,
        categories: List[str],
        trace_ctx: 'AnalysisTraceContext | None' = None,
    ) -> None:
        """
        Uzupełnia brakujące kategorie przez Google Nearby Search.
        Używa per-category radius!
        """
        from ..diagnostics import get_diag_logger, AnalysisTraceContext
        ctx = trace_ctx or AnalysisTraceContext()
        slog = get_diag_logger(__name__, ctx)

        if not self.google.api_key:
            slog.degraded(kind="DEGRADED_PROVIDER", provider="google", reason="API key not configured, skipping fallback", stage="geo")
            return
        
        from ..cache import google_nearby_cache, TTLCache, normalize_coords

        for category in categories:
            types = FALLBACK_TYPES.get(category, [])
            if not types:
                continue

            # Upewnij się że kategoria istnieje w słowniku
            if category not in pois:
                pois[category] = []

            # USE CATEGORY-SPECIFIC RADIUS!
            cat_radius = radius_by_category.get(category, default_radius)
            slog.debug(stage="geo", provider="google", op="fallback_search", meta={"category": category, "types": types, "radius": cat_radius})

            try:
                # Batch: 1 request per kategoria z wieloma typami
                norm_lat, norm_lon = normalize_coords(lat, lon, precision=4)
                types_key = ','.join(sorted(types))
                cache_key = TTLCache.make_key('google_nearby', norm_lat, norm_lon, cat_radius, types_key)
                cached = google_nearby_cache.get(cache_key)
                if cached is not None:
                    results = cached
                else:
                    results = self.google._search_nearby(lat, lon, cat_radius, types, trace_ctx=ctx)
                    google_nearby_cache.set(cache_key, results)

                for place in results[:10]:  # Max 10 per category batch
                    poi = self.google._create_poi_from_place(place, category, lat, lon)
                    if poi and not self._is_duplicate(poi, pois[category]):
                        # Skip if outside category radius
                        if poi.distance_m > cat_radius:
                            continue
                        poi.tags['source'] = 'google_fallback'
                        poi.source = 'google_fallback'
                        pois[category].append(poi)
                        
            except Exception as e:
                slog.warning(stage="geo", provider="google", op="fallback_error", message=str(e), error_class="runtime", meta={"category": category, "types": types})
            
            # Sortuj po dystansie
            pois[category].sort(key=lambda p: p.distance_m)
    
    def _enrich_top_k(
        self,
        pois: Dict[str, List[POI]],
        lat: float,
        lon: float,
        trace_ctx: 'AnalysisTraceContext | None' = None,
    ) -> int:
        """
        Wzbogaca top-k POI per kategoria o rating i reviews z Google.
        Używa Find Place + Place Details z cache 7 dni.
        Deduplikuje po place_id.
        
        Returns:
            int: Liczba wzbogaconych POI
        """
        from ..cache import google_details_cache, TTLCache
        from ..diagnostics import get_diag_logger, AnalysisTraceContext
        ctx = trace_ctx or AnalysisTraceContext()
        slog = get_diag_logger(__name__, ctx)
        
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
                        slog.debug(stage="geo", provider="google", op="enrich_skip_generic", meta={"name": poi.name, "dist": poi.distance_m, "alts": category_count})
                        continue
                    else:
                        slog.debug(stage="geo", provider="google", op="enrich_try_generic", meta={"name": poi.name})
                
                # Używamy per-category search radius
                search_radius = config.search_radius_m
                
                try:
                    # Sprawdź cache najpierw (jeśli mamy place_id)
                    existing_place_id = poi.place_id or poi.tags.get('place_id')
                    cache_key = f"details:{existing_place_id}" if existing_place_id else None
                    details = None
                    
                    # Sprawdź czy ten place_id już był wzbogacony w tej sesji
                    if existing_place_id and existing_place_id in seen_place_ids:
                        slog.debug(stage="geo", provider="google", op="enrich_skip_dup", meta={"place_id": existing_place_id})
                        continue
                    
                    # Sprawdź cache
                    if cache_key:
                        details = google_details_cache.get(cache_key)
                        if details:
                            slog.debug(stage="geo", provider="google", op="enrich_cache_hit", meta={"name": poi.name})
                    
                    # Jeśli nie w cache, pobierz z API
                    if details is None:
                        # OPTYMALIZACJA: jeśli mamy place_id, użyj _get_place_details (1 req)
                        if existing_place_id:
                            slog.debug(stage="geo", provider="google", op="enrich_direct", meta={"name": poi.name})
                            details = self.google._get_place_details(
                                existing_place_id, 
                                ['rating', 'user_ratings_total', 'geometry', 'place_id', 'types']
                            )
                            if details:
                                details['place_id'] = existing_place_id  # Upewnij się że place_id jest w response
                        else:
                            # Brak place_id — Text Search zwraca rating/reviews w 1 req
                            details = self.google.find_place_details(
                                name=poi.name,
                                lat=poi.lat,
                                lon=poi.lon,
                                search_radius=search_radius,
                                trace_ctx=ctx,
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
                            poi.place_id = final_place_id
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
                                slog.debug(stage="geo", provider="google", op="enrich_reject_distance", meta={"name": poi.name, "distance": round(distance_to_google), "max": config.max_distance_m})
                                continue
                        
                        final_place_id = poi.tags.get('place_id') or details.get('place_id')
                        if final_place_id and final_place_id in seen_place_ids:
                            slog.debug(stage="geo", provider="google", op="enrich_skip_dup_post", meta={"place_id": final_place_id})
                            continue

                        rating = details.get('rating')
                        reviews = details.get('user_ratings_total') or 0
                        types = details.get('types') or poi.tags.get('types') or []
                        
                        # Dopisz do tags
                        poi.tags['rating'] = rating
                        poi.tags['reviews_count'] = reviews
                        poi.tags['user_ratings_total'] = reviews
                        poi.tags['enriched'] = True
                        if types:
                            poi.tags['types'] = types
                        
                        # Ustal finalne place_id i dodaj do seen (ZAWSZE po enrichment)
                        final_place_id = poi.tags.get('place_id') or details.get('place_id')
                        if final_place_id:
                            poi.tags['place_id'] = final_place_id
                            poi.place_id = final_place_id
                            seen_place_ids.add(final_place_id)

                        # Badges + secondary kategorie z Google types
                        if types:
                            poi.badges = list(set(poi.badges) | set(google_types_to_badges(types)))
                            secondary = google_types_to_secondary(types)
                            if poi.primary_category:
                                secondary = [c for c in secondary if c != poi.primary_category]
                            if secondary:
                                # Max 1 secondary (primary + secondary)
                                poi.secondary_categories = list(set(poi.secondary_categories) | set(secondary[:1]))

                        # Oznacz jako "mało opinii" jeśli poniżej progu
                        if reviews < config.min_reviews_to_show:
                            poi.tags['low_reviews'] = True
                        
                        enriched_count += 1
                        poi.tags['source'] = 'google_enriched'
                        poi.source = 'google_enriched'

                        logger.debug(
                            "Enriched: %s dist=%dm place_id=%s rating=%s reviews=%s",
                            poi.name, int(poi.distance_m), final_place_id, rating, reviews
                        )
                        
                except Exception as e:
                    slog.warning(stage="geo", provider="google", op="enrichment_error", message=str(e), error_class="runtime", meta={"name": poi.name})
        
        return enriched_count
    
    def _is_duplicate(self, new_poi: POI, existing: List[POI]) -> bool:
        """
        Sprawdza czy POI już istnieje.
        Priorytet: place_id > (nazwa + dystans < 50m).
        """
        new_place_id = new_poi.place_id or new_poi.tags.get('place_id')
        
        for poi in existing:
            # Sprawdź po place_id (najbardziej niezawodne)
            if new_place_id and (poi.place_id or poi.tags.get('place_id')) == new_place_id:
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
                place_id = poi.place_id or poi.tags.get('place_id')
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

    def _merge_places(self, pois: Dict[str, List[POI]]) -> Dict[str, List[POI]]:
        """Łączy POI z różnych źródeł w unikalne miejsca."""
        merged: Dict[str, POI] = {}
        merged_list: List[POI] = []

        def key_for(poi: POI) -> str:
            if poi.place_id:
                return f"place:{poi.place_id}"
            if poi.osm_uid:
                return f"osm:{poi.osm_uid}"
            name = (poi.name or '').strip().lower()
            grid = (round(poi.lat, 4), round(poi.lon, 4))
            if name in GENERIC_NAMES or poi.tags.get('_nameless'):
                sub = (poi.subcategory or '').lower()
                primary = poi.primary_category or ''
                return f"generic:{primary}:{sub}:{grid[0]}:{grid[1]}"
            return f"name:{name}:{grid[0]}:{grid[1]}"

        for items in pois.values():
            for poi in items:
                key = key_for(poi)
                if key not in merged:
                    merged[key] = poi
                    merged_list.append(poi)
                    continue
                base = merged[key]
                self._merge_poi(base, poi)

        return self._build_category_map(merged_list, pois.keys())

    def _merge_poi(self, base: POI, other: POI) -> None:
        """Scala dane dwóch POI w jedno miejsce."""
        merged_sources = base.source != other.source

        # Preferuj identyfikatory
        if not base.place_id and other.place_id:
            base.place_id = other.place_id
            base.tags['place_id'] = other.place_id
        if not base.osm_uid and other.osm_uid:
            base.osm_uid = other.osm_uid
            base.tags['osm_uid'] = other.osm_uid

        # Preferuj nazwę nie-generyczną
        if base.tags.get('_nameless') and not other.tags.get('_nameless') and other.name:
            base.name = other.name
            base.tags.pop('_nameless', None)

        # Preferuj primary_category z OSM (po osm_uid)
        if other.osm_uid and not base.osm_uid:
            base.primary_category = other.primary_category
        elif base.primary_category is None and other.primary_category:
            base.primary_category = other.primary_category

        # Ratings/reviews z Google (jeśli lepsze)
        base_reviews = base.tags.get('user_ratings_total') or base.tags.get('reviews_count') or 0
        other_reviews = other.tags.get('user_ratings_total') or other.tags.get('reviews_count') or 0
        if other.tags.get('rating') and (not base.tags.get('rating') or other_reviews > base_reviews):
            base.tags['rating'] = other.tags.get('rating')
            base.tags['reviews_count'] = other.tags.get('reviews_count') or other.tags.get('user_ratings_total')
            base.tags['user_ratings_total'] = other.tags.get('user_ratings_total') or other.tags.get('reviews_count')

        # Typy / badges
        base_types = set(base.tags.get('types', []) or [])
        other_types = set(other.tags.get('types', []) or [])
        if other_types:
            base.tags['types'] = list(base_types | other_types)

        base.badges = list(set(base.badges) | set(other.badges))

        # Kategorie secondary + score
        base.category_scores = {
            **base.category_scores,
            **{k: max(base.category_scores.get(k, 0), v) for k, v in other.category_scores.items()}
        }
        base.secondary_categories = list(set(base.secondary_categories) | set(other.secondary_categories))

        # Dystans
        if other.distance_m is not None:
            base.distance_m = min(base.distance_m, other.distance_m) if base.distance_m is not None else other.distance_m

        if merged_sources:
            base.source = 'merged'
            base.tags['source'] = 'merged'

        # Normalizuj primary/secondary
        self._normalize_categories(base)

        # Category field = primary (spójność)
        if base.primary_category:
            base.category = base.primary_category

    def _normalize_categories(self, poi: POI) -> None:
        """Utrzymuje max 2 kategorie (primary + secondary)."""
        primary = poi.primary_category
        if not primary and poi.category_scores:
            primary = max(poi.category_scores.items(), key=lambda kv: kv[1])[0]
            poi.primary_category = primary

        candidates = set(poi.secondary_categories)
        for cat in poi.category_scores.keys():
            if cat != primary:
                candidates.add(cat)

        if primary in candidates:
            candidates.remove(primary)

        secondary = []
        if candidates:
            if poi.category_scores:
                ordered = sorted(
                    candidates,
                    key=lambda c: poi.category_scores.get(c, 0),
                    reverse=True
                )
            else:
                ordered = sorted(candidates)
            secondary = ordered[:1]

        poi.secondary_categories = secondary

    def _build_category_map(
        self,
        places: List[POI],
        base_keys: Iterable[str]
    ) -> Dict[str, List[POI]]:
        """Buduje mapę kategorii z listy unikalnych miejsc."""
        category_keys = set(base_keys)
        for poi in places:
            if poi.primary_category:
                category_keys.add(poi.primary_category)
            for cat in poi.secondary_categories:
                category_keys.add(cat)

        categories: Dict[str, List[POI]] = {k: [] for k in category_keys}
        added: Dict[str, set] = {k: set() for k in category_keys}

        for poi in places:
            cats = []
            if poi.primary_category:
                cats.append(poi.primary_category)
            cats.extend(poi.secondary_categories or [])
            for cat in cats:
                if cat not in categories:
                    categories[cat] = []
                    added[cat] = set()
                pid = id(poi)
                if pid in added[cat]:
                    continue
                categories[cat].append(poi)
                added[cat].add(pid)

        for cat, items in categories.items():
            items.sort(key=lambda p: p.distance_m)
            categories[cat] = items[:MAX_POIS_PER_CATEGORY]

        return categories
