import csv

from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Count, Q
from django.db.models.functions import TruncMonth
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.accounts.models import User
from apps.accounts.permissions import admin_required, farmer_required, role_required
from apps.core.pagination import paginate
from apps.herbs.models import ApprovedRegion

from . import ledger, services
from .filters import filter_batches
from .forms import CollectionForm, RegionReviewForm
from .models import Batch, BlockchainRecord, Collection
from .timeline import build_timeline

BATCH_RELATED = ("collection__herb", "collection__collector", "collection__region")


# ------------------------------------------------------------------ farmer
@farmer_required
def farmer_dashboard(request):
    batches = Batch.objects.filter(collection__collector=request.user)
    counts = {row["status"]: row["n"] for row in batches.values("status").annotate(n=Count("id"))}
    stats = {
        "total": batches.count(),
        "awaiting_lab": counts.get(Batch.Status.AWAITING_LAB, 0),
        "pending_review": counts.get(Batch.Status.PENDING_REVIEW, 0),
        "in_chain": sum(counts.get(s, 0) for s in (
            Batch.Status.LAB_PASSED, Batch.Status.PROCESSING, Batch.Status.PROCESSED)),
        "manufactured": counts.get(Batch.Status.MANUFACTURED, 0),
        "rejected": counts.get(Batch.Status.REJECTED, 0) + counts.get(Batch.Status.REGION_REJECTED, 0),
    }
    return render(request, "traceability/farmer_dashboard.html", {
        "stats": stats, "recent": batches.select_related(*BATCH_RELATED)[:6],
    })


@farmer_required
def collection_create(request):
    form = CollectionForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        collection = form.save(commit=False)
        collection.collector = request.user
        try:
            batch = services.register_collection(collection)
        except ValidationError as exc:
            form.add_error(None, exc)
        else:
            if batch.status == Batch.Status.AWAITING_LAB:
                messages.success(
                    request,
                    f"Collection registered. Your Batch ID is {batch.batch_id}. "
                    "It passed region verification and is queued for laboratory testing.",
                )
            else:
                messages.warning(
                    request,
                    f"Collection registered. Your Batch ID is {batch.batch_id}, but it needs "
                    f"admin region review first: {collection.region_reason}",
                )
            return redirect("traceability:batch_detail", batch_id=batch.batch_id)
    regions = list(
        ApprovedRegion.objects.filter(is_active=True).values(
            "name", "center_latitude", "center_longitude", "radius_km"
        )
    )
    regions = [
        {"name": r["name"], "lat": float(r["center_latitude"]), "lng": float(r["center_longitude"]),
         "radius_km": float(r["radius_km"])}
        for r in regions
    ]
    return render(request, "traceability/collection_form.html", {"form": form, "regions": regions})


@farmer_required
def my_collections(request):
    qs = Batch.objects.filter(collection__collector=request.user).select_related(*BATCH_RELATED)
    qs, filters = filter_batches(request, qs)
    page, params = paginate(request, qs, 10)
    return render(request, "traceability/batch_list.html", {
        "page": page, "qs_params": params, "title": "My collections", "show_collector": False, **filters,
    })


# ------------------------------------------------------------ batch detail
ALL_CHAIN_ROLES = (User.Role.ADMIN, User.Role.FARMER, User.Role.LAB, User.Role.PROCESSOR, User.Role.MANUFACTURER)


@role_required(*ALL_CHAIN_ROLES)
def batch_detail(request, batch_id):
    qs = Batch.objects.select_related(*BATCH_RELATED)
    if request.user.effective_role == User.Role.FARMER:
        qs = qs.filter(collection__collector=request.user)  # farmers see only their own batches
    batch = get_object_or_404(qs, batch_id=batch_id)
    collection = batch.collection
    report = ledger.integrity_report([batch.batch_id])
    formulation = None
    link = getattr(batch, "manufacturing_link", None)
    if link:
        formulation = getattr(link.manufacturing, "formulation", None)
    return render(request, "traceability/batch_detail.html", {
        "batch": batch,
        "collection": collection,
        "lab_tests": batch.lab_tests.select_related("tested_by"),
        "processing_records": batch.processing_records.select_related("processor"),
        "timeline": build_timeline(BlockchainRecord.objects.filter(batch_id=batch.batch_id)),
        "report": report,
        "formulation": formulation,
        "manufacturing": link.manufacturing if link else None,
        "event_labels": ledger.EVENT_LABELS,
    })


# ------------------------------------------------------------------- admin
@admin_required
def batch_list(request):
    qs = Batch.objects.select_related(*BATCH_RELATED)
    qs, filters = filter_batches(request, qs)
    page, params = paginate(request, qs, 12)
    return render(request, "traceability/batch_list.html", {
        "page": page, "qs_params": params, "title": "All batches", "show_collector": True, **filters,
    })


@admin_required
def region_reviews(request):
    qs = Batch.objects.filter(status=Batch.Status.PENDING_REVIEW).select_related(*BATCH_RELATED)
    page, params = paginate(request, qs, 10)
    return render(request, "traceability/region_reviews.html", {
        "page": page, "qs_params": params, "form": RegionReviewForm(),
    })


@admin_required
@require_POST
def region_review_decide(request, batch_id, decision):
    batch = get_object_or_404(Batch, batch_id=batch_id)
    form = RegionReviewForm(request.POST)
    note = form.cleaned_data["note"] if form.is_valid() else ""
    try:
        services.review_region(batch, request.user, approve=(decision == "approve"), note=note)
    except ValidationError as exc:
        messages.error(request, "; ".join(exc.messages))
    else:
        if decision == "approve":
            messages.success(request, f"{batch.batch_id} approved and queued for laboratory testing.")
        else:
            messages.warning(request, f"{batch.batch_id} rejected: it cannot progress further.")
    return redirect("traceability:region_reviews")


def _all_batch_ids():
    return list(Batch.objects.values_list("batch_id", flat=True))


@admin_required
def ledger_view(request):
    from apps.verification.models import Verification

    report = ledger.integrity_report(_all_batch_ids())
    q = request.GET.get("q", "").strip()
    records = BlockchainRecord.objects.all().order_by("-sequence")
    if q:
        records = records.filter(batch_id__icontains=q)
    event = request.GET.get("event", "")
    if event:
        records = records.filter(event_type=event)
    page, params = paginate(request, records, 15)
    return render(request, "traceability/ledger.html", {
        "report": report, "chain": report["chain"], "page": page, "qs_params": params,
        "q": q, "event": event, "event_labels": ledger.EVENT_LABELS,
        "history": Verification.objects.all()[:5], "genesis": ledger.GENESIS_HASH,
    })


@admin_required
@require_POST
def ledger_verify(request):
    from apps.verification.models import Verification

    report = ledger.integrity_report(_all_batch_ids())
    chain = report["chain"]
    issues = chain.issues + report["data_issues"]
    Verification.objects.create(
        checked_by=request.user, total_records=chain.total, is_valid=report["valid"],
        head_sequence=chain.head_sequence, head_hash=chain.head_hash, issues=issues,
    )
    if report["valid"]:
        messages.success(request, f"Integrity verified: all {chain.total} ledger records are consistent.")
    else:
        messages.error(request, f"Integrity check FAILED: {len(issues)} problem(s) detected. See details below.")
    return redirect("traceability:ledger")


@admin_required
def reports(request):
    herb_rows = (
        Collection.objects.values("herb__name").annotate(n=Count("id")).order_by("-n")
    )
    region_rows = (
        Collection.objects.values("region__name").annotate(n=Count("id")).order_by("-n")
    )
    monthly = (
        Collection.objects.annotate(month=TruncMonth("collection_date"))
        .values("month").annotate(n=Count("id")).order_by("month")
    )
    status_rows = [
        {"label": label, "code": code, "n": Batch.objects.filter(status=code).count()}
        for code, label in Batch.Status.choices
    ]
    from apps.laboratory.models import LaboratoryTest

    lab = LaboratoryTest.objects.aggregate(
        total=Count("id"),
        passed=Count("id", filter=Q(result="PASS")),
    )
    return render(request, "traceability/reports.html", {
        "herb_rows": herb_rows, "region_rows": region_rows, "monthly": monthly,
        "status_rows": status_rows, "lab": lab,
    })


@admin_required
def reports_export(request):
    """CSV export of all batches (honours the same filters as the batch list)."""
    qs = Batch.objects.select_related(*BATCH_RELATED)
    qs, _ = filter_batches(request, qs)
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="batches.csv"'
    writer = csv.writer(response)
    writer.writerow([
        "batch_id", "herb", "collector", "collection_date", "quantity", "unit", "source_type",
        "location", "latitude", "longitude", "coordinate_source", "region", "region_status", "batch_status",
    ])
    for b in qs.iterator():
        c = b.collection
        writer.writerow([
            b.batch_id, c.herb.name, c.collector.username, c.collection_date, c.quantity, c.unit,
            c.source_type, c.location_name, c.latitude or "", c.longitude or "", c.coordinate_source,
            c.region.name if c.region else "", c.region_status, b.get_status_display(),
        ])
    return response
