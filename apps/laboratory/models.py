from decimal import Decimal

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from apps.traceability.models import Batch


class LaboratoryTest(models.Model):
    class Result(models.TextChoices):
        PASS = "PASS", "PASS"
        FAIL = "FAIL", "FAIL"

    batch = models.ForeignKey(Batch, on_delete=models.PROTECT, related_name="lab_tests")
    tested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="lab_tests"
    )
    test_date = models.DateField()
    purity_percentage = models.DecimalField(
        max_digits=5, decimal_places=2,
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("100"))],
    )
    moisture_percentage = models.DecimalField(
        max_digits=5, decimal_places=2,
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("100"))],
    )
    contamination_details = models.TextField(blank=True)
    observations = models.TextField(blank=True)
    remarks = models.TextField(blank=True)
    result = models.CharField(max_length=4, choices=Result.choices, db_index=True)
    is_demo = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.batch.batch_id}: {self.result}"

    def ledger_snapshot(self) -> dict:
        return {
            "batch_id": self.batch.batch_id,
            "tested_by_id": self.tested_by_id,
            "test_date": self.test_date.isoformat(),
            "purity_percentage": str(self.purity_percentage),
            "moisture_percentage": str(self.moisture_percentage),
            "contamination_details": self.contamination_details,
            "observations": self.observations,
            "remarks": self.remarks,
            "result": self.result,
        }
