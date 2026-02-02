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
    'park': ('nature', 'park'),
    'natural_feature': ('nature', 'natural'),
    'campground': ('nature', 'campground'),
    
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


class GooglePlacesClient:
    """Klient do pobierania POI z Google Places API."""
    
    NEARBY_SEARCH_URL = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"
    
    # Typy Google do wyszukiwania per kategoria
    SEARCH_TYPES = {
        'shops': ['supermarket', 'convenience_store', 'shopping_mall', 'store'],
        'transport': ['subway_station', 'bus_station', 'train_station', 'transit_station'],
        'education': ['school', 'university', 'library'],
        'health': ['pharmacy', 'hospital', 'doctor', 'dentist'],
        'nature': ['park', 'natural_feature'],
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
        radius_m: int = 500
    ) -> Tuple[Dict[str, List[POI]], Dict[str, Any]]:
        """
        Pobiera POI z Google Places API.
        
        Returns:
            tuple: (pois_by_category, metrics) - ten sam format co OverpassClient
        """
        if not self.api_key:
            logger.error("Google Places API key not configured")
            return self._empty_result()
        
        pois_by_category: Dict[str, List[POI]] = {
            'shops': [], 'transport': [], 'education': [], 'health': [],
            'nature': [], 'leisure': [], 'food': [], 'finance': [], 'roads': []
        }
        
        nature_metrics = NatureMetrics()
        
        # Wykonaj wyszukiwanie dla każdej kategorii
        for our_category, google_types in self.SEARCH_TYPES.items():
            for google_type in google_types:
                try:
                    results = self._search_nearby(lat, lon, radius_m, google_type)
                    
                    for place in results:
                        poi = self._create_poi_from_place(place, our_category, lat, lon)
                        if poi:
                            pois_by_category[our_category].append(poi)
                            
                            # Aktualizuj nature metrics dla parków
                            if our_category == 'nature' and poi.subcategory == 'park':
                                nature_metrics.add_park(poi.distance_m)
                                
                except Exception as e:
                    logger.warning(f"Google Places search error for {google_type}: {e}")
        
        # Deduplikacja i limitowanie
        for cat in pois_by_category:
            # Deduplikacja po place_id (lub name+distance jako fallback)
            seen = set()
            unique_pois = []
            for poi in pois_by_category[cat]:
                key = (poi.name, round(poi.distance_m, 0))
                if key not in seen:
                    seen.add(key)
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
        place_type: str
    ) -> List[dict]:
        """Wykonuje Nearby Search dla jednego typu."""
        params = {
            'location': f"{lat},{lon}",
            'radius': radius_m,
            'type': place_type,
            'key': self.api_key,
        }
        
        logger.debug(f"Google Places search: {place_type} at ({lat}, {lon})")
        
        response = requests.get(self.NEARBY_SEARCH_URL, params=params, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        
        if data.get('status') not in ['OK', 'ZERO_RESULTS']:
            logger.warning(f"Google Places API error: {data.get('status')} - {data.get('error_message', '')}")
            return []
        
        return data.get('results', [])
    
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
                }
            )
        except Exception as e:
            logger.warning(f"Error creating POI from Google place: {e}")
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
    
    def _empty_result(self) -> Tuple[Dict[str, List[POI]], Dict[str, Any]]:
        """Zwraca pustą strukturę wyników."""
        empty_metrics = NatureMetrics()
        return (
            {cat: [] for cat in ['shops', 'transport', 'education', 'health', 
                                  'nature', 'leisure', 'food', 'finance', 'roads']},
            {'nature': empty_metrics.to_dict()}
        )
