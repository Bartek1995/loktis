"""
Klient do Google Places API (Nearby Search).
Alternatywa dla Overpass do pobierania POI.
"""
import os
import requests
import math
import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Any, Tuple

from .nature_metrics import NatureMetrics
from .overpass_client import POI, MAX_POIS_PER_CATEGORY

logger = logging.getLogger(__name__)


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
    'fast_food': ('food', 'fast_food'),
    'bar': ('food', 'bar'),
    'meal_delivery': ('food', 'delivery'),
    'meal_takeaway': ('food', 'takeaway'),
    
    # Finance
    'bank': ('finance', 'bank'),
    'atm': ('finance', 'atm'),
}

BADGE_TYPE_WHITELIST = {
    'cafe', 'bakery', 'restaurant', 'fast_food', 'meal_takeaway', 'bar',
    'atm', 'bank', 'pharmacy', 'hospital', 'doctor', 'dentist', 'health',
    'gym', 'stadium', 'amusement_park', 'bowling_alley', 'movie_theater', 'spa',
    'park', 'natural_feature', 'campground',
    'supermarket', 'convenience_store', 'shopping_mall', 'store',
    'school', 'primary_school', 'secondary_school', 'university', 'library',
    'subway_station', 'bus_station', 'train_station', 'transit_station', 'light_rail_station',
}

SECONDARY_BY_GOOGLE_TYPE = [
    ('food', {'cafe', 'bakery', 'restaurant', 'fast_food', 'meal_takeaway', 'bar'}),
    ('finance', {'atm', 'bank'}),
    ('health', {'pharmacy', 'hospital', 'doctor', 'dentist', 'health'}),
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
    """Klient do pobierania POI z Google Places API."""
    
    NEARBY_SEARCH_URL = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"
    
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
    
    def __init__(self, api_key: Optional[str] = None):
        """Inicjalizacja z kluczem API."""
        self.api_key = api_key or os.environ.get('GOOGLE_PLACES_API_KEY')
        if not self.api_key:
            logger.warning("GOOGLE_PLACES_API_KEY not set!")
    
    def get_pois_around(
        self,
        lat: float,
        lon: float,
        radius_m: int = 500,
        trace_ctx: 'AnalysisTraceContext | None' = None,
    ) -> Tuple[Dict[str, List[POI]], Dict[str, Any]]:
        """
        Pobiera POI z Google Places API.
        
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
        
        # Wykonaj wyszukiwanie dla każdej kategorii
        for our_category, google_types in self.SEARCH_TYPES.items():
            for google_type in google_types:
                try:
                    results = self._search_nearby(lat, lon, radius_m, google_type, trace_ctx=ctx)
                    
                    for place in results:
                        poi = self._create_poi_from_place(place, our_category, lat, lon)
                        if poi:
                            pois_by_category[our_category].append(poi)
                            
                            # Aktualizuj nature metrics dla parków
                            if our_category == 'nature_place' and poi.subcategory == 'park':
                                nature_metrics.add_park(poi.distance_m)
                                
                except Exception as e:
                    slog.warning(stage="geo", provider="google", op="search_nearby", message=str(e), error_class="runtime", meta={"google_type": google_type})
        
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
        place_type: str,
        trace_ctx: 'AnalysisTraceContext | None' = None,
    ) -> List[dict]:
        """Wykonuje Nearby Search dla jednego typu."""
        from ..diagnostics import get_diag_logger, AnalysisTraceContext
        ctx = trace_ctx or AnalysisTraceContext()
        slog = get_diag_logger(__name__, ctx)

        params = {
            'location': f"{lat},{lon}",
            'radius': radius_m,
            'type': place_type,
            'key': self.api_key,
        }
        
        token = slog.req_start(provider="google", op="search_nearby", stage="geo", meta={"type": place_type})
        
        response = requests.get(self.NEARBY_SEARCH_URL, params=params, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        api_status = data.get('status', '')
        
        if api_status not in ['OK', 'ZERO_RESULTS']:
            slog.req_end(provider="google", op="search_nearby", stage="geo", status="error", request_token=token, http_status=response.status_code, provider_code=api_status, message=data.get('error_message', ''))
            return []
        
        results = data.get('results', [])
        slog.req_end(provider="google", op="search_nearby", stage="geo", status="ok", request_token=token, http_status=response.status_code, provider_code=api_status, meta={"results": len(results)})
        return results
    
    def _create_poi_from_place(
        self,
        place: dict,
        our_category: str,
        ref_lat: float,
        ref_lon: float
    ) -> Optional[POI]:
        """Tworzy POI z odpowiedzi Google Places."""
        try:
            location = place.get('geometry', {}).get('location', {})
            place_lat = location.get('lat')
            place_lon = location.get('lng')
            
            if not place_lat or not place_lon:
                return None
            
            name = place.get('name', 'Obiekt bez nazwy')
            
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
            
            return POI(
                lat=place_lat,
                lon=place_lon,
                name=name,
                category=our_category,
                subcategory=subcategory,
                distance_m=distance,
                tags={
                    'place_id': place.get('place_id'),
                    'rating': place.get('rating'),
                    'user_ratings_total': place.get('user_ratings_total'),
                    'types': place.get('types', []),
                    'source': 'google_fallback',
                },
                source='google_fallback',
                place_id=place.get('place_id'),
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
    
    FIND_PLACE_URL = "https://maps.googleapis.com/maps/api/place/findplacefromtext/json"
    PLACE_DETAILS_URL = "https://maps.googleapis.com/maps/api/place/details/json"
    
    def find_place_details(
        self,
        name: str,
        lat: float,
        lon: float,
        search_radius: int = 100,
        fields: List[str] = None
    ) -> Optional[dict]:
        """
        Znajduje miejsce używając Nearby Search + keyword, potem Place Details.
        Znacznie dokładniejsze niż text search - szuka w małym promieniu od POI.
        
        Args:
            name: Nazwa POI (np. "Biedronka")
            lat, lon: Lokalizacja POI z OSM
            search_radius: Promień wyszukiwania (domyślnie 100m)
            fields: Pola do pobrania z Details
        
        Returns:
            dict z rating, user_ratings_total, geometry, place_id lub None
        """
        if not self.api_key:
            return None
        
        fields = fields or ['rating', 'user_ratings_total', 'geometry', 'place_id', 'types']
        
        try:
            # 1. Nearby Search z keyword - szukamy w małym promieniu od POI
            place_id = self._find_nearby_by_keyword(name, lat, lon, search_radius)
            if not place_id:
                return None
            
            # 2. Place Details - pobierz rating/reviews + geometry
            return self._get_place_details(place_id, fields)
            
        except Exception as e:
            logger.warning("find_place_details error for '%s': %s", name, e)
            return None
    
    def _find_nearby_by_keyword(
        self, 
        keyword: str, 
        lat: float, 
        lon: float, 
        radius: int = 100,
        trace_ctx: 'AnalysisTraceContext | None' = None,
    ) -> Optional[str]:
        """
        Szuka miejsca przez Nearby Search z keyword.
        Zwraca place_id najbliższego wyniku.
        """
        from ..diagnostics import get_diag_logger, AnalysisTraceContext
        ctx = trace_ctx or AnalysisTraceContext()
        slog = get_diag_logger(__name__, ctx)

        params = {
            'location': f"{lat},{lon}",
            'radius': radius,
            'keyword': keyword,
            'key': self.api_key,
        }
        
        token = slog.req_start(provider="google", op="find_nearby_keyword", stage="geo", meta={"keyword": keyword})
        response = requests.get(self.NEARBY_SEARCH_URL, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        api_status = data.get('status', '')
        
        if api_status == 'OK' and data.get('results'):
            place_id = data['results'][0].get('place_id')
            slog.req_end(provider="google", op="find_nearby_keyword", stage="geo", status="ok", request_token=token, provider_code=api_status, meta={"place_id": place_id})
            return place_id
        
        slog.req_end(provider="google", op="find_nearby_keyword", stage="geo", status="ok", request_token=token, provider_code=api_status, meta={"results": 0})
        return None
    
    def _get_place_details(self, place_id: str, fields: List[str], trace_ctx: 'AnalysisTraceContext | None' = None) -> Optional[dict]:
        """Pobiera szczegóły miejsca z Place Details API."""
        from ..diagnostics import get_diag_logger, AnalysisTraceContext
        ctx = trace_ctx or AnalysisTraceContext()
        slog = get_diag_logger(__name__, ctx)

        params = {
            'place_id': place_id,
            'fields': ','.join(fields),
            'key': self.api_key,
        }
        
        token = slog.req_start(provider="google", op="place_details", stage="geo", meta={"place_id": place_id})
        response = requests.get(self.PLACE_DETAILS_URL, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        api_status = data.get('status', '')
        
        if api_status == 'OK' and data.get('result'):
            slog.req_end(provider="google", op="place_details", stage="geo", status="ok", request_token=token, provider_code=api_status)
            return data['result']
        
        slog.req_end(provider="google", op="place_details", stage="geo", status="ok", request_token=token, provider_code=api_status, meta={"result": None})
        return None
    
    def _empty_result(self) -> Tuple[Dict[str, List[POI]], Dict[str, Any]]:
        """Zwraca pustą strukturę wyników."""
        empty_metrics = NatureMetrics()
        return (
            {cat: [] for cat in ['shops', 'transport', 'education', 'health',
                                  'nature_place', 'nature_background', 'leisure',
                                  'food', 'finance', 'roads']},
            {'nature': empty_metrics.to_dict()}
        )
