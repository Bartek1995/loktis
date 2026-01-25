from rest_framework import serializers
from .models import Flat, Layout


class LayoutSerializer(serializers.ModelSerializer):
    """Serializer dla modelu Layout."""
    class Meta:
        model = Layout
        fields = [
            'id', 
            'flat',
            'image',
            'scale_cm_per_px',
            'layout_data',
            'created_at',
            'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class FlatSerializer(serializers.ModelSerializer):
    """Serializer dla modelu Flat z zagnieżdżonym Layout."""
    layout = LayoutSerializer(read_only=True)

    class Meta:
        model = Flat
        fields = [
            'id',
            'name',
            'address',
            'area_sqm',
            'rooms',
            'description',
            'layout',
            'created_at',
            'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class FlatCreateUpdateSerializer(serializers.ModelSerializer):
    """Serializer do tworzenia/aktualizacji Flat (bez nested Layout)."""
    class Meta:
        model = Flat
        fields = [
            'id',
            'name',
            'address',
            'area_sqm',
            'rooms',
            'description'
        ]
        read_only_fields = ['id']
