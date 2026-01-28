"""
Serializery DRF dla analizatora ogłoszeń.
"""
from rest_framework import serializers
from .models import AnalysisResult


class AnalyzeRequestSerializer(serializers.Serializer):
    """Walidacja requesta analizy."""
    url = serializers.URLField(
        required=True,
        max_length=2048,
        help_text="URL ogłoszenia (Otodom, OLX)"
    )
    use_cache = serializers.BooleanField(
        required=False,
        default=True,
        help_text="Czy używać cache"
    )
    radius = serializers.IntegerField(
        required=False,
        default=500,
        min_value=100,
        max_value=2000,
        help_text="Promień analizy w metrach"
    )


class TLDRSerializer(serializers.Serializer):
    """TL;DR sekcja raportu."""
    pros = serializers.ListField(child=serializers.CharField())
    cons = serializers.ListField(child=serializers.CharField())


class ListingDataSerializer(serializers.Serializer):
    """Dane z ogłoszenia."""
    url = serializers.CharField()
    title = serializers.CharField(allow_blank=True)
    price = serializers.FloatField(allow_null=True)
    price_per_sqm = serializers.FloatField(allow_null=True)
    area_sqm = serializers.FloatField(allow_null=True)
    rooms = serializers.IntegerField(allow_null=True)
    floor = serializers.CharField(allow_blank=True)
    location = serializers.CharField(allow_blank=True)
    description = serializers.CharField(allow_blank=True)
    images = serializers.ListField(child=serializers.URLField())
    latitude = serializers.FloatField(allow_null=True)
    longitude = serializers.FloatField(allow_null=True)
    has_precise_location = serializers.BooleanField()
    errors = serializers.ListField(child=serializers.CharField())


class NeighborhoodSerializer(serializers.Serializer):
    """Dane o okolicy."""
    has_location = serializers.BooleanField()
    score = serializers.FloatField(allow_null=True)
    summary = serializers.CharField(allow_blank=True)
    details = serializers.DictField()
    poi_stats = serializers.DictField()
    markers = serializers.ListField(child=serializers.DictField())


class AnalysisReportSerializer(serializers.Serializer):
    """Pełny raport z analizy."""
    success = serializers.BooleanField()
    errors = serializers.ListField(child=serializers.CharField())
    warnings = serializers.ListField(child=serializers.CharField())
    tldr = TLDRSerializer()
    listing = ListingDataSerializer()
    neighborhood = NeighborhoodSerializer()
    checklist = serializers.ListField(child=serializers.CharField())
    limitations = serializers.ListField(child=serializers.CharField())


class AnalysisResultSerializer(serializers.ModelSerializer):
    """Serializer dla modelu AnalysisResult (historia)."""
    
    class Meta:
        model = AnalysisResult
        fields = [
            'id',
            'url',
            'title',
            'price',
            'price_per_sqm',
            'area_sqm',
            'rooms',
            'floor',
            'location',
            'latitude',
            'longitude',
            'has_precise_location',
            'neighborhood_score',
            'pros',
            'cons',
            'source_provider',
            'created_at',
        ]
        read_only_fields = fields


class AnalysisResultDetailSerializer(serializers.ModelSerializer):
    """Pełny serializer z wszystkimi danymi."""
    
    class Meta:
        model = AnalysisResult
        fields = '__all__'
        read_only_fields = fields
