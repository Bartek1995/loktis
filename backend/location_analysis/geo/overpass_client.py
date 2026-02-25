"""
Klient do Overpass API (OpenStreetMap).
Wersja zoptymalizowana: Single Batch Request (jedno zapytanie zamiast 8).
"""
import requests
import time
import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Tuple

from .nature_metrics import NatureMetrics


# Typy landcover do metryk nature_background (NIE do listy POI jako osobne obiekty)
LANDCOVER_TYPES = frozenset({'grass', 'meadow', 'forest', 'wood', 'recreation_ground'})
WATER_TYPES = frozenset({'water', 'beach', 'river', 'stream', 'canal', 'lake', 'pond', 'reservoir'})

# Typy do listy POI nature_place (parki, ogrody, rezerwaty - cele spaceru)
NATURE_PLACE_TYPES = frozenset({'park', 'garden', 'nature_reserve'})

# Max POI per category
MAX_POIS_PER_CATEGORY = 30

# Known shop types whitelist for subcategory normalization
KNOWN_SHOP_TYPES = frozenset({
    'supermarket', 'convenience', 'mall', 'bakery', 'clothes', 'hairdresser',
    'beauty', 'kiosk', 'alcohol', 'florist', 'greengrocer', 'butcher',
    'car_repair', 'doityourself', 'drugstore', 'books', 'electronics',
    'shoes', 'furniture', 'jewelry', 'optician', 'gift', 'hardware',
    'toys', 'sports', 'pet', 'chemist', 'perfumery', 'cosmetics',
    'tobacco', 'newsagent', 'stationery', 'deli', 'confectionery',
    'beverage', 'wine', 'garden_centre', 'mobile_phone', 'computer',
})


@dataclass
class POI:
    lat: float
    lon: float
    name: str
    category: str
    subcategory: str
    distance_m: float
    tags: dict
    source: str = "osm"
    primary_category: Optional[str] = None
    secondary_categories: List[str] = field(default_factory=list)
    category_scores: Dict[str, float] = field(default_factory=dict)
    badges: List[str] = field(default_factory=list)
    osm_uid: Optional[str] = None
    place_id: Optional[str] = None

class OverpassClient:
    """Klient do pobierania danych z OSM."""
    
    # Maksymalna liczba kategorii per POI (primary + secondary)
    MAX_CATEGORIES_PER_POI = 2
    SECONDARY_SCORE_RATIO = 0.7
    
    def __init__(self):
        from ..app_config import get_config
        config = get_config()
        self.ENDPOINTS = config.overpass_endpoints
        self.TIMEOUT = config.overpass_timeout
        self._current_endpoint_idx = 0
    
    # Konfiguracja kategorii (zachowujemy strukturę dla subkategorii i nazw)
    POI_QUERIES = {
        'shops': {
            'query': '["shop"]',
            'name': 'Sklepy',
            'alt_queries': [
                '["amenity"="fuel"]',
            ],
            'subcategories': {
                'supermarket': 'Supermarket',
                'convenience': 'Sklep spożywczy',
                'mall': 'Centrum handlowe',
                'bakery': 'Piekarnia',
                'clothes': 'Sklep odzieżowy',
                'hairdresser': 'Fryzjer',
                'beauty': 'Kosmetyczka',
                'kiosk': 'Kiosk',
                'alcohol': 'Sklep monopolowy',
                'florist': 'Kwiaciarnia',
                'greengrocer': 'Warzywniak',
                'butcher': 'Rzeźnik',
                'car_repair': 'Warsztat samochodowy',
                'doityourself': 'Sklep budowlany',
                'drugstore': 'Drogeria',
                'books': 'Księgarnia',
                'electronics': 'Elektronika',
                'shoes': 'Obuwie',
                'furniture': 'Meble',
                'jewelry': 'Jubiler',
                'optician': 'Optyk',
                'gift': 'Upominki',
            }
        },
        'transport': {
            'query': '["public_transport"="stop_position"]',
            'alt_queries': [
                '["highway"="bus_stop"]',
                '["railway"="tram_stop"]',
                '["railway"="station"]',
            ],
            'name': 'Transport publiczny',
            'subcategories': {
                'bus_stop': 'Przystanek autobusowy',
                'tram_stop': 'Przystanek tramwajowy',
                'station': 'Stacja kolejowa',
            }
        },
        'education': {
            'query': '["amenity"~"school|kindergarten|university"]',
            'name': 'Edukacja',
            'subcategories': {
                'school': 'Szkoła',
                'kindergarten': 'Przedszkole',
                'university': 'Uczelnia',
            }
        },
        'health': {
            'query': '["amenity"~"pharmacy|doctors|hospital|clinic|dentist|veterinary"]',
            'alt_queries': [
                '["healthcare"]',  # healthcare=doctor, healthcare=centre, etc.
            ],
            'name': 'Zdrowie',
            'subcategories': {
                'pharmacy': 'Apteka',
                'doctors': 'Lekarz',
                'doctor': 'Lekarz',  # healthcare=doctor
                'hospital': 'Szpital',
                'clinic': 'Przychodnia',
                'centre': 'Przychodnia',  # healthcare=centre
                'dentist': 'Dentysta',
                'veterinary': 'Weterynarz',
                'physiotherapist': 'Fizjoterapeuta',
                'optometrist': 'Optyk',
            }
        },
        'nature_place': {
            'query': '["leisure"~"park|garden|nature_reserve"]',
            'alt_queries': [
                '["boundary"="national_park"]',
            ],
            'name': 'Parki i ogrody',
            'subcategories': {
                'park': 'Park',
                'garden': 'Ogród',
                'nature_reserve': 'Rezerwat przyrody',
            }
        },
        'nature_background': {
            'query': '["landuse"~"forest|meadow|grass|recreation_ground"]',
            'alt_queries': [
                '["natural"~"wood|water|beach"]',
                '["waterway"~"river|stream|canal"]',
            ],
            'name': 'Zieleń i woda',
            'subcategories': {
                'forest': 'Las',
                'wood': 'Las',
                'meadow': 'Łąka',
                'water': 'Zbiornik wodny',
                'beach': 'Plaża',
                'grass': 'Trawnik',
                'recreation_ground': 'Teren rekreacyjny',
                'river': 'Rzeka',
                'stream': 'Strumień',
                'canal': 'Kanał',
                'lake': 'Jezioro',
                'pond': 'Staw',
                'reservoir': 'Zbiornik',
            }
        },
        'leisure': {
            'query': '["leisure"~"playground|fitness_centre|pitch|sports_centre|stadium|swimming_pool"]',
            'name': 'Sport i Rekreacja',
            'subcategories': {
                'playground': 'Plac zabaw',
                'fitness_centre': 'Siłownia',
                'pitch': 'Boisko',
                'sports_centre': 'Centrum sportowe',
                'stadium': 'Stadion',
                'swimming_pool': 'Basen',
            }
        },
        'food': {
            'query': '["amenity"~"restaurant|cafe|fast_food"]',
            'name': 'Gastronomia',
            'subcategories': {
                'restaurant': 'Restauracja',
                'cafe': 'Kawiarnia',
                'fast_food': 'Fast food',
            }
        },
        'finance': {
            'query': '["amenity"~"bank|atm"]',
            'name': 'Finanse',
            'subcategories': {
                'bank': 'Bank',
                'atm': 'Bankomat',
            }
        },
        'roads': {
            'query': '["highway"~"motorway|trunk|primary|secondary|tertiary"]',
            'alt_queries': [
                '["railway"~"tram|rail"]'
            ],
            'name': 'Ruch drogowy',
            'subcategories': {
                'motorway': 'Autostrada',
                'trunk': 'Droga ekspresowa',
                'primary': 'Droga główna',
                'secondary': 'Droga wojewódzka',
                'tertiary': 'Droga powiatowa',
                'tram': 'Tramwaj',
                'rail': 'Kolej',
            }
        },
        'car_access': {
            'query': '["amenity"~"parking|fuel"]',
            'alt_queries': [
                '["parking"]',
            ],
            'name': 'Dojazd samochodem',
            'subcategories': {
                'parking': 'Parking',
                'fuel': 'Stacja paliw',
                'underground': 'Parking podziemny',
                'surface': 'Parking naziemny',
                'multi-storey': 'Parking wielopoziomowy',
                'garage': 'Garaż',
            }
        },
    }


    def _classify_tags(self, tags: dict) -> Dict[str, float]:
        """Zwraca scoring kategorii na podstawie tagów."""
        scores: Dict[str, float] = {}

        def add(cat: str, pts: float) -> None:
            scores[cat] = scores.get(cat, 0.0) + pts

        shop = tags.get('shop')
        if shop:
            add('shops', 1.0)

        amenity = tags.get('amenity')
        if amenity in ['restaurant', 'cafe', 'fast_food']:
            add('food', 1.0)
        elif amenity == 'bar':
            add('food', 0.6)
        elif amenity in ['pharmacy', 'doctors', 'hospital', 'clinic', 'dentist', 'veterinary']:
            add('health', 1.0)
        elif amenity in ['school', 'kindergarten', 'university', 'college']:
            add('education', 1.0)
        elif amenity in ['bank', 'atm']:
            add('finance', 1.0)
        elif amenity == 'fuel':
            add('car_access', 1.0)
        elif amenity == 'parking':
            add('car_access', 1.0)
        
        # healthcare=* tag (doctor, centre, etc.)
        healthcare = tags.get('healthcare')
        if healthcare:
            add('health', 1.0)

        public_transport = tags.get('public_transport')
        if public_transport in ['stop_position', 'platform']:
            add('transport', 1.0)

        highway = tags.get('highway')
        if highway == 'bus_stop':
            add('transport', 1.0)

        railway = tags.get('railway')
        if railway in ['tram_stop', 'station']:
            add('transport', 1.0)
        if railway in ['tram', 'rail']:
            add('roads', 1.0)

        leisure = tags.get('leisure')
        if leisure in NATURE_PLACE_TYPES:
            add('nature_place', 1.0)
        elif leisure in ['playground', 'fitness_centre', 'pitch', 'sports_centre', 'stadium', 'swimming_pool']:
            add('leisure', 1.0)

        landuse = tags.get('landuse')
        if landuse in LANDCOVER_TYPES or landuse in WATER_TYPES:
            add('nature_background', 1.0)

        natural = tags.get('natural')
        if natural == 'wood' or natural in WATER_TYPES:
            add('nature_background', 1.0)

        water = tags.get('water')
        if water in WATER_TYPES:
            add('nature_background', 1.0)

        waterway = tags.get('waterway')
        if waterway in ['river', 'stream', 'canal']:
            add('nature_background', 1.0)

        boundary = tags.get('boundary')
        if boundary == 'national_park':
            add('nature_place', 1.0)

        if highway in ['motorway', 'trunk', 'primary', 'secondary', 'tertiary']:
            add('roads', 1.0)

        # parking=* tag (surface, underground, multi-storey, garage)
        parking_tag = tags.get('parking')
        if parking_tag:
            add('car_access', 1.0)

        return scores

    def _select_categories(
        self,
        scores: Dict[str, float]
    ) -> Tuple[Optional[str], List[str]]:
        """Wybiera primary + secondary kategorie na podstawie score."""
        if not scores:
            return None, []

        ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
        primary, primary_score = ranked[0]
        secondary: List[str] = []

        if len(ranked) > 1:
            for second_cat, second_score in ranked[1:]:
                if second_score >= self.SECONDARY_SCORE_RATIO * primary_score:
                    secondary.append(second_cat)
                if len(secondary) >= max(0, self.MAX_CATEGORIES_PER_POI - 1):
                    break

        return primary, secondary
    
    def _get_endpoint(self) -> str:
        return self.ENDPOINTS[self._current_endpoint_idx % len(self.ENDPOINTS)]
    
    def _rotate_endpoint(self):
        self._current_endpoint_idx += 1
    
    def get_pois_around(
        self,
        lat: float,
        lon: float,
        radius_m: int = 500,
        trace_ctx: 'AnalysisTraceContext | None' = None,
    ) -> Tuple[Dict[str, List[POI]], Dict[str, Any]]:
        """
        Pobiera punkty POI i metryki zieleni w okolicy (Single Batch Request).
        
        Returns:
            Tuple: (pois_by_category, metrics)
            - pois_by_category: Dict kategorii do list POI
            - metrics: Dict z metrykami (np. 'nature' -> NatureMetrics.to_dict())
        """
        from ..diagnostics import get_diag_logger, AnalysisTraceContext
        ctx = trace_ctx or AnalysisTraceContext()
        slog = get_diag_logger(__name__, ctx)
        
        # 1. Zbuduj wielkie Query (Union)
        union_parts = []
        
        for config in self.POI_QUERIES.values():
            q = config['query']
            # Używamy node i way (relation pomijamy dla wydajności, chyba że krytyczne)
            union_parts.append(f'node{q}(around:{radius_m},{lat},{lon});')
            union_parts.append(f'way{q}(around:{radius_m},{lat},{lon});')
            
            for alt_q in config.get('alt_queries', []):
                union_parts.append(f'node{alt_q}(around:{radius_m},{lat},{lon});')
                union_parts.append(f'way{alt_q}(around:{radius_m},{lat},{lon});')
        
        overpass_query = f"""
        [out:json][timeout:{self.TIMEOUT}];
        (
            {' '.join(union_parts)}
        );
        out center;
        """
        
        # 2. Wyślij request (z Retry Logic + Exponential Backoff)
        import random
        elements = []
        max_retries = 4
        
        for attempt in range(max_retries):
            endpoint = self._get_endpoint()
            token = slog.req_start(provider="overpass", op="batch_query", stage="geo", meta={"endpoint": endpoint, "attempt": attempt + 1})
            try:
                response = requests.post(
                    endpoint,
                    data={'data': overpass_query},
                    timeout=self.TIMEOUT * (attempt + 1),
                    headers={'Content-Type': 'application/x-www-form-urlencoded'}
                )
                response.raise_for_status()
                
                data = response.json()
                elements = data.get('elements', [])
                slog.req_end(provider="overpass", op="batch_query", stage="geo", status="ok", request_token=token, http_status=response.status_code, meta={"elements": len(elements)})
                break # Sukces
                
            except (requests.RequestException, ValueError) as e:
                self._rotate_endpoint()
                
                if attempt < max_retries - 1:
                    # Exponential backoff: 1s, 2s, 4s + random jitter 0-500ms
                    backoff = (2 ** attempt) + random.uniform(0, 0.5)
                    slog.req_end(
                        provider="overpass", op="batch_query", stage="geo",
                        status="retry", request_token=token,
                        error_class="http", retry_count=attempt + 1,
                        http_status=getattr(getattr(e, 'response', None), 'status_code', None),
                        message=f"Retrying in {backoff:.1f}s",
                        exc=str(e),
                    )
                    time.sleep(backoff)
                else:
                    slog.req_end(
                        provider="overpass", op="batch_query", stage="geo",
                        status="error", request_token=token,
                        error_class="http", retry_count=attempt + 1,
                        message="All retry attempts exhausted",
                        exc=str(e),
                        hint="All Overpass endpoints failed. Check network or try again later.",
                    )
                    # Zwracamy puste wyniki (fail gracefully)
                    empty_metrics = NatureMetrics()
                    empty_metrics.calculate_density(radius_m)
                    return {cat: [] for cat in self.POI_QUERIES}, {'nature': empty_metrics.to_dict()}

        # 3. Klasyfikuj i Parsuj wyniki lokalnie
        pois_by_category = {cat: [] for cat in self.POI_QUERIES}
        nature_metrics = NatureMetrics()
        seen_osm_uid = set()
        seen_grid_primary = set()
        # Dedup: node może być częścią way, a Overpass zwraca oba (out center)
        # Dodatkowo fallback po gridzie + primary_category.
        
        for elem in elements:
            tags = elem.get('tags', {})
            if not tags: continue
            
            # Pobierz koordynaty raz
            elem_lat = elem.get('lat') or elem.get('center', {}).get('lat')
            elem_lon = elem.get('lon') or elem.get('center', {}).get('lon')
            if not elem_lat: continue

            # Dedup po osm_uid
            elem_type = elem.get('type')
            elem_id = elem.get('id')
            osm_uid = f"{elem_type}:{elem_id}" if elem_type and elem_id else None
            if osm_uid and osm_uid in seen_osm_uid:
                continue
            if osm_uid:
                seen_osm_uid.add(osm_uid)

            # Klasyfikacja tagów -> primary/secondary kategorie
            scores = self._classify_tags(tags)
            primary_category, secondary_categories = self._select_categories(scores)
            if not primary_category:
                continue
            matched_cats = [primary_category] + secondary_categories

            # Fallback dedupe po gridzie (lat/lon + primary + rdzen tagow)
            core_tag = (
                tags.get('amenity') or
                tags.get('shop') or
                tags.get('leisure') or
                tags.get('highway') or
                tags.get('railway') or
                tags.get('natural') or
                tags.get('water') or
                tags.get('waterway') or
                tags.get('landuse') or
                ''
            )
            grid_key = (round(elem_lat, 5), round(elem_lon, 5), primary_category, core_tag)
            if grid_key in seen_grid_primary:
                continue
            seen_grid_primary.add(grid_key)

            # Oblicz dystans raz
            distance = self._haversine_distance(lat, lon, elem_lat, elem_lon)
            
            # Obsługa nature: rozdziel na POI vs metryki
            leisure = tags.get('leisure', '')
            landuse = tags.get('landuse', '')
            natural = tags.get('natural', '')
            water = tags.get('water', '')
            
            # Land cover -> metryki (nie POI)
            if landuse in LANDCOVER_TYPES:
                nature_metrics.add_landcover(landuse, distance)
            if natural == 'wood':
                nature_metrics.add_landcover('wood', distance)
            
            # Wody: preferuj waterway/water tag, fallback do natural
            waterway = tags.get('waterway', '')
            water_type = None
            if waterway in ('river', 'stream', 'canal'):
                water_type = waterway
            elif water in WATER_TYPES:
                water_type = water
            elif natural in WATER_TYPES:
                water_type = natural
            elif landuse in WATER_TYPES:
                water_type = landuse
            
            if water_type:
                nature_metrics.add_water(distance, water_type)
            
            # Park/garden/nature_reserve -> POI + aktualizuj metrykę nearest_park
            if leisure == 'park':
                nature_metrics.add_park(distance)
            
            for cat in matched_cats:
                # Dla nature_background: pomiń jako POI, tylko metryki
                # (landcover i woda są w metrykach, nie jako osobne POI na mapie)
                if cat == 'nature_background':
                    # Wody (water, beach, river, stream, reservoir) - TAK, pokazujemy na mapie jako POI
                    is_water = (
                        natural in WATER_TYPES or
                        waterway in ('river', 'stream', 'canal') or
                        water in WATER_TYPES or
                        landuse in WATER_TYPES
                    )
                    if not is_water:
                        # Pomiń land cover (grass, meadow, forest, wood) jako POI
                        continue
                
                poi = self._create_poi(
                    elem,
                    tags,
                    cat,
                    elem_lat,
                    elem_lon,
                    lat,
                    lon,
                    primary_category=primary_category,
                    secondary_categories=secondary_categories,
                    osm_uid=osm_uid,
                    category_scores=scores,
                )
                if poi:
                    pois_by_category[cat].append(poi)
        
        # 4. Oblicz density proxy
        nature_metrics.calculate_density(radius_m)
        
        # 5. Sortuj i limituj wynikowe listy
        for cat in pois_by_category:
            pois_by_category[cat].sort(key=lambda p: p.distance_m)
            pois_by_category[cat] = pois_by_category[cat][:MAX_POIS_PER_CATEGORY]
            
        return pois_by_category, {'nature': nature_metrics.to_dict()}

    def _match_categories(self, tags: dict) -> List[str]:
        """Sprawdza, do jakich kategorii pasuje dany obiekt na podstawie tagów."""
        scores = self._classify_tags(tags)
        primary, secondary = self._select_categories(scores)
        if not primary:
            return []
        return [primary] + secondary

    def _create_poi(
        self,
        elem: dict,
        tags: dict,
        category: str,
        lat: float,
        lon: float,
        ref_lat: float,
        ref_lon: float,
        primary_category: Optional[str] = None,
        secondary_categories: Optional[List[str]] = None,
        osm_uid: Optional[str] = None,
        category_scores: Optional[Dict[str, float]] = None,
    ) -> Optional[POI]:
        """Tworzy obiekt POI dla danej kategorii."""
        config = self.POI_QUERIES.get(category, {})
        
        # Nazwa
        name = tags.get('name', tags.get('brand'))
        
        # Subkategoria dla tej konkretnej kategorii
        subcategory = ''
        
        # Logika wyboru subkategorii specyficzna dla kategorii
        if category == 'shops':
            raw_shop = tags.get('shop', '')
            # Normalize: 'yes' or unknown -> 'general'
            if raw_shop in ('yes', '') or raw_shop not in KNOWN_SHOP_TYPES:
                # Check if it's a fuel station
                if tags.get('amenity') == 'fuel':
                    subcategory = 'fuel_station'
                else:
                    subcategory = 'general' if raw_shop else ''
            else:
                subcategory = raw_shop
        elif category == 'transport':
            if tags.get('highway') == 'bus_stop': subcategory = 'bus_stop'
            elif tags.get('railway') == 'tram_stop': subcategory = 'tram_stop'
            elif tags.get('railway') == 'station': subcategory = 'station'
            else: subcategory = tags.get('public_transport', '')
        elif category == 'education':
            subcategory = tags.get('amenity', '')
        elif category == 'health':
            # Prioritize: amenity > healthcare
            subcategory = tags.get('amenity') or tags.get('healthcare') or ''
        elif category == 'nature_place':
            # Parki, ogrody, rezerwaty
            subcategory = tags.get('leisure', '')
        elif category == 'nature_background':
            # Las, łąka, woda - priorytet: landuse > waterway > water > natural
            subcategory = (
                tags.get('landuse') or
                tags.get('waterway') or
                tags.get('water') or
                tags.get('natural') or
                ''
            )
        elif category == 'leisure':
            subcategory = tags.get('leisure', '')
        elif category == 'food':
            subcategory = tags.get('amenity', '')
        elif category == 'finance':
            subcategory = tags.get('amenity', '')
        elif category == 'roads':
            subcategory = tags.get('highway') or tags.get('railway', '')
        elif category == 'car_access':
            # parking=surface/underground/multi-storey/garage, amenity=parking/fuel
            subcategory = tags.get('parking') or tags.get('amenity', '')
            
        # Tłumaczenie subkategorii
        subcategory_pl = config.get('subcategories', {}).get(subcategory)
        
        # Fallback formatowania
        if not subcategory_pl:
            subcategory_pl = subcategory.replace('_', ' ').capitalize()
        
        # Fallback nazwy - generuj z typu + adres
        if not name:
            # Zbierz adres jeśli dostępny
            street = tags.get('addr:street', '')
            housenumber = tags.get('addr:housenumber', '')
            address_part = ''
            if street:
                address_part = f" ({street}"
                if housenumber:
                    address_part += f" {housenumber}"
                address_part += ")"
            
            # Generuj nazwę: "Typ (ulica nr)" lub tylko "Typ"
            if subcategory_pl:
                name = subcategory_pl.capitalize() + address_part
            elif address_part:
                name = f"Obiekt{address_part}"
            else:
                name = "Obiekt bez nazwy"
            
            # Oznacz jako bezimienne dla niższego priorytetu w raporcie
            tags['_nameless'] = True

        if osm_uid:
            tags['osm_uid'] = osm_uid
        tags['source'] = 'osm'

        distance = self._haversine_distance(ref_lat, ref_lon, lat, lon)
        
        return POI(
            lat=lat,
            lon=lon,
            name=name,
            category=category,
            subcategory=subcategory,
            distance_m=round(distance),
            tags=tags,
            source='osm',
            primary_category=primary_category or category,
            secondary_categories=secondary_categories or [],
            category_scores=category_scores or {},
            osm_uid=osm_uid,
        )

    def _haversine_distance(self, lat1, lon1, lat2, lon2):
        R = 6371000
        phi1 = math.radians(lat1)
        phi2 = math.radians(lat2)
        dphi = math.radians(lat2 - lat1)
        dlambda = math.radians(lon2 - lon1)
        a = math.sin(dphi / 2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2)**2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        return R * c
