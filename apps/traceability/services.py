"""Business rules for collections, region verification and region review."""
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.herbs.models import ApprovedRegion

from . import ledger
from .models import Batch, Collection


def evaluate_region(herb, latitude, longitude, source_type, permit_available):
    """Decide the region status for a coordinate.

    Returns ``(region, status, reason)``.

    Workflow
    --------
    * Inside an active approved region that allows the herb -> APPROVED and the
      batch goes straight to the laboratory queue.
    * Outside every approved region, missing coordinates, or a wild collection
      without a permit -> PENDING_REVIEW. An administrator must approve or
      reject it; the batch cannot progress until then.
    """
    S = Collection.RegionStatus
    if latitude is None or longitude is None:
        return None, S.PENDING_REVIEW, (
            "No GPS coordinates were provided, so the collection location could not be "
            "checked against approved regions."
        )

    regions = list(ApprovedRegion.objects.filter(is_active=True))
    matches = sorted(
        (r for r in regions if r.contains(latitude, longitude) and r.allows_herb(herb)),
        key=lambda r: r.distance_km(latitude, longitude),
    )
    if matches:
        region = matches[0]
        distance = region.distance_km(latitude, longitude)
        if source_type == Collection.SourceType.WILD and not permit_available:
            return region, S.PENDING_REVIEW, (
                f"Inside approved region '{region.name}' ({distance:.1f} km from its centre), "
                "but this is a wild collection without a permit, so it needs admin review."
            )
        return region, S.APPROVED, (
            f"Inside approved region '{region.name}' "
            f"({distance:.1f} km from centre, radius {region.radius_km} km)."
        )

    if not regions:
        return None, S.PENDING_REVIEW, "No approved collection regions are configured yet."

    nearest = min(regions, key=lambda r: r.distance_km(latitude, longitude))
    distance = nearest.distance_km(latitude, longitude)
    herb_note = ""
    if nearest.contains(latitude, longitude) and not nearest.allows_herb(herb):
        herb_note = f" The region '{nearest.name}' does not list {herb.name} as an approved herb."
    return None, S.PENDING_REVIEW, (
        f"Outside all approved regions. Nearest is '{nearest.name}', {distance:.1f} km from its "
        f"centre (radius {nearest.radius_km} km).{herb_note}"
    )


@transaction.atomic
def register_collection(collection: Collection) -> Batch:
    """Validate region, save the collection, create its batch and ledger entry."""
    region, status, reason = evaluate_region(
        collection.herb, collection.latitude, collection.longitude,
        collection.source_type, collection.permit_available,
    )
    collection.region, collection.region_status, collection.region_reason = region, status, reason
    if not collection.has_coordinates:
        collection.coordinate_source = Collection.CoordinateSource.NONE
    collection.full_clean(exclude=["collector"])
    collection.save()

    batch_status = (
        Batch.Status.AWAITING_LAB
        if status == Collection.RegionStatus.APPROVED
        else Batch.Status.PENDING_REVIEW
    )
    batch = Batch.create_for_collection(collection, batch_status)
    ledger.record_event(
        batch_id=batch.batch_id,
        event_type=ledger.COLLECTION_REGISTERED,
        actor_user=collection.collector,
        obj=collection,
        extra={"initial_batch_status": batch_status},
    )
    return batch


@transaction.atomic
def review_region(batch: Batch, admin_user, approve: bool, note: str = "") -> Batch:
    """Admin decision for a collection waiting in PENDING_REVIEW."""
    batch = Batch.objects.select_for_update().select_related("collection").get(pk=batch.pk)
    if batch.status != Batch.Status.PENDING_REVIEW:
        raise ValidationError("Only batches pending region review can be reviewed.")
    collection = batch.collection
    collection.region_status = (
        Collection.RegionStatus.APPROVED if approve else Collection.RegionStatus.REJECTED
    )
    collection.reviewed_by = admin_user
    collection.reviewed_at = timezone.now()
    suffix = f" Admin note: {note.strip()}" if note.strip() else ""
    collection.region_reason = (
        f"{collection.region_reason} — {'Approved' if approve else 'Rejected'} by admin.{suffix}"
    )
    collection.save()
    batch.transition(Batch.Status.AWAITING_LAB if approve else Batch.Status.REGION_REJECTED)
    ledger.record_event(
        batch_id=batch.batch_id,
        event_type=ledger.REGION_REVIEWED,
        actor_user=admin_user,
        obj=collection,
        extra={"decision": "APPROVED" if approve else "REJECTED", "note": note.strip()},
    )
    return batch
