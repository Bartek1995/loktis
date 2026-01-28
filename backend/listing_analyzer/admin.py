from django.contrib import admin
from .models import AnalysisResult


@admin.register(AnalysisResult)
class AnalysisResultAdmin(admin.ModelAdmin):
    list_display = ['title', 'price', 'area_sqm', 'location', 'neighborhood_score', 'created_at']
    list_filter = ['source_provider', 'has_precise_location', 'created_at']
    search_fields = ['title', 'url', 'location']
    readonly_fields = ['url_hash', 'created_at']
    ordering = ['-created_at']
    
    fieldsets = (
        ('Ogłoszenie', {
            'fields': ('url', 'url_hash', 'title', 'source_provider')
        }),
        ('Dane', {
            'fields': ('price', 'price_per_sqm', 'area_sqm', 'rooms', 'floor', 'location')
        }),
        ('Lokalizacja', {
            'fields': ('latitude', 'longitude', 'has_precise_location', 'neighborhood_score')
        }),
        ('Raport', {
            'fields': ('pros', 'cons', 'checklist'),
            'classes': ('collapse',)
        }),
        ('Meta', {
            'fields': ('created_at', 'parsing_errors'),
            'classes': ('collapse',)
        }),
    )
