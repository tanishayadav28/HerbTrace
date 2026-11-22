from django.conf import settings
from django.db import models

from apps.traceability.models import Batch


class Processing(models.Model):
    class Stage(models.TextChoices):
        CLEANING = "CLEANING", "Cleaning / sorting"
        DRYING = "DRYING", "Drying"
        GRINDING = "GRINDING", "Grinding / powdering"
        EXTRACTION = "EXTRACTION", "Extraction"
        STORAGE = "STORAGE", "Storage"
        PACKAGING = "PACKAGING", "Intermediate packaging"
        OTHER = "OTHER", "Other"

    class Status(models.TextChoices):
        IN_PROGRESS = "IN_PROGRESS", "In progress"
        COMPLETED = "COMPLETED", "Completed"

    batch = models.ForeignKey(Batch, on_delete=models.PROTECT, related_name="processing_records")
    processor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="processing_records"
    )
    stage = models.CharField(max_length=12, choices=Stage.choices)
    processing_date = models.DateField()
    location = models.CharField(max_length=200)
    description = models.TextField()
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.IN_PROGRESS, db_index=True)
    is_demo = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["processing_date", "created_at"]
        verbose_name_plural = "processing records"

    def __str__(self):
        return f"{self.batch.batch_id} – {self.get_stage_display()}"

    def ledger_snapshot(self) -> dict:
        return {
            "batch_id": self.batch.batch_id,
            "processor_id": self.processor_id,
            "stage": self.stage,
            "processing_date": self.processing_date.isoformat(),
            "location": self.location,
            "description": self.description,
            "status": self.status,
        }
