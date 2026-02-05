"""
Serializery DRF dla analizy lokalizacji.
"""
from rest_framework import serializers
from .models import LocationAnalysis


class AnalyzeListingRequestSerializer(serializers.Serializer):
    """Walidacja requesta analizy przez URL ogłoszenia."""
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


class AnalyzeLocationRequestSerializer(serializers.Serializer):
    """Walidacja requesta analizy lokalizacji (location-first model)."""
    latitude = serializers.FloatField(
        required=True,
        min_value=-90,
        max_value=90,
        help_text="Szerokość geograficzna"
    )
    longitude = serializers.FloatField(
        required=True,
        min_value=-180,
        max_value=180,
        help_text="Długość geograficzna"
    )
    price = serializers.FloatField(
        required=True,
        min_value=0,
        help_text="Cena nieruchomości"
    )
    area_sqm = serializers.FloatField(
        required=True,
        min_value=1,
        help_text="Powierzchnia w m²"
    )
    address = serializers.CharField(
        required=True,
        max_length=500,
        help_text="Adres lokalizacji"
    )
    radius = serializers.IntegerField(
        required=False,
        default=500,
        min_value=100,
        max_value=2000,
        help_text="Promień analizy w metrach"
    )
    reference_url = serializers.URLField(
        required=False,
        allow_blank=True,
        max_length=2048,
        help_text="Opcjonalny URL ogłoszenia jako referencja"
    )
    # Nowy parametr: profile_key
    profile_key = serializers.ChoiceField(
        choices=[
            ('urban', 'City Life'),
            ('family', 'Rodzina z dziećmi'),
            ('quiet_green', 'Spokojnie i zielono'),
            ('remote_work', 'Home Office'),
            ('active_sport', 'Aktywny sportowo'),
            ('car_first', 'Pod auto / przedmieścia'),
            ('investor', 'Inwestor'),
        ],
        required=False,
        default='family',
        help_text="Klucz profilu scoringu"
    )
    # Legacy - zachowujemy dla kompatybilności (mapowane na profile_key)
    user_profile = serializers.ChoiceField(
        choices=[
            'urban', 'family', 'quiet_green', 'remote_work', 
            'active_sport', 'car_first',
            'investor',  # legacy
        ],
        required=False,
        default='family',
        help_text="[LEGACY] Profil użytkownika - użyj profile_key"
    )
    poi_provider = serializers.ChoiceField(
        choices=['overpass', 'google', 'hybrid'],
        required=False,
        default='hybrid',
        help_text="Dostawca POI (overpass, google, hybrid)"
    )



class TLDRSerializer(serializers.Serializer):
    """TL;DR sekcja raportu."""
    pros = serializers.ListField(child=serializers.CharField())
    cons = serializers.ListField(child=serializers.CharField())


class PropertyDataSerializer(serializers.Serializer):
    """Dane o nieruchomości."""
    url = serializers.CharField(allow_blank=True)
    title = serializers.CharField(allow_blank=True)
    address = serializers.CharField(allow_blank=True)
    price = serializers.FloatField(allow_null=True)
    price_per_sqm = serializers.FloatField(allow_null=True)
    area_sqm = serializers.FloatField(allow_null=True)
    rooms = serializers.IntegerField(allow_null=True)
    floor = serializers.CharField(allow_blank=True)
    location = serializers.CharField(allow_blank=True)
    description = serializers.CharField(allow_blank=True)
    images = serializers.ListField(child=serializers.URLField(), required=False)
    latitude = serializers.FloatField(allow_null=True)
    longitude = serializers.FloatField(allow_null=True)
    has_precise_location = serializers.BooleanField()
    errors = serializers.ListField(child=serializers.CharField(), required=False)


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
    listing = PropertyDataSerializer()
    neighborhood = NeighborhoodSerializer()
    checklist = serializers.ListField(child=serializers.CharField())
    limitations = serializers.ListField(child=serializers.CharField())


class LocationAnalysisSerializer(serializers.ModelSerializer):
    """Serializer dla modelu LocationAnalysis (historia)."""
    
    class Meta:
        model = LocationAnalysis
        fields = [
            'id',
            'url',
            'title',
            'address',
            'price',
            'price_per_sqm',
            'area_sqm',
            'rooms',
            'floor',
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


class LocationAnalysisDetailSerializer(serializers.ModelSerializer):
    """Pełny serializer z wszystkimi danymi."""
    
    class Meta:
        model = LocationAnalysis
        fields = '__all__'
