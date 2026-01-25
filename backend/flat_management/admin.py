from django.contrib import admin
from .models import Flat, Layout


@admin.register(Flat)
class FlatAdmin(admin.ModelAdmin):
    list_display = ['name', 'address', 'rooms', 'area_sqm', 'created_at']
    search_fields = ['name', 'address']
    list_filter = ['rooms', 'area_sqm', 'created_at']
    ordering = ['-created_at']
    readonly_fields = ['created_at', 'updated_at']
    fieldsets = (
        ('Informacje podstawowe', {
            'fields': ('name', 'address', 'rooms', 'area_sqm')
        }),
        ('Opis', {
            'fields': ('description',)
        }),
        ('Metadane', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(Layout)
class LayoutAdmin(admin.ModelAdmin):
    list_display = ['get_flat_name', 'has_image', 'scale_cm_per_px', 'created_at']
    search_fields = ['flat__name']
    list_filter = ['created_at', 'scale_cm_per_px']
    ordering = ['-created_at']
    readonly_fields = ['created_at', 'updated_at']
    fieldsets = (
        ('Layout', {
            'fields': ('flat', 'image', 'scale_cm_per_px')
        }),
        ('Dane geometryczne', {
            'fields': ('layout_data',),
            'classes': ('collapse',)
        }),
        ('Metadane', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def get_flat_name(self, obj):
        return obj.flat.name if obj.flat else 'Brak'
    get_flat_name.short_description = 'Mieszkanie'

    def has_image(self, obj):
        return bool(obj.image)
    has_image.boolean = True
    has_image.short_description = 'Obraz'
