from django.db import models


class Flat(models.Model):
    """Model reprezentujący mieszkanie."""
    name = models.CharField(
        max_length=255,
        help_text="Nazwa mieszkania, np. '2-pokojowe Poznań, ul. Lipowa 5'"
    )
    address = models.CharField(
        max_length=512,
        blank=True,
        help_text="Adres mieszkania"
    )
    area_sqm = models.FloatField(
        null=True,
        blank=True,
        help_text="Powierzchnia w m²"
    )
    rooms = models.IntegerField(
        null=True,
        blank=True,
        help_text="Liczba pokoi"
    )
    description = models.TextField(
        blank=True,
        help_text="Opis mieszkania"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Mieszkanie'
        verbose_name_plural = 'Mieszkania'

    def __str__(self):
        return self.name


class Layout(models.Model):
    """Model reprezentujący rzut mieszkania z danymi geometrycznymi."""
    flat = models.OneToOneField(
        Flat,
        on_delete=models.CASCADE,
        related_name='layout',
        null=True,
        blank=True,
        help_text="Powiązane mieszkanie"
    )
    image = models.ImageField(
        upload_to='layouts/%Y/%m/%d/',
        null=True,
        blank=True,
        help_text="Zdjęcie/PDF rzutu mieszkania"
    )
    scale_cm_per_px = models.FloatField(
        null=True,
        blank=True,
        help_text="Skala: ile cm w rzeczywistości na 1 piksel na obrazie"
    )
    layout_data = models.JSONField(
        default=dict,
        blank=True,
        help_text="JSON struktura: {walls: [...], points: [...], scale_cm_per_px: ...}"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Layout'
        verbose_name_plural = 'Layouty'

    def __str__(self):
        return f"Layout {self.flat.name}" if self.flat else "Layout bez mieszkania"
