from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render

from apps.accounts.permissions import lab_required
from apps.core.pagination import paginate
from apps.traceability.filters import filter_batches
from apps.traceability.models import Batch

from .forms import LabTestForm
from .models import LaboratoryTest
from .services import record_test

RELATED = ("collection__herb", "collection__collector", "collection__region")


@lab_required
def dashboard(request):
    tests = LaboratoryTest.objects.aggregate(
        total=Count("id"),
        passed=Count("id", filter=Q(result="PASS")),
        failed=Count("id", filter=Q(result="FAIL")),
    )
    queue = Batch.objects.filter(status=Batch.Status.AWAITING_LAB).select_related(*RELATED)
    return render(request, "laboratory/dashboard.html", {
        "pending": queue.count(), "tests": tests,
        "queue": queue.order_by("created_at")[:6],
        "recent": LaboratoryTest.objects.select_related("batch", "tested_by")[:6],
    })


@lab_required
def queue(request):
    qs = Batch.objects.filter(status=Batch.Status.AWAITING_LAB).select_related(*RELATED).order_by("created_at")
    qs, filters = filter_batches(request, qs)
    page, params = paginate(request, qs, 10)
    return render(request, "laboratory/queue.html", {"page": page, "qs_params": params, **filters})


@lab_required
def test_create(request, batch_id):
    batch = get_object_or_404(Batch.objects.select_related(*RELATED), batch_id=batch_id)
    if batch.status != Batch.Status.AWAITING_LAB:
        messages.error(request, f"{batch.batch_id} is '{batch.get_status_display()}' and cannot be tested.")
        return redirect("laboratory:queue")
    form = LabTestForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            test = record_test(batch, request.user, form.save(commit=False))
        except ValidationError as exc:
            form.add_error(None, exc)
        else:
            if test.result == LaboratoryTest.Result.PASS:
                messages.success(request, f"{batch.batch_id} PASSED and is now approved for processing.")
            else:
                messages.warning(request, f"{batch.batch_id} FAILED and has been rejected. It cannot be processed or manufactured.")
            return redirect("laboratory:queue")
    return render(request, "laboratory/test_form.html", {"form": form, "batch": batch, "collection": batch.collection})


@lab_required
def history(request):
    qs = LaboratoryTest.objects.select_related("batch__collection__herb", "tested_by")
    q = request.GET.get("q", "").strip()
    result = request.GET.get("result", "")
    if q:
        qs = qs.filter(Q(batch__batch_id__icontains=q) | Q(batch__collection__herb__name__icontains=q))
    if result in LaboratoryTest.Result.values:
        qs = qs.filter(result=result)
    page, params = paginate(request, qs, 10)
    return render(request, "laboratory/history.html", {"page": page, "qs_params": params, "q": q, "result": result})
