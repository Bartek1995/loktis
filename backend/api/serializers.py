from rest_framework import serializers
from .models import Layout


class LayoutSerializer(serializers.ModelSerializer):
    class Meta:
        model = Layout
        fields = ['id', 'name', 'layout_data', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']
