from rest_framework import viewsets
from .models import Layout
from .serializers import LayoutSerializer


class LayoutViewSet(viewsets.ModelViewSet):
    """
    API endpoints for floor plan layouts.
    GET /api/layouts/ - list all
    POST /api/layouts/ - create
    GET /api/layouts/:id/ - retrieve
    PUT /api/layouts/:id/ - update
    PATCH /api/layouts/:id/ - partial update
    DELETE /api/layouts/:id/ - delete
    """
    queryset = Layout.objects.all()
    serializer_class = LayoutSerializer
    filterset_fields = ['name', 'created_at']
    search_fields = ['name']
