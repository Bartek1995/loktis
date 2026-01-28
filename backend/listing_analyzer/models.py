from django.db import models
import json


class AnalysisResult(models.Model):
    """
    Model przechowujący wyniki analizy ogłoszenia.
    Opcjonalnie zapisywany do bazy (historia bez logowania).
    """
    url = models.URLField(max_length=2048, db_index=True)
    url_hash = models.CharField(max_length=64, unique=True, db_index=True)
    
    # Dane z ogłoszenia
    title = models.CharField(max_length=512, blank=True)
    price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    price_per_sqm = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    area_sqm = models.FloatField(null=True, blank=True)
    rooms = models.IntegerField(null=True, blank=True)
    floor = models.CharField(max_length=50, blank=True)
    location = models.CharField(max_length=512, blank=True)
    description = models.TextField(blank=True)
    images = models.JSONField(default=list, blank=True)
    
    # Geo data
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    has_precise_location = models.BooleanField(default=False)
    
    # Wyniki analizy okolicy
    neighborhood_data = models.JSONField(default=dict, blank=True)
    neighborhood_score = models.FloatField(null=True, blank=True)
    
    # Raport
    report_data = models.JSONField(default=dict, blank=True)
    pros = models.JSONField(default=list, blank=True)
    cons = models.JSONField(default=list, blank=True)
    checklist = models.JSONField(default=list, blank=True)
    
    # Meta
    source_provider = models.CharField(max_length=50, blank=True)
    parsing_errors = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Wynik analizy'
        verbose_name_plural = 'Wyniki analiz'
    
    def __str__(self):
        return f"{self.title[:50]}..." if len(self.title) > 50 else self.title
    
    @classmethod
    def generate_url_hash(cls, url: str) -> str:
        import hashlib
        normalized = url.strip().lower().rstrip('/')
        return hashlib.sha256(normalized.encode()).hexdigest()
