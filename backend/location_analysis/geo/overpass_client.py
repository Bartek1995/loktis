"""
Klient do Overpass API (OpenStreetMap).
Wersja zoptymalizowana: Single Batch Request (jedno zapytanie zamiast 8).
"""
import requests
import time
import math
from dataclasses import dataclass
from typing import Dict, List, Optional, Any, Tuple

from .nature_metrics import NatureMetrics


# Typy landcover do metryk (NIE do listy POI)
LANDCOVER_TYPES = frozenset({'grass', 'meadow', 'forest', 'wood', 'recreation_ground'})
WATER_TYPES = frozenset({'water', 'beach', 'river', 'stream', 'canal', 'lake', 'pond', 'reservoir'})
# Typy do listy POI nature
NATURE_POI_TYPES = frozenset({'park', 'garden', 'nature_reserve'})

# Max POI per category
MAX_POIS_PER_CATEGORY = 30


@dataclass
class POI:
    lat: float
    lon: float
    name: str
    category: str
    subcategory: str
    distance_m: float
    tags: dict

class OverpassClient:
    """Klient do pobierania danych z OSM."""
    
    # Lista publicznych instancji Overpass API (Load Balancer)
    ENDPOINTS = [
        "https://overpass-api.de/api/interpreter",
        "https://lz4.overpass-api.de/api/interpreter",
        "https://z.overpass-api.de/api/interpreter",
        "https://maps.mail.ru/osm/tools/overpass/api/interpreter", 
    ]
    
    TIMEOUT = 60 # Zwiększony timeout dla dużego zapytania
    
    # Konfiguracja kategorii (zachowujemy strukturę dla subkategorii i nazw)
    POI_QUERIES = {
        'shops': {
            'query': '["shop"]',
            'name': 'Sklepy',
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
            'query': '["amenity"~"pharmacy|doctors|hospital|clinic"]',
            'name': 'Zdrowie',
            'subcategories': {
                'pharmacy': 'Apteka',
                'doctors': 'Lekarz',
                'hospital': 'Szpital',
                'clinic': 'Przychodnia',
            }
        },
        'nature': {
            'query': '["leisure"~"park|garden|nature_reserve"]',
            'alt_queries': [
                '["landuse"~"forest|meadow|grass|recreation_ground"]',
                '["natural"~"wood|water|beach"]',
                '["waterway"~"river|stream|canal"]',
            ],
            'name': 'Zieleń i Wypoczynek',
            'subcategories': {
                'park': 'Park',
                'garden': 'Ogród',
                'nature_reserve': 'Rezerwat przyrody',
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
    }
    
    def __init__(self):
        self._current_endpoint_idx = 0
    
    def _get_endpoint(self) -> str:
        return self.ENDPOINTS[self._current_endpoint_idx % len(self.ENDPOINTS)]
    
    def _rotate_endpoint(self):
        self._current_endpoint_idx += 1
    
    def get_pois_around(
        self,
        lat: float,
        lon: float,
        radius_m: int = 500
    ) -> Tuple[Dict[str, List[POI]], Dict[str, Any]]:
        """
        Pobiera punkty POI i metryki zieleni w okolicy (Single Batch Request).
        
        Returns:
            Tuple: (pois_by_category, metrics)
            - pois_by_category: Dict kategorii do list POI
            - metrics: Dict z metrykami (np. 'nature' -> NatureMetrics.to_dict())
        """
        
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
            try:
                response = requests.post(
                    self._get_endpoint(),
                    data={'data': overpass_query},
                    timeout=self.TIMEOUT * (attempt + 1),
                    headers={'Content-Type': 'application/x-www-form-urlencoded'}
                )
                response.raise_for_status()
                
                data = response.json()
                elements = data.get('elements', [])
                break # Sukces
                
            except (requests.RequestException, ValueError) as e:
                print(f"WARN: Overpass request failed on {self._get_endpoint()}: {e}")
                self._rotate_endpoint()
                
                if attempt < max_retries - 1:
                    # Exponential backoff: 1s, 2s, 4s + random jitter 0-500ms
                    backoff = (2 ** attempt) + random.uniform(0, 0.5)
                    print(f"INFO: Retrying in {backoff:.1f}s (attempt {attempt+2}/{max_retries})...")
                    time.sleep(backoff)
                else:
                    print("ERROR: Wszystkie próby pobrania danych nie powiodły się.")
                    # Zwracamy puste wyniki (fail gracefully)
                    empty_metrics = NatureMetrics()
                    empty_metrics.calculate_density(radius_m)
                    return {cat: [] for cat in self.POI_QUERIES}, {'nature': empty_metrics.to_dict()}

        # 3. Klasyfikuj i Parsuj wyniki lokalnie
        pois_by_category = {cat: [] for cat in self.POI_QUERIES}
        nature_metrics = NatureMetrics()
        
        # Cache przetworzonych id, żeby nie dublować (node może być częścią way, ale tu dostajemy node i way osobno z query)
        # Overpass 'out center' zwraca geometrię way jako center, więc jest ok.
        
        for elem in elements:
            tags = elem.get('tags', {})
            if not tags: continue
            
            # Pobierz koordynaty raz
            elem_lat = elem.get('lat') or elem.get('center', {}).get('lat')
            elem_lon = elem.get('lon') or elem.get('center', {}).get('lon')
            if not elem_lat: continue
            
            # Dopasuj kategorie (z uwzględnieniem metryk dla nature)
            matched_cats = self._match_categories(tags)
            
            # Oblicz dystans raz
            distance = self._haversine_distance(lat, lon, elem_lat, elem_lon)
            
            # Obsługa nature: rozdziel na POI vs metryki
            leisure = tags.get('leisure', '')
            landuse = tags.get('landuse', '')
            natural = tags.get('natural', '')
            
            # Land cover -> metryki (nie POI)
            if landuse in LANDCOVER_TYPES:
                nature_metrics.add_landcover(landuse, distance)
            if natural == 'wood':
                nature_metrics.add_landcover('wood', distance)
            
            # Wody: natural=water/beach lub waterway=river/stream/canal
            if natural in WATER_TYPES:
                nature_metrics.add_water(distance, natural)
            
            waterway = tags.get('waterway', '')
            if waterway in ('river', 'stream', 'canal'):
                nature_metrics.add_water(distance, waterway)
            
            # Park/garden/nature_reserve -> POI + aktualizuj metrykę nearest_park
            if leisure == 'park':
                nature_metrics.add_park(distance)
            
            for cat in matched_cats:
                # Dla nature: pomiń land cover (grass/meadow/forest), ale zostaw parki i wodę
                if cat == 'nature':
                    # Parki, ogrody, rezerwaty - TAK
                    is_valuable_nature_poi = leisure in NATURE_POI_TYPES
                    # Wody (water, beach, river, stream) - TAK, pokazujemy na mapie
                    is_water = natural in WATER_TYPES or waterway in ('river', 'stream', 'canal')
                    
                    # Pomiń tylko land cover (grass, meadow, forest, wood)
                    if not is_valuable_nature_poi and not is_water:
                        continue
                
                poi = self._create_poi(elem, tags, cat, elem_lat, elem_lon, lat, lon)
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
        matches = []
        
        # Shops
        if 'shop' in tags:
            matches.append('shops')
            
        # Transport (public_transport=stop_position OR highway=bus_stop OR railway=tram_stop/station)
        if (tags.get('public_transport') == 'stop_position' or 
            tags.get('highway') == 'bus_stop' or 
            tags.get('railway') in ['tram_stop', 'station']):
            matches.append('transport')
            
        # Education (amenity ~ school|kindergarten|university)
        amenity = tags.get('amenity', '')
        if amenity in ['school', 'kindergarten', 'university']:
            matches.append('education')
            
        # Health (amenity ~ pharmacy|doctors|hospital|clinic)
        if amenity in ['pharmacy', 'doctors', 'hospital', 'clinic']:
            matches.append('health')
            
        # Nature (leisure ~ park|garden|nature_reserve OR landuse ~ ... OR waterway ~ ...)
        leisure = tags.get('leisure', '')
        landuse = tags.get('landuse', '')
        natural = tags.get('natural', '')
        waterway = tags.get('waterway', '')
        
        if (leisure in ['park', 'garden', 'nature_reserve'] or
            landuse in ['forest', 'meadow', 'grass', 'recreation_ground'] or
            natural in ['wood', 'water', 'beach'] or
            waterway in ['river', 'stream', 'canal']):
            matches.append('nature')
            
        # Leisure (playground, fitness, pitch, etc)
        if leisure in ['playground', 'fitness_centre', 'pitch', 'sports_centre', 'stadium', 'swimming_pool']:
            matches.append('leisure')
            
        # Food
        if amenity in ['restaurant', 'cafe', 'fast_food']:
            matches.append('food')
            
        # Finance
        if amenity in ['bank', 'atm']:
            matches.append('finance')
            
        # Roads (highway ~ motorway... OR railway ~ tram|rail)
        highway = tags.get('highway', '')
        railway = tags.get('railway', '')
        if (highway in ['motorway', 'trunk', 'primary', 'secondary', 'tertiary'] or
            railway in ['tram', 'rail']):
            matches.append('roads')
            
        return matches

    def _create_poi(self, elem: dict, tags: dict, category: str, 
                    lat: float, lon: float, ref_lat: float, ref_lon: float) -> Optional[POI]:
        """Tworzy obiekt POI dla danej kategorii."""
        config = self.POI_QUERIES.get(category, {})
        
        # Nazwa
        name = tags.get('name', tags.get('brand'))
        
        # Subkategoria dla tej konkretnej kategorii
        subcategory = ''
        
        # Logika wyboru subkategorii specyficzna dla kategorii
        if category == 'shops':
            subcategory = tags.get('shop', '')
        elif category == 'transport':
            if tags.get('highway') == 'bus_stop': subcategory = 'bus_stop'
            elif tags.get('railway') == 'tram_stop': subcategory = 'tram_stop'
            elif tags.get('railway') == 'station': subcategory = 'station'
            else: subcategory = tags.get('public_transport', '')
        elif category == 'education':
            subcategory = tags.get('amenity', '')
        elif category == 'health':
            subcategory = tags.get('amenity', '')
        elif category == 'nature':
            # Priorytet: leisure > landuse > natural
            subcategory = tags.get('leisure') or tags.get('landuse') or tags.get('natural', '')
        elif category == 'leisure':
            subcategory = tags.get('leisure', '')
        elif category == 'food':
            subcategory = tags.get('amenity', '')
        elif category == 'finance':
            subcategory = tags.get('amenity', '')
        elif category == 'roads':
            subcategory = tags.get('highway') or tags.get('railway', '')
            
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

        distance = self._haversine_distance(ref_lat, ref_lon, lat, lon)
        
        return POI(
            lat=lat,
            lon=lon,
            name=name,
            category=category,
            subcategory=subcategory,
            distance_m=round(distance),
            tags=tags
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
