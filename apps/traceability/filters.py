"""Shared search / filter logic for batch tables."""
from datetime import date

from django.db.models import Q

from .models import Batch


def _parse_date(value):
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def filter_batches(request, queryset):
    """Search by Batch ID / herb, filter by status and collection date range."""
    q = request.GET.get("q", "").strip()
    status = request.GET.get("status", "")
    date_from = _parse_date(request.GET.get("date_from"))
    date_to = _parse_date(request.GET.get("date_to"))

    if q:
        queryset = queryset.filter(
            Q(batch_id__icontains=q)
            | Q(collection__herb__name__icontains=q)
            | Q(collection__location_name__icontains=q)
        )
    if status in Batch.Status.values:
        queryset = queryset.filter(status=status)
    if date_from:
        queryset = queryset.filter(collection__collection_date__gte=date_from)
    if date_to:
        queryset = queryset.filter(collection__collection_date__lte=date_to)

    return queryset, {
        "q": q,
        "status": status,
        "date_from": request.GET.get("date_from", ""),
        "date_to": request.GET.get("date_to", ""),
        "statuses": Batch.Status.choices,
    }
