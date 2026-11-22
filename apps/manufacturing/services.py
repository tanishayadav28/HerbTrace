import secrets

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.traceability import ledger
from apps.traceability.models import Batch

from .models import BatchManufacturing, FinalFormulation, Manufacturing
from .qr import generate_qr


def _formulation_code() -> str:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    for _ in range(20):
        code = f"FRM-{timezone.localdate():%Y%m%d}-" + "".join(secrets.choice(alphabet) for _ in range(6))
        if not FinalFormulation.objects.filter(formulation_code=code).exists():
            return code
    raise RuntimeError("Could not allocate a unique formulation code.")


def eligible_batches():
    """Batches that finished processing and passed the laboratory."""
    return Batch.objects.filter(status=Batch.Status.PROCESSED, lab_tests__result="PASS").distinct()


@transaction.atomic
def create_formulation(*, user, batches, manufacturing: Manufacturing, formulation: FinalFormulation):
    """Create the manufacturing run, the final formulation, the QR code and ledger entries.

    Every selected batch is locked and re-validated *inside* the transaction, so a
    failed, unprocessed or already-manufactured batch can never be included even
    if the form was tampered with.
    """
    batch_ids = [b.pk for b in batches]
    if not batch_ids:
        raise ValidationError("Select at least one batch.")
    locked = list(Batch.objects.select_for_update().filter(pk__in=batch_ids).order_by("pk"))
    if len(locked) != len(set(batch_ids)):
        raise ValidationError("One or more selected batches do not exist.")
    for batch in locked:
        if batch.status != Batch.Status.PROCESSED:
            raise ValidationError(
                f"Batch {batch.batch_id} is '{batch.get_status_display()}' and cannot be manufactured."
            )
        if not batch.is_lab_cleared:
            raise ValidationError(f"Batch {batch.batch_id} has no passing laboratory result.")

    manufacturing.manufacturer = user
    manufacturing.full_clean(exclude=["manufacturer"])
    manufacturing.save()
    for batch in locked:
        BatchManufacturing.objects.create(manufacturing=manufacturing, batch=batch)

    formulation.manufacturing = manufacturing
    formulation.created_by = user
    formulation.formulation_code = _formulation_code()
    formulation.full_clean(exclude=["manufacturing", "created_by", "formulation_code"])
    formulation.save()

    for batch in locked:
        batch.transition(Batch.Status.MANUFACTURED)
        ledger.record_event(
            batch_id=batch.batch_id, event_type=ledger.MANUFACTURING_RECORDED,
            actor_user=user, obj=manufacturing,
        )
        ledger.record_event(
            batch_id=batch.batch_id, event_type=ledger.FORMULATION_CREATED,
            actor_user=user, obj=formulation,
        )
    generate_qr(formulation)
    return formulation
