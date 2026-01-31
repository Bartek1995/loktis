"""
Model przechowujący wyniki analizy lokalizacji.
"""
from django.db import models
import hashlib
import secrets


class LocationAnalysis(models.Model):
    """
    Model przechowujący wyniki analizy lokalizacji.
    Główna jednostka danych dla loktis.pl - analiza lokalizacji nieruchomości.
    """
    # Publiczny identyfikator - hash do URL (auto-generowany)
    public_id = models.CharField(max_length=32, unique=True, db_index=True, blank=True)
    
    # Identyfikacja - URL opcjonalny (location-first model)
    url = models.URLField(max_length=2048, blank=True, db_index=True)
    url_hash = models.CharField(max_length=64, unique=True, db_index=True)
    
    # Dane o nieruchomości
    title = models.CharField(max_length=512, blank=True)
    address = models.CharField(max_length=512, blank=True)
    price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    price_per_sqm = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    area_sqm = models.FloatField(null=True, blank=True)
    rooms = models.IntegerField(null=True, blank=True)
    floor = models.CharField(max_length=50, blank=True)
    description = models.TextField(blank=True)
    images = models.JSONField(default=list, blank=True)
    
    # Lokalizacja - kluczowe dla location-first model
    latitude = models.FloatField(null=True, blank=True, db_index=True)
    longitude = models.FloatField(null=True, blank=True, db_index=True)
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
    analysis_radius = models.IntegerField(default=500)
    parsing_errors = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Analiza Lokalizacji'
        verbose_name_plural = 'Analizy Lokalizacji'
    
    def __str__(self):
        if self.address:
            return f"{self.address[:50]}..." if len(self.address) > 50 else self.address
        return f"Analiza #{self.id}"
    
    @classmethod
    def generate_hash(cls, lat: float = None, lon: float = None, url: str = None) -> str:
        """Generate unique hash for location or URL."""
        if lat is not None and lon is not None:
            # Hash based on location (rounded to 5 decimals for ~1m precision)
            normalized = f"{round(lat, 5)},{round(lon, 5)}"
        elif url:
            normalized = url.strip().lower().rstrip('/')
        else:
            import uuid
            normalized = str(uuid.uuid4())
        return hashlib.sha256(normalized.encode()).hexdigest()
    
    @classmethod
    def generate_public_id(cls) -> str:
        """Generate unique public ID for shareable URLs."""
        return secrets.token_urlsafe(16)[:24]  # 24 chars - short but unique
    
    @classmethod
    def generate_url_hash(cls, url: str) -> str:
        """Legacy method for URL-based hash."""
        return cls.generate_hash(url=url)
    
    def save(self, *args, **kwargs):
        """Override save to auto-generate public_id if not set."""
        if not self.public_id:
            # Generate unique public_id
            for _ in range(10):  # Max 10 attempts
                new_id = self.generate_public_id()
                if not LocationAnalysis.objects.filter(public_id=new_id).exists():
                    self.public_id = new_id
                    break
            else:
                # Fallback to longer token
                self.public_id = secrets.token_urlsafe(24)[:32]
        super().save(*args, **kwargs)
