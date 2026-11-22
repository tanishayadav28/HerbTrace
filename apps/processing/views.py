from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.accounts.permissions import processor_required
from apps.core.pagination import paginate
from apps.traceability.filters import filter_batches
from apps.traceability.models import Batch

from .forms import ProcessingForm
from .models import Processing
from .services import PROCESSABLE, add_processing, update_status

RELATED = ("collection__herb", "collection__collector")


def _eligible():
    """Lab-approved batches that are not yet manufactured."""
    return Batch.objects.filter(status__in=PROCESSABLE, lab_tests__result="PASS").distinct()


@processor_required
def dashboard(request):
    eligible = _eligible()
    return render(request, "processing/dashboard.html", {
        "stats": {
            "ready": eligible.filter(status=Batch.Status.LAB_PASSED).count(),
            "in_progress": eligible.filter(status=Batch.Status.PROCESSING).count(),
            "processed": eligible.filter(status=Batch.Status.PROCESSED).count(),
            "mine": Processing.objects.filter(processor=request.user).count(),
        },
        "recent": Processing.objects.filter(processor=request.user).select_related("batch__collection__herb")[:6],
    })


@processor_required
def eligible(request):
    qs, filters = filter_batches(request, _eligible().select_related(*RELATED))
    page, params = paginate(request, qs, 10)
    return render(request, "processing/eligible.html", {"page": page, "qs_params": params, **filters})


@processor_required
def add(request, batch_id):
    batch = get_object_or_404(Batch.objects.select_related(*RELATED), batch_id=batch_id)
    if batch.status not in PROCESSABLE or not batch.is_lab_cleared:
        messages.error(request, f"{batch.batch_id} is not laboratory-approved for processing.")
        return redirect("processing:eligible")
    form = ProcessingForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            add_processing(batch, request.user, form.save(commit=False))
        except ValidationError as exc:
            form.add_error(None, exc)
        else:
            messages.success(request, f"Processing step recorded for {batch.batch_id}.")
            return redirect("processing:history")
    return render(request, "processing/form.html", {
        "form": form, "batch": batch,
        "records": batch.processing_records.select_related("processor"),
    })


@processor_required
def history(request):
    qs = Processing.objects.select_related("batch__collection__herb", "processor")
    q = request.GET.get("q", "").strip()
    status = request.GET.get("status", "")
    mine = request.GET.get("mine") == "1"
    if q:
        qs = qs.filter(Q(batch__batch_id__icontains=q) | Q(batch__collection__herb__name__icontains=q))
    if status in Processing.Status.values:
        qs = qs.filter(status=status)
    if mine:
        qs = qs.filter(processor=request.user)
    page, params = paginate(request, qs, 10)
    return render(request, "processing/history.html", {
        "page": page, "qs_params": params, "q": q, "status": status, "mine": mine,
        "statuses": Processing.Status.choices,
    })


@processor_required
@require_POST
def set_status(request, pk):
    record = get_object_or_404(Processing, pk=pk)
    try:
        update_status(record, request.user, request.POST.get("status", ""))
    except PermissionDenied:
        messages.error(request, "You can only update your own processing records.")
    except ValidationError as exc:
        messages.error(request, "; ".join(exc.messages))
    else:
        messages.success(request, "Processing status updated.")
    return redirect("processing:history")
