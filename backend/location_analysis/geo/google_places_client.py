"""
Klient do Google Places API (New) — searchNearby + Place Details.
Używa nowych endpointów places.googleapis.com/v1/.
"""
import os
import time
import requests
import math
import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Any, Tuple

from .nature_metrics import NatureMetrics
from .overpass_client import POI, MAX_POIS_PER_CATEGORY

logger = logging.getLogger(__name__)


# =============================================================================
# VALID GOOGLE PLACES API (NEW) TYPES — single source of truth
# Reference: https://developers.google.com/maps/documentation/places/web-service/supported_types
# Any type used in SEARCH_TYPES or FALLBACK_TYPES MUST be in this set.
# =============================================================================
VALID_GOOGLE_TYPES = frozenset({
    # Shops
    'supermarket', 'convenience_store', 'shopping_mall', 'store',
    'grocery_or_supermarket', 'bakery', 'clothing_store', 'shoe_store',
    'hardware_store', 'electronics_store', 'furniture_store', 'book_store',
    'florist', 'pet_store',
    # Transport
    'subway_station', 'bus_station', 'train_station', 'transit_station',
    'light_rail_station',
    # Education
    'school', 'primary_school', 'secondary_school', 'university', 'library',
    # Health
    'pharmacy', 'hospital', 'doctor', 'dentist',
    'physiotherapist', 'veterinary_care',
    # Nature
    'park', 'natural_feature', 'campground',
    # Leisure
    'gym', 'stadium', 'amusement_park', 'bowling_alley', 'movie_theater', 'spa',
    # Food — NOTE: 'fast_food' is NOT a valid Google type!
    'restaurant', 'cafe', 'bar', 'meal_delivery', 'meal_takeaway',
    # Finance
    'bank', 'atm',
    # Car access
    'parking', 'gas_station',
})


# Mapowanie typów Google Places → nasze kategorie
GOOGLE_TO_CATEGORY = {
    # Shops
    'supermarket': ('shops', 'supermarket'),
    'grocery_or_supermarket': ('shops', 'supermarket'),
    'convenience_store': ('shops', 'convenience'),
    'shopping_mall': ('shops', 'mall'),
    'bakery': ('shops', 'bakery'),
    'clothing_store': ('shops', 'clothes'),
    'shoe_store': ('shops', 'shoes'),
    'hardware_store': ('shops', 'hardware'),
    'electronics_store': ('shops', 'electronics'),
    'furniture_store': ('shops', 'furniture'),
    'book_store': ('shops', 'books'),
    'florist': ('shops', 'florist'),
    'pet_store': ('shops', 'pet'),
    'store': ('shops', 'general'),
    
    # Transport
    'subway_station': ('transport', 'subway'),
    'bus_station': ('transport', 'bus_stop'),
    'train_station': ('transport', 'railway'),
    'transit_station': ('transport', 'transit'),
    'light_rail_station': ('transport', 'tram_stop'),
    
    # Education
    'school': ('education', 'school'),
    'primary_school': ('education', 'school'),
    'secondary_school': ('education', 'school'),
    'university': ('education', 'university'),
    'library': ('education', 'library'),
    
    # Health
    'pharmacy': ('health', 'pharmacy'),
    'hospital': ('health', 'hospital'),
    'doctor': ('health', 'doctors'),
    'dentist': ('health', 'dentist'),
    'health': ('health', 'clinic'),
    
    # Nature
    'park': ('nature_place', 'park'),
    'natural_feature': ('nature_place', 'natural'),
    'campground': ('nature_place', 'campground'),
    
    # Leisure
    'gym': ('leisure', 'fitness_centre'),
    'stadium': ('leisure', 'stadium'),
    'amusement_park': ('leisure', 'amusement'),
    'bowling_alley': ('leisure', 'bowling'),
    'movie_theater': ('leisure', 'cinema'),
    'spa': ('leisure', 'spa'),
    
    # Food
    'restaurant': ('food', 'restaurant'),
    'cafe': ('food', 'cafe'),
    # NOTE: 'fast_food' is NOT a valid Google type — removed
    'bar': ('food', 'bar'),
    'meal_delivery': ('food', 'delivery'),
    'meal_takeaway': ('food', 'takeaway'),
    
    # Finance
    'bank': ('finance', 'bank'),
    'atm': ('finance', 'atm'),
}

BADGE_TYPE_WHITELIST = {
    'cafe', 'bakery', 'restaurant', 'meal_takeaway', 'bar',
    'atm', 'bank', 'pharmacy', 'hospital', 'doctor', 'dentist',
    'gym', 'stadium', 'amusement_park', 'bowling_alley', 'movie_theater', 'spa',
    'park', 'natural_feature', 'campground',
    'supermarket', 'convenience_store', 'shopping_mall', 'store',
    'school', 'primary_school', 'secondary_school', 'university', 'library',
    'subway_station', 'bus_station', 'train_station', 'transit_station', 'light_rail_station',
}

SECONDARY_BY_GOOGLE_TYPE = [
    ('food', {'cafe', 'bakery', 'restaurant', 'meal_takeaway', 'bar'}),
    ('finance', {'atm', 'bank'}),
    ('health', {'pharmacy', 'hospital', 'doctor', 'dentist'}),
    ('leisure', {'gym', 'stadium', 'amusement_park', 'bowling_alley', 'movie_theater', 'spa'}),
    ('nature_place', {'park', 'natural_feature', 'campground'}),
    ('shops', {'supermarket', 'convenience_store', 'shopping_mall', 'store'}),
    ('education', {'school', 'primary_school', 'secondary_school', 'university', 'library'}),
    ('transport', {'subway_station', 'bus_station', 'train_station', 'transit_station', 'light_rail_station'}),
]


def google_types_to_badges(types: List[str]) -> List[str]:
    return [t for t in types if t in BADGE_TYPE_WHITELIST]


def google_types_to_secondary(types: List[str]) -> List[str]:
    secondary: List[str] = []
    types_set = set(types or [])
    for category, type_set in SECONDARY_BY_GOOGLE_TYPE:
        if types_set & type_set:
            secondary.append(category)
    return secondary


class GooglePlacesClient:
    """Klient do pobierania POI z Google Places API (New)."""
    
    NEARBY_SEARCH_URL = "https://places.googleapis.com/v1/places:searchNearby"
    PLACE_DETAILS_URL = "https://places.googleapis.com/v1/places/"
    
    # Pola do Nearby Search (Pro SKU — tańsze, bez rating/reviews)
    # Rating/reviews pobieramy osobno w enrichment (Text Search) — tylko dla top-k POI
    NEARBY_FIELD_MASK = ",".join([
        "places.id",
        "places.displayName",
        "places.location",
        "places.types",
    ])
    
    # Pola do Place Details (Enterprise SKU)
    DETAILS_FIELD_MASK = ",".join([
        "id",
        "displayName",
        "location",
        "types",
        "rating",
        "userRatingCount",
    ])
    
    # Typy Google do wyszukiwania per kategoria
    SEARCH_TYPES = {
        'shops': ['supermarket', 'convenience_store', 'shopping_mall', 'store'],
        'transport': ['subway_station', 'bus_station', 'train_station', 'transit_station'],
        'education': ['school', 'university', 'library'],
        'health': ['pharmacy', 'hospital', 'doctor', 'dentist'],
        'nature_place': ['park', 'natural_feature', 'campground'],
        'leisure': ['gym', 'stadium', 'movie_theater'],
        'food': ['restaurant', 'cafe', 'bar'],
        'finance': ['bank', 'atm'],
    }
    
    MAX_RETRIES = 2  # fallback, overridden in __init__
    
    def __init__(self, api_key: Optional[str] = None):
        """Inicjalizacja z kluczem API (z config lub explicite)."""
        from ..app_config import get_config
        config = get_config()
        self.api_key = api_key or config.google_places_api_key or os.environ.get('GOOGLE_PLACES_API_KEY')
        self.MAX_RETRIES = config.google_max_retries
        self._enabled = config.google_places_enabled
        if not self.api_key:
            logger.warning("GOOGLE_PLACES_API_KEY not set!")
    
    def _request_with_retry(
        self,
        method: str,
        url: str,
        max_retries: int = None,
        trace_ctx=None,
        **kwargs,
    ) -> requests.Response:
        """HTTP request z retry i exponential backoff dla 429/5xx."""
        retries = max_retries if max_retries is not None else self.MAX_RETRIES
        kwargs.setdefault('timeout', 10)
        
        last_response = None
        for attempt in range(retries + 1):
            try:
                response = requests.request(method, url, **kwargs)
                last_response = response
                
                # Retry na 429 (rate limit) i 5xx (server error)
                if response.status_code == 429 or response.status_code >= 500:
                    if attempt < retries:
                        wait = 0.5 * (2 ** attempt)
                        logger.debug("Retry %d/%d for %s (status=%d), waiting %.1fs",
                                     attempt + 1, retries, url, response.status_code, wait)
                        time.sleep(wait)
                        continue
                
                return response
                
            except (requests.Timeout, requests.ConnectionError) as e:
                last_response = None
                if attempt < retries:
                    wait = 0.5 * (2 ** attempt)
                    logger.debug("Retry %d/%d for %s (%s), waiting %.1fs",
                                 attempt + 1, retries, url, type(e).__name__, wait)
                    time.sleep(wait)
                    continue
                raise
        
        return last_response
    
    def _make_headers(self, field_mask: str) -> dict:
        """Tworzy nagłówki dla Places API (New)."""
        return {
            'X-Goog-Api-Key': self.api_key,
            'X-Goog-FieldMask': field_mask,
            'Content-Type': 'application/json',
        }
    
    def get_pois_around(
        self,
        lat: float,
        lon: float,
        radius_m: int = 500,
        trace_ctx: 'AnalysisTraceContext | None' = None,
    ) -> Tuple[Dict[str, List[POI]], Dict[str, Any]]:
        """
        Pobiera POI z Google Places API (New).
        
        Używa batch types per kategoria — 1 request per kategoria zamiast per typ.
        
        Returns:
            tuple: (pois_by_category, metrics) - ten sam format co OverpassClient
        """
        from ..diagnostics import get_diag_logger, AnalysisTraceContext
        ctx = trace_ctx or AnalysisTraceContext()
        slog = get_diag_logger(__name__, ctx)

        if not self.api_key:
            slog.error(stage="geo", provider="google", op="get_pois_around", message="API key not configured", error_class="config")
            return self._empty_result()
        
        pois_by_category: Dict[str, List[POI]] = {
            'shops': [], 'transport': [], 'education': [], 'health': [],
            'nature_place': [], 'nature_background': [], 'leisure': [],
            'food': [], 'finance': [], 'roads': []
        }
        
        nature_metrics = NatureMetrics()
        
        # Wykonaj wyszukiwanie per KATEGORIA (batch types!)
        for our_category, google_types in self.SEARCH_TYPES.items():
            try:
                results = self._search_nearby(lat, lon, radius_m, google_types, trace_ctx=ctx)
                
                for place in results:
                    poi = self._create_poi_from_place(place, our_category, lat, lon)
                    if poi:
                        pois_by_category[our_category].append(poi)
                        
                        # Aktualizuj nature metrics dla parków
                        if our_category == 'nature_place' and poi.subcategory == 'park':
                            nature_metrics.add_park(poi.distance_m)
                            
            except Exception as e:
                slog.warning(stage="geo", provider="google", op="search_nearby", message=str(e), error_class="runtime", meta={"google_types": google_types})
        
        # Deduplikacja i limitowanie
        for cat in pois_by_category:
            # Deduplikacja: place_id (primary) > name+distance_bucket (fallback)
            seen_place_ids = set()
            seen_fallback = set()
            unique_pois = []
            
            for poi in pois_by_category[cat]:
                place_id = poi.place_id or poi.tags.get('place_id')
                
                # Primary: dedupe po place_id
                if place_id:
                    if place_id in seen_place_ids:
                        continue
                    seen_place_ids.add(place_id)
                else:
                    # Fallback: name + distance bucket (~20m)
                    fallback_key = (poi.name.lower(), round(poi.distance_m / 20) * 20)
                    if fallback_key in seen_fallback:
                        continue
                    seen_fallback.add(fallback_key)
                
                unique_pois.append(poi)
            
            # Sortuj i limituj
            unique_pois.sort(key=lambda p: p.distance_m)
            pois_by_category[cat] = unique_pois[:MAX_POIS_PER_CATEGORY]
        
        # Oblicz density (przybliżone dla Google - mniej dokładne)
        nature_metrics.calculate_density(radius_m)
        
        return pois_by_category, {'nature': nature_metrics.to_dict()}
    
    def _search_nearby(
        self, 
        lat: float, 
        lon: float, 
        radius_m: int, 
        place_types: List[str],
        trace_ctx: 'AnalysisTraceContext | None' = None,
    ) -> List[dict]:
        """
        Wykonuje Nearby Search (New) dla listy typów.
        
        Nowe API akceptuje wiele typów w jednym zapytaniu (includedTypes),
        co redukuje liczbę requestów.
        """
        from ..diagnostics import get_diag_logger, AnalysisTraceContext
        ctx = trace_ctx or AnalysisTraceContext()
        slog = get_diag_logger(__name__, ctx)

        body = {
            'includedTypes': place_types,
            'maxResultCount': 20,
            'locationRestriction': {
                'circle': {
                    'center': {
                        'latitude': lat,
                        'longitude': lon,
                    },
                    'radius': float(radius_m),
                }
            },
            'languageCode': 'pl',
        }
        
        headers = self._make_headers(self.NEARBY_FIELD_MASK)
        
        token = slog.req_start(provider="google", op="search_nearby", stage="geo", meta={"types": place_types})
        
        response = self._request_with_retry(
            'POST', self.NEARBY_SEARCH_URL,
            json=body, headers=headers,
        )
        
        if response is None:
            slog.req_end(provider="google", op="search_nearby", stage="geo", status="error", request_token=token, http_status=0, message="All retries failed")
            return []
        
        if response.status_code != 200:
            slog.req_end(provider="google", op="search_nearby", stage="geo", status="error", request_token=token, http_status=response.status_code, message=response.text[:200])
            return []
        
        data = response.json()
        results = data.get('places', [])
        slog.req_end(provider="google", op="search_nearby", stage="geo", status="ok", request_token=token, http_status=response.status_code, meta={"results": len(results)})
        return results
    
    def _search_nearby_single_type(
        self,
        lat: float,
        lon: float,
        radius_m: int,
        place_type: str,
        trace_ctx: 'AnalysisTraceContext | None' = None,
    ) -> List[dict]:
        """Convenience wrapper — single type search."""
        return self._search_nearby(lat, lon, radius_m, [place_type], trace_ctx=trace_ctx)
    
    def _create_poi_from_place(
        self,
        place: dict,
        our_category: str,
        ref_lat: float,
        ref_lon: float
    ) -> Optional[POI]:
        """Tworzy POI z odpowiedzi Google Places API (New)."""
        try:
            location = place.get('location', {})
            place_lat = location.get('latitude')
            place_lon = location.get('longitude')
            
            if not place_lat or not place_lon:
                return None
            
            # displayName jest obiektem z polami text i languageCode
            display_name = place.get('displayName', {})
            name = display_name.get('text', 'Obiekt bez nazwy') if isinstance(display_name, dict) else str(display_name or 'Obiekt bez nazwy')
            
            # Znajdź najbardziej pasującą subkategorię
            subcategory = our_category  # fallback
            for gtype in place.get('types', []):
                if gtype in GOOGLE_TO_CATEGORY:
                    _, subcat = GOOGLE_TO_CATEGORY[gtype]
                    subcategory = subcat
                    break
            
            distance = self._haversine_distance(ref_lat, ref_lon, place_lat, place_lon)
            types = place.get('types', []) or []
            secondary = google_types_to_secondary(types)
            if our_category in secondary:
                secondary = [c for c in secondary if c != our_category]
            secondary = secondary[:1]
            badges = google_types_to_badges(types)
            
            # place_id w nowym API to pole 'id'
            place_id = place.get('id')
            
            return POI(
                lat=place_lat,
                lon=place_lon,
                name=name,
                category=our_category,
                subcategory=subcategory,
                distance_m=distance,
                tags={
                    'place_id': place_id,
                    'rating': place.get('rating'),
                    'user_ratings_total': place.get('userRatingCount'),
                    'types': types,
                    'source': 'google_fallback',
                },
                source='google_fallback',
                place_id=place_id,
                primary_category=our_category,
                secondary_categories=secondary,
                badges=badges,
            )
        except Exception as e:
            logger.warning("Error creating POI from Google place: %s", e)
            return None
    
    def _haversine_distance(
        self, 
        lat1: float, lon1: float, 
        lat2: float, lon2: float
    ) -> float:
        """Oblicza dystans w metrach między dwoma punktami."""
        R = 6371000  # Earth radius in meters
        
        phi1 = math.radians(lat1)
        phi2 = math.radians(lat2)
        delta_phi = math.radians(lat2 - lat1)
        delta_lambda = math.radians(lon2 - lon1)
        
        a = (math.sin(delta_phi / 2) ** 2 + 
             math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2)
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        
        return R * c
    
    # ===== METODY DLA HYBRID ENRICHMENT =====
    
    def find_place_details(
        self,
        name: str,
        lat: float,
        lon: float,
        search_radius: int = 100,
        fields: List[str] = None,
        trace_ctx: 'AnalysisTraceContext | None' = None,
    ) -> Optional[dict]:
        """
        Znajduje miejsce i pobiera szczegóły w JEDNYM zapytaniu Text Search.
        
        Optymalizacja: Text Search zwraca rating/reviews/location bezpośrednio,
        więc nie potrzebujemy osobnego Place Details (1 req zamiast 2).
        
        Returns:
            dict w formacie kompatybilnym ze starym API lub None
        """
        if not self.api_key:
            return None
        
        try:
            return self._text_search_place(name, lat, lon, search_radius, trace_ctx=trace_ctx)
        except Exception as e:
            logger.warning("find_place_details error for '%s': %s", name, e)
            return None
    
    def _text_search_place(
        self, 
        keyword: str, 
        lat: float, 
        lon: float, 
        radius: int = 100,
        trace_ctx: 'AnalysisTraceContext | None' = None,
    ) -> Optional[dict]:
        """
        Text Search (New) — szuka miejsca po nazwie i zwraca pełne dane
        (rating, reviews, location) w jednym zapytaniu.
        
        Zastępuje stary flow: _find_nearby_by_keyword + _get_place_details (2 req → 1 req).
        """
        from ..diagnostics import get_diag_logger, AnalysisTraceContext
        ctx = trace_ctx or AnalysisTraceContext()
        slog = get_diag_logger(__name__, ctx)

        text_search_url = "https://places.googleapis.com/v1/places:searchText"
        
        body = {
            'textQuery': keyword,
            'locationBias': {
                'circle': {
                    'center': {
                        'latitude': lat,
                        'longitude': lon,
                    },
                    'radius': float(radius),
                }
            },
            'maxResultCount': 1,
            'languageCode': 'pl',
        }
        
        # Pobieramy rating/reviews razem z lokalizacją — 1 request zamiast 2!
        field_mask = 'places.id,places.displayName,places.location,places.types,places.rating,places.userRatingCount'
        headers = self._make_headers(field_mask)
        
        token = slog.req_start(provider="google", op="find_nearby_keyword", stage="geo", meta={"keyword": keyword})
        
        response = self._request_with_retry(
            'POST', text_search_url,
            json=body, headers=headers,
        )
        
        if response is None or response.status_code != 200:
            status_code = response.status_code if response else 0
            slog.req_end(provider="google", op="find_nearby_keyword", stage="geo", status="error", request_token=token, http_status=status_code)
            return None
        
        data = response.json()
        places = data.get('places', [])
        
        if not places:
            slog.req_end(provider="google", op="find_nearby_keyword", stage="geo", status="ok", request_token=token, meta={"results": 0})
            return None
        
        place = places[0]
        place_id = place.get('id')
        slog.req_end(provider="google", op="find_nearby_keyword", stage="geo", status="ok", request_token=token, meta={"place_id": place_id})
        
        # Konwertuj na format kompatybilny ze starym API
        location = place.get('location', {})
        display_name = place.get('displayName', {})
        
        return {
            'place_id': place_id,
            'rating': place.get('rating'),
            'user_ratings_total': place.get('userRatingCount'),
            'types': place.get('types', []),
            'geometry': {
                'location': {
                    'lat': location.get('latitude'),
                    'lng': location.get('longitude'),
                }
            },
            'name': display_name.get('text', '') if isinstance(display_name, dict) else str(display_name or ''),
        }
    
    def _get_place_details(
        self, 
        place_id: str, 
        fields: List[str] = None,
        trace_ctx: 'AnalysisTraceContext | None' = None,
    ) -> Optional[dict]:
        """
        Pobiera szczegóły miejsca z Place Details API (New).
        
        Zwraca dict w formacie kompatybilnym ze starym API (z kluczami
        'place_id', 'rating', 'user_ratings_total', 'geometry', 'types')
        dla kompatybilności z resztą kodu.
        """
        from ..diagnostics import get_diag_logger, AnalysisTraceContext
        ctx = trace_ctx or AnalysisTraceContext()
        slog = get_diag_logger(__name__, ctx)

        # Place Details (New): GET places/{place_id}
        url = f"{self.PLACE_DETAILS_URL}{place_id}"
        
        headers = {
            'X-Goog-Api-Key': self.api_key,
            'X-Goog-FieldMask': self.DETAILS_FIELD_MASK,
        }
        
        token = slog.req_start(provider="google", op="place_details", stage="geo", meta={"place_id": place_id})
        
        response = self._request_with_retry(
            'GET', url, headers=headers,
        )
        
        if response is None or response.status_code != 200:
            status_code = response.status_code if response else 0
            message = response.text[:200] if response else "All retries failed"
            slog.req_end(provider="google", op="place_details", stage="geo", status="error", request_token=token, http_status=status_code, message=message)
            return None
        
        data = response.json()
        
        if not data.get('id'):
            slog.req_end(provider="google", op="place_details", stage="geo", status="ok", request_token=token, meta={"result": None})
            return None
        
        # Konwertuj na format kompatybilny ze starym API
        location = data.get('location', {})
        display_name = data.get('displayName', {})
        
        result = {
            'place_id': data.get('id'),
            'rating': data.get('rating'),
            'user_ratings_total': data.get('userRatingCount'),
            'types': data.get('types', []),
            'geometry': {
                'location': {
                    'lat': location.get('latitude'),
                    'lng': location.get('longitude'),
                }
            },
            'name': display_name.get('text', '') if isinstance(display_name, dict) else str(display_name or ''),
        }
        
        slog.req_end(provider="google", op="place_details", stage="geo", status="ok", request_token=token)
        return result
    
    def _empty_result(self) -> Tuple[Dict[str, List[POI]], Dict[str, Any]]:
        """Zwraca pustą strukturę wyników."""
        empty_metrics = NatureMetrics()
        return (
            {cat: [] for cat in ['shops', 'transport', 'education', 'health',
                                  'nature_place', 'nature_background', 'leisure',
                                  'food', 'finance', 'roads']},
            {'nature': empty_metrics.to_dict()}
        )
