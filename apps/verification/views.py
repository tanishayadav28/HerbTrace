"""Public verification pages: no login required, no private data exposed."""
import uuid

from django import forms
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render

from apps.manufacturing.models import FinalFormulation
from apps.traceability import ledger
from apps.traceability.models import Batch, BlockchainRecord
from apps.traceability.timeline import build_timeline


class LookupForm(forms.Form):
    code = forms.CharField(max_length=60, label="Product code or Batch ID")


def lookup(request):
    form = LookupForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        code = form.cleaned_data["code"].strip().upper()
        formulation = FinalFormulation.objects.filter(formulation_code=code).first()
        if formulation is None:
            batch = Batch.objects.filter(batch_id=code).first()
            link = getattr(batch, "manufacturing_link", None) if batch else None
            if link:
                formulation = link.manufacturing.formulation
            elif batch:
                messages.info(
                    request,
                    f"Batch {batch.batch_id} exists but has not been made into a final product yet, "
                    "so there is no public product page for it.",
                )
                return render(request, "verification/lookup.html", {"form": form})
        if formulation:
            return redirect("verification:public", public_id=formulation.public_id)
        messages.error(request, "No product or batch matches that code.")
    return render(request, "verification/lookup.html", {"form": form})


def _short_name(user) -> str:
    """First name + last initial only. Never the username, e-mail or phone."""
    first = (user.first_name or "").strip()
    last = (user.last_name or "").strip()
    if not first:
        return "Registered collector"
    return f"{first} {last[0]}." if last else first


ROLE_LABELS = {
    "ADMIN": "Administrator", "FARMER": "Collector", "LAB": "Laboratory",
    "PROCESSOR": "Processor", "MANUFACTURER": "Manufacturer",
}


def _public_actor(actor: str) -> str:
    """Ledger actors look like 'username (ROLE)'. Publicly show the role only."""
    if "(" in actor and actor.endswith(")"):
        return ROLE_LABELS.get(actor.rsplit("(", 1)[1].rstrip(")"), "Staff")
    return "System"


def public_verification(request, public_id: uuid.UUID):
    formulation = get_object_or_404(
        FinalFormulation.objects.select_related("manufacturing", "qr_code"), public_id=public_id
    )
    manufacturing = formulation.manufacturing
    batches = list(
        manufacturing.batches.select_related("collection__herb", "collection__collector", "collection__region")
        .prefetch_related("lab_tests", "processing_records")
        .order_by("batch_id")
    )
    batch_ids = [b.batch_id for b in batches]
    report = ledger.integrity_report(batch_ids)

    items, markers = [], []
    for b in batches:
        c = b.collection
        test = b.lab_tests.order_by("-created_at").first()
        items.append({
            "batch": b,
            "collection": c,
            "collector_name": _short_name(c.collector),  # no e-mail / phone / username
            "test": test,
            "processing": list(b.processing_records.all()),
        })
        if c.has_coordinates:
            markers.append({
                "lat": float(c.latitude), "lng": float(c.longitude),
                "title": f"{c.herb.name} – {b.batch_id}",
                "detail": c.location_name,
                "source": c.get_coordinate_source_display(),
                "accuracy": c.gps_accuracy_m,
            })

    records = BlockchainRecord.objects.filter(batch_id__in=batch_ids).order_by("timestamp", "sequence")
    return render(request, "verification/public.html", {
        "formulation": formulation,
        "manufacturing": manufacturing,
        "items": items,
        "markers": markers,
        "report": report,
        "timeline": [{**e, "actor": _public_actor(e["actor"])} for e in build_timeline(records)],
        "qr": getattr(formulation, "qr_code", None),
    })
