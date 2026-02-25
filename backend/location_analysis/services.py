"""
Główny serwis analizy lokalizacji.
Orchestruje cały proces: parsowanie → geo → raport.
"""
import logging
from typing import Optional, Dict, Any

from .providers import get_provider_for_url, ProviderRegistry, PropertyData
from .geo import OverpassClient, GooglePlacesClient, HybridPOIProvider, POIAnalyzer
from .report_builder import ReportBuilder, AnalysisReport
from .cache import listing_cache, overpass_cache, TTLCache, normalize_coords
from .models import LocationAnalysis
from .personas import get_persona_by_string, PersonaType
from .scoring.profile_verdict import ProfileVerdictGenerator
from .scoring.profiles import get_profile, get_profiles_summary
from .scoring.profile_engine import create_scoring_engine
from .ai_insights import generate_decision_insights, generate_insights_from_factsheet
from .analysis_factsheet import build_factsheet_from_scoring
from .data_quality import build_data_quality_report
from .diagnostics import AnalysisTraceContext, get_diag_logger
from .geo.air_quality import get_air_quality_provider

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
        self.hybrid_provider = HybridPOIProvider(
            overpass_client=self.overpass_client,
            google_client=self.google_places_client
        )
        self.poi_analyzer = POIAnalyzer()
        self.report_builder = ReportBuilder()
    
    def _map_profile_to_persona(self, profile_key: str) -> str:
        """
        Mapuje nowy klucz profilu na starą personę dla legacy kompatybilności.
        """
        # Mapowanie nowych profili na stare persony
        mapping = {
            'urban': 'urban',
            'family': 'family',
            'quiet_green': 'family',  # Najbliżej family pod względem priorytetów
            'remote_work': 'urban',   # Praca z domu - miejski profil
            'active_sport': 'urban',  # Aktywny - miejski profil
            'car_first': 'family',    # Przedmieścia - rodzina
            'investor': 'investor',
        }
        return mapping.get(profile_key, 'family')
    
    def analyze_stream(self, url: str, radius: int = 500, use_cache: bool = True):
        """
        Generator analizy ze statusami.
        Yields: dict z eventem (status, message, result?)
        """
        import json
        
        ctx = AnalysisTraceContext()
        slog = get_diag_logger(__name__, ctx)
        slog.info(stage="init", op="analyze_stream", message="Start URL analysis", meta={"url": url, "radius": radius})
        
        # Walidacja URL
        yield json.dumps({'status': 'validating', 'message': 'Walidacja URL...'}) + '\n'
        is_valid, error = ProviderRegistry.validate_url(url)
        if not is_valid:
            slog.warning(stage="init", op="validate_url", status="invalid", message=error or "Invalid URL")
            yield json.dumps({'status': 'error', 'error': error}) + '\n'
            return
        
        # Cache check
        if use_cache:
            cache_key = TTLCache.make_key('report', url, radius)
            cached_report = listing_cache.get(cache_key)
            if cached_report:
                 slog.info(stage="init", op="cache_hit", message="Report served from cache")
                 yield json.dumps({'status': 'complete', 'result': cached_report}) + '\n'
                 return

        try:
            # 1. Parsuj
            ctx.start_stage("parsing")
            yield json.dumps({'status': 'parsing', 'message': 'Pobieranie ogłoszenia...'}) + '\n'
            listing = self._parse_listing(url, use_cache)
            ctx.end_stage("parsing")
            if listing.errors:
                 # Jeśli błędy krytyczne parsowania
                 pass
            
            # 2. Analiza okolicy
            neighborhood_score = None
            poi_stats = None
            pois = None
            
            if listing.has_precise_location and listing.latitude and listing.longitude:
                try:
                    ctx.start_stage("geo")
                    yield json.dumps({'status': 'map', 'message': f'Analiza mapy (promień {radius}m)...'}) + '\n'
                    pois, metrics = self._get_pois(
                        listing.latitude,
                        listing.longitude,
                        radius,
                        use_cache
                    )
                    dur = ctx.end_stage("geo")
                    slog.info(stage="geo", op="get_pois", duration_ms=dur)
                    
                    ctx.start_stage("scoring")
                    yield json.dumps({'status': 'calculating', 'message': 'Obliczanie wyników...'}) + '\n'
                    neighborhood_score = self.poi_analyzer.analyze(pois, metrics)
                    poi_stats = self.poi_analyzer.get_statistics(pois)
                    dur = ctx.end_stage("scoring")
                    slog.info(stage="scoring", op="analyze", duration_ms=dur)
                    
                except Exception as e:
                    slog.error(stage="geo", op="neighborhood", message=str(e), error_class="runtime")
                    listing.errors.append("Nie udało się przeanalizować okolicy.")
            else:
                 slog.info(stage="geo", op="skip", message="No precise location")
                 yield json.dumps({'status': 'info', 'message': 'Brak dokładnej lokalizacji - pomijam mapę.'}) + '\n'

            # 3. Buduj raport
            ctx.start_stage("report")
            yield json.dumps({'status': 'generating', 'message': 'Generowanie raportu końcowego...'}) + '\n'
            report = self.report_builder.build(
                property_input=listing,
                neighborhood_score=neighborhood_score,
                poi_stats=poi_stats,
                all_pois=pois,
                air_quality=self._fetch_air_quality(listing.latitude, listing.longitude, slog) if listing.has_precise_location and listing.latitude else None,
            )
            ctx.end_stage("report")
            
            # 4. Save & Cache
            ctx.start_stage("save")
            self._save_to_db(url, listing, report)
            result = report.to_dict()
            if use_cache:
                listing_cache.set(TTLCache.make_key('report', url, radius), result, ttl=3600)
            ctx.end_stage("save")
            
            ctx.summary.emit(slog, ctx, status="ok")
            yield json.dumps({'status': 'complete', 'result': result}) + '\n'
            
        except Exception as e:
            slog.error(stage="pipeline", op="analyze_stream", message=str(e), exc=type(e).__name__, error_class="runtime", hint="Check traceback in Django logs")
            ctx.summary.emit(slog, ctx, status="error")
            yield json.dumps({'status': 'error', 'error': str(e)}) + '\n'
    
    # Alias for backwards compatibility
    def analyze_listing_stream(self, url: str, radius: int = 500, use_cache: bool = True):
        """Alias for analyze_stream for URL-based listing analysis."""
        yield from self.analyze_stream(url, radius=radius, use_cache=use_cache)

    def analyze_location_stream(
        self,
        lat: float,
        lon: float,
        price: Optional[float],  # Opcjonalne - dane nieruchomości
        area_sqm: Optional[float],  # Opcjonalne - dane nieruchomości
        address: str,
        radius: int = 500,
        reference_url: str = None,
        user_profile: str = 'family',  # Legacy - mapujemy na profile_key
        poi_provider: str = 'overpass',
        profile_key: str = None,  # Nowy parametr - klucz profilu
        radius_overrides: Dict[str, int] = None,  # User-defined radius per category
    ):
        """
        Generator analizy lokalizacji (location-first model).
        Yields: dict z eventem (status, message, result?)
        
        Args:
            lat, lon: Koordynaty (wymagane)
            price: Cena nieruchomości (opcjonalna, od użytkownika)
            area_sqm: Metraż (opcjonalny, od użytkownika) 
            profile_key: Klucz nowego profilu (urban, family, quiet_green, remote_work, active_sport, car_first)
            user_profile: [LEGACY] Stary parametr - mapowany na profile_key jeśli profile_key nie podany
            radius_overrides: Opcjonalne nadpisanie promieni per kategoria (np. {'shops': 800})
        """
        import json
        
        ctx = AnalysisTraceContext()
        slog = get_diag_logger(__name__, ctx)
        
        try:
            # Mapowanie legacy user_profile -> profile_key
            effective_profile_key = profile_key or user_profile
            
            slog.info(
                stage="init", op="analyze_location_stream",
                message="Start location analysis",
                meta={"lat": lat, "lon": lon, "radius": radius, "profile": effective_profile_key, "poi_provider": poi_provider},
            )
            
            # Pobierz nowy profil konfiguracyjny
            profile = get_profile(effective_profile_key)
            
            # Apply user overrides to profile radii
            effective_radius_m = dict(profile.radius_m)  # Copy defaults
            if radius_overrides:
                for category, override_radius in radius_overrides.items():
                    if category in effective_radius_m:
                        effective_radius_m[category] = override_radius
                        slog.debug(stage="init", op="radius_override", meta={"category": category, "new": override_radius, "was": profile.radius_m.get(category)})

            # Ustal promien pobierania POI = max promien per kategoria (including overrides)
            profile_radius_max = max(effective_radius_m.values()) if effective_radius_m else radius
            fetch_radius = max(radius, profile_radius_max)
            
            # Legacy: pobierz też starą personę dla kompatybilności wstecznej
            # Mapujemy nowe profile_key na stare persony gdzie to możliwe
            legacy_persona_key = self._map_profile_to_persona(effective_profile_key)
            persona = get_persona_by_string(legacy_persona_key)
            
            yield json.dumps({
                'status': 'starting', 
                'message': f'Rozpoczynam analizę lokalizacji dla profilu: {profile.emoji} {profile.name}...'
            }) + '\n'
            
            # Twórz PropertyData z podanych danych (source='user')
            listing = PropertyData(
                url=reference_url or f"location://{lat},{lon}",
                title=address,
                price=price,  # Może być None
                area_sqm=area_sqm,  # Może być None
                latitude=lat,
                longitude=lon,
                has_precise_location=True,
                location=address,
            )
            # Oznacz źródło danych jako 'user' (nie provider)
            listing.source = 'user'
            
            # Oblicz price_per_sqm tylko jeśli oba są podane
            if price and area_sqm:
                listing.price_per_sqm = round(price / area_sqm, 2)
            
            # Analiza okolicy
            neighborhood_score = None
            poi_stats = None
            pois = None
            profile_scoring_result = None
            verdict = None
            ai_insights = None
            
            try:
                ctx.start_stage("geo")
                provider_label = 'Google Places' if poi_provider == 'google' else ('Hybrid' if poi_provider == 'hybrid' else 'Overpass')
                yield json.dumps({'status': 'map', 'message': f'Analiza mapy ({provider_label}, promień {fetch_radius}m)...'}) + '\n'
                pois, metrics, poi_cache_used = self._get_pois(
                    lat, lon, fetch_radius, 
                    use_cache=True, 
                    provider=poi_provider,
                    radius_by_category=effective_radius_m,  # Pass per-category radius!
                    trace_ctx=ctx,
                )
                geo_dur = ctx.end_stage("geo")
                slog.info(stage="geo", op="get_pois", provider=poi_provider, duration_ms=geo_dur, meta={"cache_used": poi_cache_used})

                # Debug: zrzut wykrytych POI (top 10 per kategoria)
                if logging.getLogger(__name__).isEnabledFor(logging.DEBUG):
                    for cat, items in (pois or {}).items():
                        if items:
                            slog.debug(stage="geo", op="poi_dump", meta={"category": cat, "count": len(items), "top3": [p.name for p in items[:3]]})
                
                # Build DataQualityReport for debugging and UI
                data_quality = build_data_quality_report(
                    pois_by_category=pois,
                    radii=effective_radius_m,
                    overpass_status="ok",  # TODO: track from hybrid provider
                    overpass_had_retry=False,  # TODO: track from hybrid provider
                    fallback_started=[],  # TODO: track from hybrid provider
                    fallback_contributed=[],  # TODO: track from hybrid provider
                    cache_used=poi_cache_used,
                    profile_weights=profile.weights,
                )
                
                ctx.start_stage("scoring")
                yield json.dumps({'status': 'calculating', 'message': 'Obliczanie scoringu bazowego...'}) + '\n'
                
                # 1. Standardowa analiza POI (surowe score'y) - dla kompatybilności
                neighborhood_score = self.poi_analyzer.analyze(pois, metrics)
                poi_stats = self.poi_analyzer.get_statistics(pois)
                scoring_dur = ctx.end_stage("scoring")
                slog.info(stage="scoring", op="base_scoring", duration_ms=scoring_dur)
                
                yield json.dumps({
                    'status': 'profile', 
                    'message': f'Przeliczanie dla profilu: {profile.emoji} {profile.name}...'
                }) + '\n'
                
                # 2. NOWY: Profile-based scoring z krzywymi spadku
                ctx.start_stage("profile_scoring")
                profile_engine = create_scoring_engine(effective_profile_key, radius_overrides)
                profile_scoring_result = profile_engine.calculate(
                    pois_by_category=pois,
                    quiet_score=neighborhood_score.quiet_score or 50.0,
                    nature_metrics=metrics.get('nature'),
                    base_neighborhood_score=neighborhood_score.total_score,
                )
                ctx.end_stage("profile_scoring")
                
                # 3. Generuj werdykt decyzyjny (używamy nowego profilu)
                ctx.start_stage("verdict")
                verdict_generator = ProfileVerdictGenerator()
                verdict = verdict_generator.generate(profile_scoring_result, profile)
                verdict_dur = ctx.end_stage("verdict")
                
                slog.info(
                    stage="verdict", op="profile_verdict", duration_ms=verdict_dur,
                    meta={"score": round(profile_scoring_result.total_score, 1), "verdict": verdict.level.value, "profile": effective_profile_key},
                )
                
                # 4. NOWE: Generuj AI insights (Single Source of Truth architecture)
                ctx.start_stage("ai")
                yield json.dumps({'status': 'ai', 'message': 'Generowanie opisów AI...'}) + '\n'
                try:
                    # Build canonical factsheet - the ONLY input AI receives
                    quiet = neighborhood_score.quiet_score or 50.0
                    factsheet = build_factsheet_from_scoring(
                        profile=profile,
                        scoring_result=profile_scoring_result,
                        verdict=verdict,
                        quiet_score=quiet,
                        pois_by_category=pois,
                        listing=listing,
                    )
                    
                    # Generate AI insights from factsheet (not raw data)
                    ai_insights = generate_insights_from_factsheet(factsheet)
                    ai_dur = ctx.end_stage("ai")
                    
                    if ai_insights:
                        slog.info(stage="ai", op="insights_generated", duration_ms=ai_dur, meta={"summary_len": len(ai_insights.summary)})
                except Exception as ai_error:
                    ctx.end_stage("ai")
                    slog.warning(stage="ai", op="insights_failed", message=str(ai_error), error_class="runtime")
                    ai_insights = None
                
            except Exception as e:
                slog.error(stage="geo", op="neighborhood", message=str(e), exc=type(e).__name__, error_class="runtime", hint="POI fetch or scoring failed")
                listing.errors.append("Nie udało się przeanalizować okolicy.")
            
            # Buduj raport
            ctx.start_stage("report")
            yield json.dumps({'status': 'generating', 'message': 'Generowanie raportu końcowego...'}) + '\n'
            report = self.report_builder.build(
                property_input=listing,
                neighborhood_score=neighborhood_score,
                poi_stats=poi_stats,
                all_pois=pois,
                air_quality=self._fetch_air_quality(lat, lon, slog),
            )
            ctx.end_stage("report")
            
            # Dodaj parametry generowania raportu
            from datetime import datetime
            report.generation_params = {
                'generated_at': datetime.now().isoformat(),
                'profile': {
                    'key': effective_profile_key,
                    'name': profile.name,
                    'emoji': profile.emoji,
                },
                'radii': effective_radius_m,
                'fetch_radius': fetch_radius,
                'poi_provider': poi_provider,
                'poi_cache_used': poi_cache_used,  # DEV: czy dane POI były z cache
                'coords': {'lat': lat, 'lon': lon},
                # Data Quality Report for DEV mode
                'data_quality': data_quality.to_dict() if data_quality else None,
            }
            
            # Zapisz do bazy i pobierz public_id
            ctx.start_stage("save")
            saved_analysis = self._save_location_to_db(
                lat=lat,
                lon=lon,
                listing=listing,
                report=report,
                radius=fetch_radius,
                reference_url=reference_url,
                user_profile=user_profile,
                profile_key=effective_profile_key,
                profile_scoring_result=profile_scoring_result,
                verdict=verdict,
                ai_insights=ai_insights,
            )
            
            ctx.end_stage("save")
            result = report.to_dict()
            
            # Dodaj public_id do wyniku
            if saved_analysis:
                result['public_id'] = saved_analysis.public_id
            
            # Dodaj dane profilu i scoringu do wyniku
            result['profile'] = profile.to_dict()
            result['persona'] = persona.to_dict()  # Legacy
            
            if profile_scoring_result:
                result['scoring'] = profile_scoring_result.to_dict()
            if verdict:
                result['verdict'] = verdict.to_dict()
            
            # Dodaj AI insights do wyniku
            if ai_insights:
                result['ai_insights'] = {
                    'summary': ai_insights.summary,
                    'attention_points': ai_insights.attention_points,
                    'verification_checklist': ai_insights.verification_checklist,
                }
            
            ctx.summary.emit(slog, ctx, status="ok", extra_meta={"profile": effective_profile_key, "public_id": getattr(saved_analysis, 'public_id', None)})
            yield json.dumps({'status': 'complete', 'result': result}) + '\n'
            
        except Exception as e:
            slog.error(stage="pipeline", op="analyze_location_stream", message=str(e), exc=type(e).__name__, error_class="runtime", hint="Check traceback in Django logs")
            ctx.summary.emit(slog, ctx, status="error")
            yield json.dumps({'status': 'error', 'error': str(e)}) + '\n'
    
    def _parse_listing(self, url: str, use_cache: bool) -> PropertyData:
        """Parsuje ogłoszenie (z cache jeśli dostępne)."""
        cache_key = TTLCache.make_key('listing', url)
        
        if use_cache:
            cached = listing_cache.get(cache_key)
            if cached:
                logger.debug("Listing cache hit: %s", url)
                return cached
        
        provider = get_provider_for_url(url)
        if not provider:
            listing = PropertyData(url=url)
            listing.errors.append("Brak providera dla tej domeny.")
            return listing
        
        logger.debug("Parsing %s via %s", url, provider.name)
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
        provider: str = 'hybrid',
        radius_by_category: Dict[str, int] = None,  # NEW: per-category radius
        trace_ctx: 'AnalysisTraceContext | None' = None,
    ) -> tuple:
        """
        Pobiera POI i metryki (z cache jeśli dostępne).
        
        Args:
            provider: 'overpass', 'google', lub 'hybrid' (domyślny)
            radius_by_category: Per-category radius limits for filtering
            trace_ctx: Optional trace context for structured logging
        
        Returns:
            tuple: (pois_by_category, metrics)
        """
        # Normalizuj koordynaty dla lepszego cache hit rate (~11m grid)
        norm_lat, norm_lon = normalize_coords(lat, lon, precision=4)
        
        # Include radius_by_category in cache key if provided
        cache_suffix = ""
        if radius_by_category:
            # Create stable hash for category radii
            sorted_items = sorted(radius_by_category.items())
            cache_suffix = "|" + "|".join(f"{k}:{v}" for k, v in sorted_items)
        cache_key = TTLCache.make_key('pois', norm_lat, norm_lon, radius, provider) + cache_suffix
        
        if use_cache:
            cached = overpass_cache.get(cache_key)
            if cached:
                logger.debug("POI cache hit (%s): (%s, %s) r=%s", provider, norm_lat, norm_lon, radius)
                return cached[0], cached[1], True  # pois, metrics, cache_used=True
        
        # Wybór klienta
        if provider == 'hybrid':
            pois, metrics = self.hybrid_provider.get_pois_hybrid(
                lat, lon, radius,
                radius_by_category=radius_by_category,  # Pass per-category radius!
                trace_ctx=trace_ctx,
            )
        elif provider == 'google':
            pois, metrics = self.google_places_client.get_pois_around(lat, lon, radius, trace_ctx=trace_ctx)
        else:
            pois, metrics = self.overpass_client.get_pois_around(lat, lon, radius, trace_ctx=trace_ctx)
            # Apply filter for non-hybrid providers too
            if radius_by_category:
                from .geo.poi_filter import filter_by_radius
                pois = filter_by_radius(pois, radius_by_category, default_radius=radius)
        
        result = (pois, metrics)
        if use_cache:
            overpass_cache.set(cache_key, result, ttl=604800)  # 7 dni
        
        return pois, metrics, False  # cache_used=False
    
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
                    'checklist': report.checklist,
                    'source_provider': get_provider_for_url(url).name if get_provider_for_url(url) else '',
                    'parsing_errors': listing.errors,
                }
            )
            
            return result
            
        except Exception as e:
            logger.warning("DB save failed: %s", e)
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
        profile_key: str = None,
        profile_scoring_result = None,
        verdict = None,
        ai_insights = None,
    ) -> Optional[LocationAnalysis]:
        """Zapisuje wynik analizy lokalizacji do bazy danych."""
        try:
            # Generuj hash na podstawie lokalizacji
            url_hash = LocationAnalysis.generate_hash(lat=lat, lon=lon)
            url = reference_url or f"location://{lat},{lon}"

            # Dodaj public_id do report_data
            report_dict = report.to_dict()

            # Przygotuj dane scoringu
            scoring_data = profile_scoring_result.to_dict() if profile_scoring_result else {}
            verdict_data = verdict.to_dict() if verdict else {}
            
            # Wyciągnij category_scores z nowego scoringu
            category_scores = {}
            if profile_scoring_result:
                category_scores = {
                    cat: result.to_dict()
                    for cat, result in profile_scoring_result.category_results.items()
                }
            
            # Debug info
            scoring_debug = {
                'profile_scoring': scoring_data,
            }
            
            persona_adjusted_score = profile_scoring_result.total_score if profile_scoring_result else None
            profile_config_version = profile_scoring_result.profile_config_version if profile_scoring_result else 1
            
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
                    'checklist': report.checklist,
                    'source_provider': 'location',
                    'analysis_radius': radius,
                    'parsing_errors': listing.errors,
                    # Nowe pola profili
                    'profile_key': profile_key or user_profile,
                    'profile_config_version': profile_config_version,
                    'user_profile': user_profile,  # Legacy
                    'scoring_data': scoring_data,
                    'category_scores': category_scores,
                    'scoring_debug': scoring_debug,
                    'verdict_data': verdict_data,
                    'persona_adjusted_score': persona_adjusted_score,
                    'ai_insights_data': {
                        'summary': ai_insights.summary if ai_insights else '',
                        'quick_facts': ai_insights.quick_facts if ai_insights else [],
                        'attention_points': ai_insights.attention_points if ai_insights else [],  # Legacy alias
                        'verification_checklist': ai_insights.verification_checklist if ai_insights else [],
                        'recommendation_line': ai_insights.recommendation_line if ai_insights else '',
                        'target_audience': ai_insights.target_audience if ai_insights else '',
                        'disclaimer': ai_insights.disclaimer if ai_insights else '',  # Data quality warnings
                    } if ai_insights else {},
                }
            )
            
            # Dodaj public_id do report_data po zapisie
            if result.public_id:
                report_dict['public_id'] = result.public_id
                result.report_data = report_dict
                result.save(update_fields=['report_data'])
            
            logger.debug("Saved analysis: %s [profile: %s]", result.public_id, profile_key or user_profile)
            return result
            
        except Exception as e:
            logger.warning("DB save (location) failed: %s", e)
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
    
    def _fetch_air_quality(self, lat: float, lon: float, slog=None) -> Optional[Dict[str, Any]]:
        """
        Pobiera dane o jakości powietrza z providera.
        Zwraca None jeśli cokolwiek nie działa (graceful degradation).
        """
        try:
            provider = get_air_quality_provider('open_meteo')
            result = provider.get_air_quality(lat, lon)
            if result and slog:
                slog.info(
                    stage="geo", provider="open_meteo", op="air_quality",
                    message="Air quality data fetched",
                    meta={"aqi": result.get("aqi"), "period": result.get("period")}
                )
            return result
        except Exception as e:
            if slog:
                slog.warning(stage="geo", op="air_quality", message=f"Air quality fetch failed: {e}")
            return None


# Singleton
analysis_service = AnalysisService()
