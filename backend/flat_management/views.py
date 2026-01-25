from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework import status
from .models import Flat, Layout
from .serializers import (
    FlatSerializer,
    FlatCreateUpdateSerializer,
    LayoutSerializer
)


class FlatViewSet(viewsets.ModelViewSet):
    """
    API endpoints dla mieszkań (Flat).
    
    GET /api/flats/ - lista wszystkich
    POST /api/flats/ - utworz
    GET /api/flats/:id/ - pobierz szczegóły
    PUT /api/flats/:id/ - zaktualizuj
    PATCH /api/flats/:id/ - aktualizacja częściowa
    DELETE /api/flats/:id/ - usuń
    """
    queryset = Flat.objects.all()
    filterset_fields = ['name', 'rooms', 'area_sqm']
    search_fields = ['name', 'address', 'description']

    def get_serializer_class(self):
        """Używaj FlatCreateUpdateSerializer do POST/PUT/PATCH."""
        if self.action in ['create', 'update', 'partial_update']:
            return FlatCreateUpdateSerializer
        return FlatSerializer

    @action(detail=True, methods=['post'])
    def upload_layout_image(self, request, pk=None):
        """
        Upload obrazu do layoutu mieszkania.
        POST /api/flats/:id/upload_layout_image/
        """
        flat = self.get_object()
        image = request.FILES.get('image')

        if not image:
            return Response(
                {'error': 'Brak pliku'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Utwórz lub zaktualizuj Layout
        layout, created = Layout.objects.get_or_create(flat=flat)
        layout.image = image
        layout.save()

        return Response(
            LayoutSerializer(layout).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK
        )


class LayoutViewSet(viewsets.ModelViewSet):
    """
    API endpoints dla layoutów (Plan mieszkania).
    
    GET /api/layouts/ - lista wszystkich
    POST /api/layouts/ - utworz
    GET /api/layouts/:id/ - pobierz szczegóły
    PUT /api/layouts/:id/ - zaktualizuj
    PATCH /api/layouts/:id/ - aktualizacja częściowa
    DELETE /api/layouts/:id/ - usuń
    """
    queryset = Layout.objects.all()
    serializer_class = LayoutSerializer
    filterset_fields = ['flat']
    search_fields = ['flat__name']

    @action(detail=True, methods=['post'])
    def set_scale(self, request, pk=None):
        """
        Ustaw skalę layoutu.
        POST /api/layouts/:id/set_scale/
        Body: {"scale_cm_per_px": 0.5}
        """
        layout = self.get_object()
        scale = request.data.get('scale_cm_per_px')

        if scale is None:
            return Response(
                {'error': 'scale_cm_per_px jest wymagane'},
                status=status.HTTP_400_BAD_REQUEST
            )

        layout.scale_cm_per_px = float(scale)
        layout.save()

        return Response(
            LayoutSerializer(layout).data,
            status=status.HTTP_200_OK
        )

    @action(detail=True, methods=['post'])
    def save_layout_data(self, request, pk=None):
        """
        Zapisz dane layoutu (ściany, punkty, itp).
        POST /api/layouts/:id/save_layout_data/
        Body: {
          "layout_data": {
            "walls": [...],
            "points": [{"id": "bed", "x": 100, "y": 50}, ...],
            "scale_cm_per_px": 0.5
          }
        }
        """
        layout = self.get_object()
        layout_data = request.data.get('layout_data', {})

        layout.layout_data = layout_data
        if 'scale_cm_per_px' in layout_data:
            layout.scale_cm_per_px = layout_data['scale_cm_per_px']
        layout.save()

        return Response(
            LayoutSerializer(layout).data,
            status=status.HTTP_200_OK
        )
