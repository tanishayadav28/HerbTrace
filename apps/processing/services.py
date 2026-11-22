from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction

from apps.traceability import ledger
from apps.traceability.models import Batch

from .models import Processing

PROCESSABLE = {Batch.Status.LAB_PASSED, Batch.Status.PROCESSING, Batch.Status.PROCESSED}


def _sync_batch_status(batch: Batch):
    """PROCESSING while any step is open, PROCESSED once every step is completed."""
    records = batch.processing_records.all()
    if not records:
        return
    open_steps = records.filter(status=Processing.Status.IN_PROGRESS).exists()
    target = Batch.Status.PROCESSING if open_steps else Batch.Status.PROCESSED
    if batch.status != target:
        batch.transition(target)


@transaction.atomic
def add_processing(batch: Batch, user, record: Processing) -> Processing:
    batch = Batch.objects.select_for_update().get(pk=batch.pk)
    if batch.status not in PROCESSABLE or not batch.is_lab_cleared:
        raise ValidationError(
            f"Batch {batch.batch_id} is not laboratory-approved for processing "
            f"(current status: {batch.get_status_display()})."
        )
    record.batch = batch
    record.processor = user
    record.full_clean(exclude=["batch", "processor"])
    record.save()
    _sync_batch_status(batch)
    ledger.record_event(
        batch_id=batch.batch_id, event_type=ledger.PROCESSING_RECORDED, actor_user=user, obj=record,
    )
    return record


@transaction.atomic
def update_status(record: Processing, user, new_status: str) -> Processing:
    """Only the processor who created a step may change its status."""
    record = Processing.objects.select_for_update().select_related("batch").get(pk=record.pk)
    if record.processor_id != user.pk:
        raise PermissionDenied("You can only update your own processing records.")
    if new_status not in Processing.Status.values:
        raise ValidationError("Unknown processing status.")
    batch = Batch.objects.select_for_update().get(pk=record.batch_id)
    if batch.status == Batch.Status.MANUFACTURED:
        raise ValidationError("This batch has already been manufactured and can no longer change.")
    if record.status == new_status:
        return record
    record.status = new_status
    record.save()
    _sync_batch_status(batch)
    ledger.record_event(
        batch_id=batch.batch_id, event_type=ledger.PROCESSING_STATUS_UPDATED, actor_user=user,
        obj=record, extra={"new_status": new_status},
    )
    return record
