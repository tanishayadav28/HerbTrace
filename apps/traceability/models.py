import secrets
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import IntegrityError, models, transaction
from django.utils import timezone

from apps.herbs.models import ApprovedRegion, Herb


class Collection(models.Model):
    class Unit(models.TextChoices):
        KG = "kg", "Kilograms (kg)"
        G = "g", "Grams (g)"
        TONNE = "t", "Tonnes (t)"

    class Method(models.TextChoices):
        HAND = "HAND", "Hand-picked"
        TOOLS = "TOOLS", "Harvested with tools"
        PRUNING = "PRUNING", "Selective pruning"
        DIGGING = "DIGGING", "Digging (roots / tubers)"
        OTHER = "OTHER", "Other"

    class SourceType(models.TextChoices):
        CULTIVATED = "CULTIVATED", "Cultivated"
        WILD = "WILD", "Wild collected"

    class CoordinateSource(models.TextChoices):
        GPS = "GPS", "Captured by device GPS"
        MANUAL = "MANUAL", "Entered manually"
        NONE = "NONE", "Not provided"

    class RegionStatus(models.TextChoices):
        APPROVED = "APPROVED", "Inside approved region"
        PENDING_REVIEW = "PENDING_REVIEW", "Pending admin review"
        REJECTED = "REJECTED", "Rejected"

    herb = models.ForeignKey(Herb, on_delete=models.PROTECT, related_name="collections")
    collector = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="collections"
    )
    collection_date = models.DateField()
    collection_time = models.TimeField()
    quantity = models.DecimalField(
        max_digits=10, decimal_places=3, validators=[MinValueValidator(Decimal("0.001"))]
    )
    unit = models.CharField(max_length=3, choices=Unit.choices, default=Unit.KG)
    collection_method = models.CharField(max_length=10, choices=Method.choices)
    source_type = models.CharField(max_length=12, choices=SourceType.choices)
    sustainability_details = models.TextField(blank=True)
    permit_available = models.BooleanField(default=False)
    permit_number = models.CharField(max_length=80, blank=True)

    latitude = models.DecimalField(
        max_digits=9, decimal_places=6, null=True, blank=True,
        validators=[MinValueValidator(Decimal("-90")), MaxValueValidator(Decimal("90"))],
    )
    longitude = models.DecimalField(
        max_digits=9, decimal_places=6, null=True, blank=True,
        validators=[MinValueValidator(Decimal("-180")), MaxValueValidator(Decimal("180"))],
    )
    coordinate_source = models.CharField(
        max_length=6, choices=CoordinateSource.choices, default=CoordinateSource.NONE
    )
    gps_accuracy_m = models.PositiveIntegerField(null=True, blank=True)
    location_name = models.CharField(max_length=200)

    region = models.ForeignKey(
        ApprovedRegion, null=True, blank=True, on_delete=models.SET_NULL, related_name="collections"
    )
    region_status = models.CharField(
        max_length=16, choices=RegionStatus.choices, default=RegionStatus.PENDING_REVIEW, db_index=True
    )
    region_reason = models.TextField(blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="reviewed_collections",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    is_demo = models.BooleanField(default=False, help_text="Marks seeded demonstration data.")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-collection_date", "-created_at"]
        indexes = [models.Index(fields=["collection_date"])]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(quantity__gt=0), name="collection_quantity_positive"
            ),
            models.CheckConstraint(
                condition=(models.Q(latitude__isnull=True, longitude__isnull=True)
                           | models.Q(latitude__isnull=False, longitude__isnull=False)),
                name="collection_lat_lng_together",
            ),
        ]

    def __str__(self):
        return f"{self.herb} – {self.collection_date}"

    @property
    def has_coordinates(self) -> bool:
        return self.latitude is not None and self.longitude is not None

    def clean(self):
        if (self.latitude is None) != (self.longitude is None):
            raise ValidationError("Latitude and longitude must be provided together.")

    def ledger_snapshot(self) -> dict:
        return {
            "herb_id": self.herb_id,
            "collector_id": self.collector_id,
            "collection_date": self.collection_date.isoformat(),
            "collection_time": self.collection_time.strftime("%H:%M:%S"),
            "quantity": str(self.quantity),
            "unit": self.unit,
            "collection_method": self.collection_method,
            "source_type": self.source_type,
            "permit_available": self.permit_available,
            "latitude": None if self.latitude is None else str(self.latitude),
            "longitude": None if self.longitude is None else str(self.longitude),
            "coordinate_source": self.coordinate_source,
            "location_name": self.location_name,
            "region_id": self.region_id,
            "region_status": self.region_status,
        }


class Batch(models.Model):
    class Status(models.TextChoices):
        PENDING_REVIEW = "PENDING_REVIEW", "Pending region review"
        REGION_REJECTED = "REGION_REJECTED", "Region rejected"
        AWAITING_LAB = "AWAITING_LAB", "Awaiting laboratory test"
        LAB_PASSED = "LAB_PASSED", "Lab approved – ready for processing"
        REJECTED = "REJECTED", "Rejected (failed laboratory test)"
        PROCESSING = "PROCESSING", "Processing"
        PROCESSED = "PROCESSED", "Processed – ready for manufacturing"
        MANUFACTURED = "MANUFACTURED", "Manufactured"

    # Allowed workflow transitions. Anything else raises ValidationError.
    TRANSITIONS = {
        Status.PENDING_REVIEW: {Status.AWAITING_LAB, Status.REGION_REJECTED},
        Status.REGION_REJECTED: set(),
        Status.AWAITING_LAB: {Status.LAB_PASSED, Status.REJECTED},
        Status.LAB_PASSED: {Status.PROCESSING, Status.PROCESSED},
        Status.REJECTED: set(),
        Status.PROCESSING: {Status.PROCESSING, Status.PROCESSED},
        Status.PROCESSED: {Status.PROCESSING, Status.MANUFACTURED},
        Status.MANUFACTURED: set(),
    }

    batch_id = models.CharField(max_length=24, unique=True, editable=False)
    collection = models.OneToOneField(Collection, on_delete=models.PROTECT, related_name="batch")
    status = models.CharField(max_length=16, choices=Status.choices, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name_plural = "batches"

    def __str__(self):
        return self.batch_id

    # ---- Batch ID generation -------------------------------------------------
    @staticmethod
    def generate_batch_id(today=None) -> str:
        """HB-YYYYMMDD-XXXXXX (6 random base-32 characters, ~1 billion per day)."""
        today = today or timezone.localdate()
        alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no look-alike characters
        token = "".join(secrets.choice(alphabet) for _ in range(6))
        return f"HB-{today:%Y%m%d}-{token}"

    @classmethod
    def create_for_collection(cls, collection: Collection, status: str) -> "Batch":
        """Create a batch with a unique ID (retries on the rare collision)."""
        for _ in range(10):
            try:
                with transaction.atomic():
                    return cls.objects.create(
                        batch_id=cls.generate_batch_id(), collection=collection, status=status
                    )
            except IntegrityError:
                if cls.objects.filter(collection=collection).exists():
                    raise
        raise RuntimeError("Could not allocate a unique batch ID.")

    # ---- Workflow ------------------------------------------------------------
    def can_transition_to(self, new_status: str) -> bool:
        return new_status in self.TRANSITIONS.get(self.status, set())

    def transition(self, new_status: str, save: bool = True):
        if not self.can_transition_to(new_status):
            raise ValidationError(
                f"Batch {self.batch_id} cannot move from '{self.get_status_display()}' "
                f"to '{self.Status(new_status).label}'."
            )
        self.status = new_status
        if save:
            self.save(update_fields=["status", "updated_at"])

    @property
    def latest_lab_test(self):
        return self.lab_tests.order_by("-created_at").first()

    @property
    def is_lab_cleared(self) -> bool:
        test = self.latest_lab_test
        return bool(test and test.result == "PASS")


class LedgerState(models.Model):
    """Single-row table holding the current chain head.

    It serves two purposes: (1) it is the row that is locked
    (``SELECT … FOR UPDATE``) while a record is appended, which serialises
    concurrent writers; (2) it is an anchor that lets verification notice if
    the newest record(s) were deleted.
    """

    id = models.PositiveSmallIntegerField(primary_key=True, default=1)
    head_sequence = models.PositiveBigIntegerField(default=0)
    head_hash = models.CharField(max_length=64)

    def __str__(self):
        return f"head #{self.head_sequence}"


class BlockchainRecord(models.Model):
    """One entry of the application-level SHA-256 hash-linked ledger."""

    sequence = models.PositiveBigIntegerField(unique=True, editable=False)
    batch_id = models.CharField(max_length=24, db_index=True)
    event_type = models.CharField(max_length=40, db_index=True)
    actor = models.CharField(max_length=200)
    actor_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    timestamp = models.DateTimeField(db_index=True)
    event_data = models.JSONField()
    previous_hash = models.CharField(max_length=64)
    current_hash = models.CharField(max_length=64, unique=True)

    class Meta:
        ordering = ["sequence"]

    def __str__(self):
        return f"#{self.sequence} {self.event_type} {self.batch_id}"
