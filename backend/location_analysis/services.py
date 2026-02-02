"""
Główny serwis analizy lokalizacji.
Orchestruje cały proces: parsowanie → geo → raport.
"""
import logging
from typing import Optional, Dict, Any

from .providers import get_provider_for_url, ProviderRegistry, PropertyData
from .geo import OverpassClient, GooglePlacesClient, POIAnalyzer
from .report_builder import ReportBuilder, AnalysisReport
from .cache import listing_cache, overpass_cache, TTLCache
from .models import LocationAnalysis
from .personas import get_persona_by_string, PersonaType
from .scoring import ScoringEngine, VerdictGenerator

logger = logging.getLogger(__name__)


class AnalysisService:
    """
    Główny serwis do analizy lokalizacji nieruchomości.
    """
    
    # Promień dla analizy okolicy (metry)
    NEIGHBORHOOD_RADIUS = 500
    
    def __init__(self):
        self.overpass_client = OverpassClient()
        self.google_places_client = GooglePlacesClient()
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
                    pois, metrics = self._get_pois(
                        listing.latitude,
                        listing.longitude,
                        radius,
                        use_cache
                    )
                    
                    yield json.dumps({'status': 'calculating', 'message': 'Obliczanie wyników...'}) + '\n'
                    neighborhood_score = self.poi_analyzer.analyze(pois, metrics)
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
    
    # Alias for backwards compatibility
    def analyze_listing_stream(self, url: str, radius: int = 500, use_cache: bool = True):
        """Alias for analyze_stream for URL-based listing analysis."""
        yield from self.analyze_stream(url, radius=radius, use_cache=use_cache)

    def analyze_location_stream(
        self,
        lat: float,
        lon: float,
        price: float,
        area_sqm: float,
        address: str,
        radius: int = 500,
        reference_url: str = None,
        user_profile: str = 'family',
        poi_provider: str = 'overpass',
    ):
        """
        Generator analizy lokalizacji (location-first model).
        Yields: dict z eventem (status, message, result?)
        """
        import json
        
        try:
            # Pobierz persona dla profilu
            persona = get_persona_by_string(user_profile)
            
            yield json.dumps({
                'status': 'starting', 
                'message': f'Rozpoczynam analizę lokalizacji dla profilu: {persona.emoji} {persona.name}...'
            }) + '\n'
            
            # Twórz sztuczny PropertyData z podanych danych
            listing = PropertyData(
                url=reference_url or f"location://{lat},{lon}",
                title=address,
                price=price,
                area_sqm=area_sqm,
                latitude=lat,
                longitude=lon,
                has_precise_location=True,
                location=address,
            )
            
            # Oblicz price_per_sqm
            if price and area_sqm:
                listing.price_per_sqm = round(price / area_sqm, 2)
            
            # Analiza okolicy
            neighborhood_score = None
            poi_stats = None
            pois = None
            scoring_result = None
            verdict = None
            
            try:
                provider_label = 'Google Places' if poi_provider == 'google' else 'Overpass'
                yield json.dumps({'status': 'map', 'message': f'Analiza mapy ({provider_label}, promień {radius}m)...'}) + '\n'
                pois, metrics = self._get_pois(lat, lon, radius, use_cache=True, provider=poi_provider)
                
                yield json.dumps({'status': 'calculating', 'message': 'Obliczanie scoringu bazowego...'}) + '\n'
                # 1. Najpierw standardowa analiza POI (surowe score'y)
                neighborhood_score = self.poi_analyzer.analyze(pois, metrics)
                poi_stats = self.poi_analyzer.get_statistics(pois)
                
                yield json.dumps({
                    'status': 'persona', 
                    'message': f'Przeliczanie dla profilu: {persona.emoji} {persona.name}...'
                }) + '\n'
                
                # 2. Teraz persona-based scoring
                scoring_engine = ScoringEngine(persona)
                scoring_result = scoring_engine.calculate(
                    category_scores=neighborhood_score.category_scores,
                    quiet_score=neighborhood_score.quiet_score or 50.0,
                )
                
                # 3. Generuj werdykt decyzyjny
                verdict_generator = VerdictGenerator()
                verdict = verdict_generator.generate(scoring_result, persona)
                
                logger.info(
                    f"Scoring dla ({lat}, {lon}) profil={user_profile}: "
                    f"base={scoring_result.base_score:.1f}, "
                    f"total={scoring_result.total_score:.1f}, "
                    f"verdict={verdict.level.value}"
                )
                
            except Exception as e:
                logger.warning(f"Błąd analizy okolicy: {e}")
                listing.errors.append("Nie udało się przeanalizować okolicy.")
            
            # Buduj raport
            yield json.dumps({'status': 'generating', 'message': 'Generowanie raportu końcowego...'}) + '\n'
            report = self.report_builder.build(
                listing=listing,
                neighborhood_score=neighborhood_score,
                poi_stats=poi_stats,
                all_pois=pois
            )
            
            # Zapisz do bazy i pobierz public_id
            saved_analysis = self._save_location_to_db(
                lat=lat,
                lon=lon,
                listing=listing,
                report=report,
                radius=radius,
                reference_url=reference_url,
                user_profile=user_profile,
                scoring_result=scoring_result,
                verdict=verdict,
            )
            
            result = report.to_dict()
            
            # Dodaj public_id do wyniku
            if saved_analysis:
                result['public_id'] = saved_analysis.public_id
            
            # Dodaj dane persona/scoring/verdict do wyniku
            result['persona'] = persona.to_dict()
            if scoring_result:
                result['scoring'] = scoring_result.to_dict()
            if verdict:
                result['verdict'] = verdict.to_dict()
            
            yield json.dumps({'status': 'complete', 'result': result}) + '\n'
            
        except Exception as e:
            logger.exception(f"Błąd analizy lokalizacji ({lat}, {lon})")
            yield json.dumps({'status': 'error', 'error': str(e)}) + '\n'
    
    def _parse_listing(self, url: str, use_cache: bool) -> PropertyData:
        """Parsuje ogłoszenie (z cache jeśli dostępne)."""
        cache_key = TTLCache.make_key('listing', url)
        
        if use_cache:
            cached = listing_cache.get(cache_key)
            if cached:
                logger.info(f"Listing z cache: {url}")
                return cached
        
        provider = get_provider_for_url(url)
        if not provider:
            listing = PropertyData(url=url)
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
        use_cache: bool,
        provider: str = 'overpass'
    ) -> tuple:
        """
        Pobiera POI i metryki (z cache jeśli dostępne).
        
        Args:
            provider: 'overpass' lub 'google'
        
        Returns:
            tuple: (pois_by_category, metrics)
        """
        cache_key = TTLCache.make_key('pois', lat, lon, radius, provider)
        
        if use_cache:
            cached = overpass_cache.get(cache_key)
            if cached:
                logger.info(f"POI z cache ({provider}): ({lat}, {lon}) r={radius}")
                return cached
        
        # Wybór klienta
        if provider == 'google':
            logger.info(f"Pobieranie POI z Google Places: ({lat}, {lon}) r={radius}")
            pois, metrics = self.google_places_client.get_pois_around(lat, lon, radius)
        else:
            logger.info(f"Pobieranie POI z Overpass: ({lat}, {lon}) r={radius}")
            pois, metrics = self.overpass_client.get_pois_around(lat, lon, radius)
        
        result = (pois, metrics)
        if use_cache:
            overpass_cache.set(cache_key, result, ttl=86400)  # 24h
        
        return result
    
    def _save_to_db(
        self,
        url: str,
        listing: PropertyData,
        report: AnalysisReport
    ) -> Optional[LocationAnalysis]:
        """Zapisuje wynik do bazy danych."""
        try:
            url_hash = LocationAnalysis.generate_url_hash(url)
            
            result, created = LocationAnalysis.objects.update_or_create(
                url_hash=url_hash,
                defaults={
                    'url': url,
                    'title': listing.title,
                    'price': listing.price,
                    'price_per_sqm': listing.price_per_sqm,
                    'area_sqm': listing.area_sqm,
                    'rooms': listing.rooms,
                    'floor': listing.floor,
                    'address': listing.location,
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
    
    def _save_location_to_db(
        self,
        lat: float,
        lon: float,
        listing: PropertyData,
        report: AnalysisReport,
        radius: int = 500,
        reference_url: str = None,
        user_profile: str = 'family',
        scoring_result = None,
        verdict = None,
    ) -> Optional[LocationAnalysis]:
        """Zapisuje wynik analizy lokalizacji do bazy danych."""
        try:
            # Generuj hash na podstawie lokalizacji
            url_hash = LocationAnalysis.generate_hash(lat=lat, lon=lon)
            url = reference_url or f"location://{lat},{lon}"
            
            # Dodaj public_id do report_data
            report_dict = report.to_dict()
            
            # Przygotuj dane persona-based
            scoring_data = scoring_result.to_dict() if scoring_result else {}
            verdict_data = verdict.to_dict() if verdict else {}
            persona_adjusted_score = scoring_result.total_score if scoring_result else None
            
            result, created = LocationAnalysis.objects.update_or_create(
                url_hash=url_hash,
                defaults={
                    'url': url,
                    'title': listing.title or listing.location,
                    'price': listing.price,
                    'price_per_sqm': listing.price_per_sqm,
                    'area_sqm': listing.area_sqm,
                    'rooms': listing.rooms,
                    'floor': listing.floor or '',
                    'address': listing.location,
                    'description': listing.description[:5000] if listing.description else '',
                    'images': listing.images or [],
                    'latitude': lat,
                    'longitude': lon,
                    'has_precise_location': True,
                    'neighborhood_score': report.neighborhood_score,
                    'neighborhood_data': report.neighborhood_details,
                    'report_data': report_dict,
                    'pros': report.pros,
                    'cons': report.cons,
                    'checklist': report.checklist,
                    'source_provider': 'location',
                    'analysis_radius': radius,
                    'parsing_errors': listing.errors,
                    # Persona-based data
                    'user_profile': user_profile,
                    'scoring_data': scoring_data,
                    'verdict_data': verdict_data,
                    'persona_adjusted_score': persona_adjusted_score,
                }
            )
            
            # Dodaj public_id do report_data po zapisie
            if result.public_id:
                report_dict['public_id'] = result.public_id
                result.report_data = report_dict
                result.save(update_fields=['report_data'])
            
            logger.info(f"Zapisano analizę lokalizacji: {result.public_id} [profil: {user_profile}]")
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
