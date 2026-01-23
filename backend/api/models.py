from django.db import models


class Layout(models.Model):
    """Floor plan layout model."""
    name = models.CharField(max_length=255, default="Unnamed Layout")
    layout_data = models.JSONField(
        default=dict,
        blank=True,
        help_text="JSON structure: {walls: [...], objects: [...], doors: [...]}"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Layout'
        verbose_name_plural = 'Layouts'

    def __str__(self):
        return f"{self.name} ({self.created_at.date()})"
