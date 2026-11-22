from django.conf import settings
from django.db import models


class Verification(models.Model):
    """Log of every ledger integrity check run by an administrator."""

    checked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    checked_at = models.DateTimeField(auto_now_add=True, db_index=True)
    total_records = models.PositiveBigIntegerField()
    is_valid = models.BooleanField()
    head_sequence = models.PositiveBigIntegerField(default=0)
    head_hash = models.CharField(max_length=64, blank=True)
    issues = models.JSONField(default=list)

    class Meta:
        ordering = ["-checked_at"]

    def __str__(self):
        return f"{self.checked_at:%Y-%m-%d %H:%M} – {'valid' if self.is_valid else 'INVALID'}"
