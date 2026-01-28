"""
Widoki API dla analizatora ogłoszeń.
"""
import logging

from rest_framework import status
from rest_framework.views import APIView
from rest_framework.viewsets import ReadOnlyModelViewSet
from rest_framework.response import Response
from rest_framework.decorators import action

from .models import AnalysisResult
from .serializers import (
    AnalyzeRequestSerializer,
    AnalysisReportSerializer,
    AnalysisResultSerializer,
    AnalysisResultDetailSerializer,
)
from .services import analysis_service
from .rate_limiter import rate_limit
from .providers import ProviderRegistry

logger = logging.getLogger(__name__)


from django.http import StreamingHttpResponse

class AnalyzeView(APIView):
    """
    Endpoint do analizy ogłoszenia.
    
    POST /api/analyze/
    Returns: NDJSON stream
    """
    
    @rate_limit()
    def post(self, request):
        """Analizuje ogłoszenie z podanego URL (stream)."""
        serializer = AnalyzeRequestSerializer(data=request.data)
        
        if not serializer.is_valid():
            return Response(
                {'errors': serializer.errors},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        url = serializer.validated_data['url']
        use_cache = serializer.validated_data.get('use_cache', True)
        radius = serializer.validated_data.get('radius', 500)
        
        logger.info(f"Analiza URL (stream): {url} (radius={radius})")
        
        # Stream response (NDJSON)
        response = StreamingHttpResponse(
            analysis_service.analyze_stream(url, radius=radius, use_cache=use_cache),
            content_type='application/x-ndjson'
        )
        response['X-Accel-Buffering'] = 'no'  # Disable Nginx buffering if present
        return response


class ValidateURLView(APIView):
    """
    Endpoint do walidacji URL przed wysłaniem.
    
    POST /api/validate-url/
    {"url": "..."}
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
    """
    
    queryset = AnalysisResult.objects.all()
    serializer_class = AnalysisResultSerializer
    
    def get_serializer_class(self):
        if self.action == 'retrieve':
            return AnalysisResultDetailSerializer
        return AnalysisResultSerializer
    
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
