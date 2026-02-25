"""
Widoki API dla analizy lokalizacji.
"""
import logging

from django.http import StreamingHttpResponse
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.viewsets import ReadOnlyModelViewSet
from rest_framework.response import Response
from rest_framework.decorators import action

from .models import LocationAnalysis
from .serializers import (
    AnalyzeListingRequestSerializer,
    AnalyzeLocationRequestSerializer,
    AnalysisReportSerializer,
    LocationAnalysisSerializer,
    LocationAnalysisDetailSerializer,
)
from .services import analysis_service
from .rate_limiter import rate_limit
from .providers import ProviderRegistry
from .scoring.profiles import get_profiles_summary, get_profile

logger = logging.getLogger(__name__)


class AnalyzeLocationView(APIView):
    """
    Endpoint do analizy lokalizacji (location-first model).
    Główny endpoint dla loktis.pl - użytkownik podaje lokalizację, cenę, metraż.
    
    POST /api/analyze-location/
    Returns: NDJSON stream
    """
    
    @rate_limit()
    def post(self, request):
        """Analizuje lokalizację (stream)."""
        serializer = AnalyzeLocationRequestSerializer(data=request.data)
        
        if not serializer.is_valid():
            return Response(
                {'errors': serializer.errors},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        lat = serializer.validated_data['latitude']
        lon = serializer.validated_data['longitude']
        price = serializer.validated_data['price']
        area_sqm = serializer.validated_data['area_sqm']
        address = serializer.validated_data['address']
        radius = serializer.validated_data.get('radius', 500)
        reference_url = serializer.validated_data.get('reference_url', None)
        profile_key = serializer.validated_data.get('profile_key', None)
        user_profile = serializer.validated_data.get('user_profile', 'family')
        poi_provider = serializer.validated_data.get('poi_provider', 'overpass')
        radius_overrides = serializer.validated_data.get('radius_overrides', None)
        enable_enrichment = serializer.validated_data.get('enable_enrichment', False)
        enable_fallback = serializer.validated_data.get('enable_fallback', True)
        
        # Użyj profile_key jeśli podany, inaczej fallback na user_profile
        effective_profile = profile_key or user_profile
        
        logger.info(f"Analiza lokalizacji (stream): ({lat}, {lon}) - {address} [profil: {effective_profile}, provider: {poi_provider}]")
        
        response = StreamingHttpResponse(
            analysis_service.analyze_location_stream(
                lat=lat,
                lon=lon,
                price=price,
                area_sqm=area_sqm,
                address=address,
                radius=radius,
                reference_url=reference_url,
                user_profile=user_profile,
                profile_key=profile_key,
                poi_provider=poi_provider,
                radius_overrides=radius_overrides,
                enable_enrichment=enable_enrichment,
                enable_fallback=enable_fallback,
            ),
            content_type='application/x-ndjson'
        )
        response['X-Accel-Buffering'] = 'no'
        return response


class AnalyzeListingView(APIView):
    """
    Endpoint do analizy ogłoszenia przez URL.
    Opcjonalna funkcjonalność - głównie dla integracji z Otodom/OLX.
    
    POST /api/analyze/
    Returns: NDJSON stream
    """
    
    @rate_limit()
    def post(self, request):
        """Analizuje ogłoszenie z podanego URL (stream)."""
        serializer = AnalyzeListingRequestSerializer(data=request.data)
        
        if not serializer.is_valid():
            return Response(
                {'errors': serializer.errors},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        url = serializer.validated_data['url']
        use_cache = serializer.validated_data.get('use_cache', True)
        radius = serializer.validated_data.get('radius', 500)
        
        logger.info(f"Analiza URL (stream): {url} (radius={radius})")
        
        response = StreamingHttpResponse(
            analysis_service.analyze_listing_stream(url, radius=radius, use_cache=use_cache),
            content_type='application/x-ndjson'
        )
        response['X-Accel-Buffering'] = 'no'
        return response


class ValidateURLView(APIView):
    """
    Endpoint do walidacji URL przed wysłaniem.
    
    POST /api/validate-url/
    """
    
    def post(self, request):
        url = request.data.get('url', '')
        is_valid, error = ProviderRegistry.validate_url(url)
        
        return Response({
            'valid': is_valid,
            'error': error if not is_valid else None,
            'allowed_domains': list(set(
                d.replace('www.', '') for d in ProviderRegistry.ALLOWED_DOMAINS
            ))
        })


class HistoryViewSet(ReadOnlyModelViewSet):
    """
    Endpoint do przeglądania historii analiz.
    
    GET /api/history/           - lista analiz
    GET /api/history/{id}/      - szczegóły analizy
    GET /api/history/recent/    - ostatnie 10 analiz
    """
    
    queryset = LocationAnalysis.objects.all()
    serializer_class = LocationAnalysisSerializer
    
    def get_serializer_class(self):
        if self.action == 'retrieve':
            return LocationAnalysisDetailSerializer
        return LocationAnalysisSerializer
    
    @action(detail=False, methods=['get'])
    def recent(self, request):
        """Zwraca ostatnie 10 analiz."""
        recent = self.queryset[:10]
        serializer = self.get_serializer(recent, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['get'])
    def report(self, request, pk=None):
        """Zwraca pełny raport z bazy."""
        instance = self.get_object()
        return Response(instance.report_data)


class ProvidersView(APIView):
    """
    Endpoint informacyjny o obsługiwanych providerach.
    
    GET /api/providers/
    """
    
    def get(self, request):
        domains = list(set(
            d.replace('www.', '') for d in ProviderRegistry.ALLOWED_DOMAINS
        ))
        
        return Response({
            'providers': [
                {
                    'name': 'Otodom',
                    'domain': 'otodom.pl',
                    'example': 'https://www.otodom.pl/pl/oferta/...'
                },
                {
                    'name': 'OLX Nieruchomości',
                    'domain': 'olx.pl',
                    'example': 'https://www.olx.pl/nieruchomosci/...'
                }
            ],
            'allowed_domains': domains,
        })


class ProfilesView(APIView):
    """
    Endpoint do pobierania dostępnych profili scoringu.
    
    GET /api/profiles/          - lista profili
    GET /api/profiles/{key}/    - szczegóły profilu
    """
    
    def get(self, request, profile_key=None):
        if profile_key:
            # Szczegóły konkretnego profilu
            profile = get_profile(profile_key)
            return Response(profile.to_dict())
        
        # Lista wszystkich profili
        return Response({
            'profiles': get_profiles_summary(),
            'default': 'family',
        })


class ReportDetailView(APIView):
    """
    Publiczny endpoint do pobierania raportu po public_id.
    
    GET /api/report/{public_id}/
    """
    
    def get(self, request, public_id):
        """Zwraca pełny raport z bazy po public_id."""
        analysis = get_object_or_404(LocationAnalysis, public_id=public_id)
        
        # Zwróć pełny raport z report_data lub zbuduj z pól
        if analysis.report_data:
            report = analysis.report_data.copy()
            
            # Dodaj zapisane AI insights (persisted from original analysis)
            if analysis.ai_insights_data:
                report['ai_insights'] = analysis.ai_insights_data
            
            # Dodaj scoring i verdict jeśli dostępne
            if analysis.scoring_data and 'scoring' not in report:
                report['scoring'] = analysis.scoring_data
            if analysis.verdict_data and 'verdict' not in report:
                report['verdict'] = analysis.verdict_data
            
            # Dodaj rescore tracking
            report['rescore_count'] = analysis.rescore_count
            report['rescore_limit'] = analysis.rescore_limit
            
            return Response(report)
        
        # Fallback - zbuduj z pól modelu
        return Response({
            'success': True,
            'errors': analysis.parsing_errors or [],
            'warnings': [],
            'tldr': {
                'pros': analysis.pros or [],
                'cons': analysis.cons or [],
            },
            'listing': {
                'url': analysis.url,
                'title': analysis.title,
                'address': analysis.address,
                'price': float(analysis.price) if analysis.price else None,
                'price_per_sqm': float(analysis.price_per_sqm) if analysis.price_per_sqm else None,
                'area_sqm': analysis.area_sqm,
                'rooms': analysis.rooms,
                'floor': analysis.floor,
                'description': analysis.description,
                'images': analysis.images or [],
                'latitude': analysis.latitude,
                'longitude': analysis.longitude,
                'has_precise_location': analysis.has_precise_location,
            },
            'neighborhood': {
                'has_location': analysis.has_precise_location,
                'score': analysis.neighborhood_score,
                'summary': '',
                'details': analysis.neighborhood_data or {},
                'poi_stats': {},
                'markers': [],
            },
            'checklist': analysis.checklist or [],
            'limitations': [],
            'public_id': analysis.public_id,
            'ai_insights': analysis.ai_insights_data or {},
        })


class RescoreReportView(APIView):
    """
    Zmiana profilu na istniejącym raporcie (bez ponownego pobierania danych geo).
    
    POST /api/report/{public_id}/rescore/
    Body: { "profile_key": "urban" }
    Returns: { scoring, verdict, ai_insights, profile, rescore_count, rescore_limit }
    """
    
    def post(self, request, public_id):
        from .rescore_service import rescore_service, RescoreLimitExceeded, RescoreDataMissing
        
        analysis = get_object_or_404(LocationAnalysis, public_id=public_id)
        
        profile_key = request.data.get('profile_key')
        if not profile_key:
            return Response(
                {'error': 'Brak parametru profile_key'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Walidacja profilu
        try:
            get_profile(profile_key)
        except Exception:
            return Response(
                {'error': f'Nieznany profil: {profile_key}'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            result = rescore_service.rescore(analysis, profile_key)
            return Response(result)
        except RescoreLimitExceeded as e:
            return Response(
                {'error': str(e), 'rescore_count': analysis.rescore_count, 'rescore_limit': analysis.rescore_limit},
                status=status.HTTP_429_TOO_MANY_REQUESTS
            )
        except RescoreDataMissing as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_422_UNPROCESSABLE_ENTITY
            )
        except ValueError as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            logger.error("Rescore error: %s", e, exc_info=True)
            return Response(
                {'error': 'Wewnętrzny błąd serwera podczas przeliczania profilu'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
