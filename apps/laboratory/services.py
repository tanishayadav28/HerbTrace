from django.core.exceptions import ValidationError
from django.db import transaction

from apps.traceability import ledger
from apps.traceability.models import Batch

from .models import LaboratoryTest


@transaction.atomic
def record_test(batch: Batch, user, test: LaboratoryTest) -> LaboratoryTest:
    """Store a lab result and move the batch: PASS -> LAB_PASSED, FAIL -> REJECTED."""
    batch = Batch.objects.select_for_update().get(pk=batch.pk)
    if batch.status != Batch.Status.AWAITING_LAB:
        raise ValidationError(
            f"Batch {batch.batch_id} is '{batch.get_status_display()}' and cannot be tested."
        )
    test.batch = batch
    test.tested_by = user
    test.full_clean(exclude=["batch", "tested_by"])
    test.save()
    batch.transition(
        Batch.Status.LAB_PASSED if test.result == LaboratoryTest.Result.PASS else Batch.Status.REJECTED
    )
    ledger.record_event(
        batch_id=batch.batch_id, event_type=ledger.LAB_TEST_RECORDED, actor_user=user, obj=test,
    )
    return test
