from decimal import Decimal

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from .geo import haversine_km


class Herb(models.Model):
    name = models.CharField(max_length=120, unique=True)
    botanical_name = models.CharField(max_length=160, blank=True)
    description = models.TextField(blank=True)
    part_used = models.CharField(max_length=120, blank=True, help_text="e.g. root, leaf, bark")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class ApprovedRegion(models.Model):
    """A circular approved collection zone: centre point + radius.

    A circle is a deliberately simple geofence. See README "Region
    verification limitations" for what this does and does not prove.
    """

    name = models.CharField(max_length=150, unique=True)
    state = models.CharField(max_length=100, blank=True)
    center_latitude = models.DecimalField(
        max_digits=9, decimal_places=6, validators=[MinValueValidator(Decimal("-90")), MaxValueValidator(Decimal("90"))]
    )
    center_longitude = models.DecimalField(
        max_digits=9, decimal_places=6, validators=[MinValueValidator(Decimal("-180")), MaxValueValidator(Decimal("180"))]
    )
    radius_km = models.DecimalField(
        max_digits=7, decimal_places=2, validators=[MinValueValidator(Decimal("0.1"))]
    )
    herbs = models.ManyToManyField(
        Herb,
        blank=True,
        related_name="approved_regions",
        help_text="Leave empty to approve every herb in this region.",
    )
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    def distance_km(self, lat, lng) -> float:
        return haversine_km(self.center_latitude, self.center_longitude, lat, lng)

    def contains(self, lat, lng) -> bool:
        return self.distance_km(lat, lng) <= float(self.radius_km)

    def allows_herb(self, herb) -> bool:
        if not self.herbs.exists():
            return True
        return self.herbs.filter(pk=herb.pk).exists()
