"""
Główny serwis analizy ogłoszeń.
Orchestruje cały proces: parsowanie → geo → raport.
"""
import logging
from typing import Optional, Dict, Any

from .providers import get_provider_for_url, ProviderRegistry, ListingData
from .geo import OverpassClient, POIAnalyzer
from .report_builder import ReportBuilder, AnalysisReport
from .cache import listing_cache, overpass_cache, TTLCache
from .models import AnalysisResult

logger = logging.getLogger(__name__)


class AnalysisService:
    """
    Główny serwis do analizy ogłoszeń nieruchomości.
    """
    
    # Promień dla analizy okolicy (metry)
    NEIGHBORHOOD_RADIUS = 500
    
    def __init__(self):
        self.overpass_client = OverpassClient()
        self.poi_analyzer = POIAnalyzer()
        self.report_builder = ReportBuilder()
    
    def analyze_stream(self, url: str, radius: int = 500, use_cache: bool = True):
        """
        Generator analizy ze statusami.
        Yields: dict z eventem (status, message, result?)
        """
        import json
        
        # Walidacja URL
        yield json.dumps({'status': 'validating', 'message': 'Walidacja URL...'}) + '\n'
        is_valid, error = ProviderRegistry.validate_url(url)
        if not is_valid:
            yield json.dumps({'status': 'error', 'error': error}) + '\n'
            return
        
        # Cache check
        if use_cache:
            cache_key = TTLCache.make_key('report', url, radius)
            cached_report = listing_cache.get(cache_key)
            if cached_report:
                 yield json.dumps({'status': 'complete', 'result': cached_report}) + '\n'
                 return

        try:
            # 1. Parsuj
            yield json.dumps({'status': 'parsing', 'message': 'Pobieranie ogłoszenia...'}) + '\n'
            listing = self._parse_listing(url, use_cache)
            if listing.errors:
                 # Jeśli błędy krytyczne parsowania
                 pass
            
            # 2. Analiza okolicy
            neighborhood_score = None
            poi_stats = None
            pois = None
            
            if listing.has_precise_location and listing.latitude and listing.longitude:
                try:
                    yield json.dumps({'status': 'map', 'message': f'Analiza mapy (promień {radius}m)...'}) + '\n'
                    pois = self._get_pois(
                        listing.latitude,
                        listing.longitude,
                        radius,
                        use_cache
                    )
                    
                    yield json.dumps({'status': 'calculating', 'message': 'Obliczanie wyników...'}) + '\n'
                    neighborhood_score = self.poi_analyzer.analyze(pois)
                    poi_stats = self.poi_analyzer.get_statistics(pois)
                    
                except Exception as e:
                    logger.warning(f"Błąd analizy okolicy: {e}")
                    listing.errors.append("Nie udało się przeanalizować okolicy.")
            else:
                 yield json.dumps({'status': 'info', 'message': 'Brak dokładnej lokalizacji - pomijam mapę.'}) + '\n'

            # 3. Buduj raport
            yield json.dumps({'status': 'generating', 'message': 'Generowanie raportu końcowego...'}) + '\n'
            report = self.report_builder.build(
                listing=listing,
                neighborhood_score=neighborhood_score,
                poi_stats=poi_stats,
                all_pois=pois
            )
            
            # 4. Save & Cache
            self._save_to_db(url, listing, report)
            result = report.to_dict()
            if use_cache:
                listing_cache.set(TTLCache.make_key('report', url, radius), result, ttl=3600)
            
            yield json.dumps({'status': 'complete', 'result': result}) + '\n'
            
        except Exception as e:
            logger.exception(f"Błąd analizy dla {url}")
            yield json.dumps({'status': 'error', 'error': str(e)}) + '\n'
    
    def _parse_listing(self, url: str, use_cache: bool) -> ListingData:
        """Parsuje ogłoszenie (z cache jeśli dostępne)."""
        cache_key = TTLCache.make_key('listing', url)
        
        if use_cache:
            cached = listing_cache.get(cache_key)
            if cached:
                logger.info(f"Listing z cache: {url}")
                return cached
        
        provider = get_provider_for_url(url)
        if not provider:
            listing = ListingData(url=url)
            listing.errors.append("Brak providera dla tej domeny.")
            return listing
        
        logger.info(f"Parsowanie {url} przez {provider.name}")
        listing = provider.parse(url)
        
        if use_cache and not listing.errors:
            listing_cache.set(cache_key, listing, ttl=3600)
        
        return listing
    
    def _get_pois(
        self,
        lat: float,
        lon: float,
        radius: int,
        use_cache: bool
    ) -> Dict[str, list]:
        """Pobiera POI (z cache jeśli dostępne)."""
        cache_key = TTLCache.make_key('pois', lat, lon, radius)
        
        if use_cache:
            cached = overpass_cache.get(cache_key)
            if cached:
                logger.info(f"POI z cache: ({lat}, {lon}) r={radius}")
                return cached
        
        logger.info(f"Pobieranie POI z Overpass: ({lat}, {lon}) r={radius}")
        pois = self.overpass_client.get_pois_around(
            lat, lon, radius
        )
        
        if use_cache:
            overpass_cache.set(cache_key, pois, ttl=86400)  # 24h
        
        return pois
    
    def _save_to_db(
        self,
        url: str,
        listing: ListingData,
        report: AnalysisReport
    ) -> Optional[AnalysisResult]:
        """Zapisuje wynik do bazy danych."""
        try:
            url_hash = AnalysisResult.generate_url_hash(url)
            
            result, created = AnalysisResult.objects.update_or_create(
                url_hash=url_hash,
                defaults={
                    'url': url,
                    'title': listing.title,
                    'price': listing.price,
                    'price_per_sqm': listing.price_per_sqm,
                    'area_sqm': listing.area_sqm,
                    'rooms': listing.rooms,
                    'floor': listing.floor,
                    'location': listing.location,
                    'description': listing.description[:5000] if listing.description else '',
                    'images': listing.images,
                    'latitude': listing.latitude,
                    'longitude': listing.longitude,
                    'has_precise_location': listing.has_precise_location,
                    'neighborhood_score': report.neighborhood_score,
                    'neighborhood_data': report.neighborhood_details,
                    'report_data': report.to_dict(),
                    'pros': report.pros,
                    'cons': report.cons,
                    'checklist': report.checklist,
                    'source_provider': get_provider_for_url(url).name if get_provider_for_url(url) else '',
                    'parsing_errors': listing.errors,
                }
            )
            
            return result
            
        except Exception as e:
            logger.warning(f"Nie udało się zapisać do bazy: {e}")
            return None
    
    def _error_response(self, message: str) -> Dict[str, Any]:
        """Zwraca odpowiedź błędu."""
        return {
            'success': False,
            'errors': [message],
            'warnings': [],
            'tldr': {'pros': [], 'cons': []},
            'listing': {},
            'neighborhood': {
                'has_location': False,
                'score': None,
                'summary': '',
                'details': {},
                'poi_stats': {},
            },
            'checklist': [],
            'limitations': [],
        }


# Singleton
analysis_service = AnalysisService()
