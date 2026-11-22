import uuid

from django.conf import settings
from django.db import models

from apps.traceability.models import Batch


class Manufacturing(models.Model):
    manufacturer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="manufacturing_runs"
    )
    manufacturer_name = models.CharField(max_length=200)
    manufacturing_date = models.DateField()
    location = models.CharField(max_length=200)
    details = models.TextField()
    batches = models.ManyToManyField(Batch, through="BatchManufacturing", related_name="manufacturing_runs")
    is_demo = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name_plural = "manufacturing runs"

    def __str__(self):
        return f"Manufacturing #{self.pk} ({self.manufacturing_date})"

    def ledger_snapshot(self) -> dict:
        return {
            "manufacturer_id": self.manufacturer_id,
            "manufacturer_name": self.manufacturer_name,
            "manufacturing_date": self.manufacturing_date.isoformat(),
            "location": self.location,
            "details": self.details,
            "batch_ids": sorted(self.batches.values_list("batch_id", flat=True)),
        }


class BatchManufacturing(models.Model):
    """Link table. ``batch`` is unique: a batch can be manufactured only once."""

    manufacturing = models.ForeignKey(Manufacturing, on_delete=models.CASCADE, related_name="batch_links")
    batch = models.OneToOneField(Batch, on_delete=models.PROTECT, related_name="manufacturing_link")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.batch.batch_id} → run #{self.manufacturing_id}"


class FinalFormulation(models.Model):
    manufacturing = models.OneToOneField(Manufacturing, on_delete=models.PROTECT, related_name="formulation")
    product_name = models.CharField(max_length=200)
    formulation_code = models.CharField(max_length=24, unique=True, editable=False)
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    formulation_date = models.DateField()
    packaging_info = models.TextField()
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="formulations"
    )
    is_demo = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.product_name} ({self.formulation_code})"

    def ledger_snapshot(self) -> dict:
        return {
            "product_name": self.product_name,
            "formulation_code": self.formulation_code,
            "public_id": str(self.public_id),
            "formulation_date": self.formulation_date.isoformat(),
            "packaging_info": self.packaging_info,
            "created_by_id": self.created_by_id,
        }


class QRCode(models.Model):
    formulation = models.OneToOneField(FinalFormulation, on_delete=models.CASCADE, related_name="qr_code")
    url = models.URLField(max_length=300)
    image = models.ImageField(upload_to="qrcodes/")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"QR for {self.formulation.formulation_code}"
