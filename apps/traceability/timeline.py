"""Human-readable timeline built from the ledger records themselves.

Because the text is generated from the snapshot stored *inside* each ledger
record, the timeline shows exactly what the hash chain certifies.
"""
from apps.herbs.models import Herb

from . import ledger as L

ICONS = {
    L.COLLECTION_REGISTERED: "bi-basket2",
    L.REGION_REVIEWED: "bi-geo-alt",
    L.LAB_TEST_RECORDED: "bi-clipboard2-pulse",
    L.PROCESSING_RECORDED: "bi-gear",
    L.PROCESSING_STATUS_UPDATED: "bi-arrow-repeat",
    L.MANUFACTURING_RECORDED: "bi-building-gear",
    L.FORMULATION_CREATED: "bi-capsule-pill",
}


def _summary(rec, herb_names) -> str:
    data = rec.event_data or {}
    snap = data.get("snapshot", {})
    et = rec.event_type
    try:
        if et == L.COLLECTION_REGISTERED:
            herb = herb_names.get(snap.get("herb_id"), "herb")
            return (
                f"{snap.get('quantity')} {snap.get('unit')} of {herb} "
                f"({snap.get('source_type', '').lower()}) collected at {snap.get('location_name')} "
                f"on {snap.get('collection_date')}. Region check: "
                f"{str(snap.get('region_status', '')).replace('_', ' ').lower()}."
            )
        if et == L.REGION_REVIEWED:
            note = f" Note: {data['note']}" if data.get("note") else ""
            return f"Administrator {str(data.get('decision', '')).lower()} the collection region.{note}"
        if et == L.LAB_TEST_RECORDED:
            return (
                f"Laboratory result {snap.get('result')}: purity {snap.get('purity_percentage')}%, "
                f"moisture {snap.get('moisture_percentage')}% (tested {snap.get('test_date')})."
            )
        if et == L.PROCESSING_RECORDED:
            return (
                f"{str(snap.get('stage', '')).replace('_', ' ').title()} at {snap.get('location')} "
                f"on {snap.get('processing_date')} — {snap.get('status', '').replace('_', ' ').lower()}."
            )
        if et == L.PROCESSING_STATUS_UPDATED:
            return (
                f"{str(snap.get('stage', '')).replace('_', ' ').title()} step marked "
                f"{str(data.get('new_status', '')).replace('_', ' ').lower()}."
            )
        if et == L.MANUFACTURING_RECORDED:
            return (
                f"Manufactured by {snap.get('manufacturer_name')} at {snap.get('location')} "
                f"on {snap.get('manufacturing_date')}."
            )
        if et == L.FORMULATION_CREATED:
            return f"Final formulation '{snap.get('product_name')}' created ({snap.get('formulation_code')})."
    except Exception:  # never let a malformed snapshot break a page
        pass
    return "Recorded."


def build_timeline(records):
    records = list(records)
    herb_ids = {
        r.event_data.get("snapshot", {}).get("herb_id")
        for r in records if isinstance(r.event_data, dict)
    } - {None}
    herb_names = dict(Herb.objects.filter(pk__in=herb_ids).values_list("pk", "name"))
    return [
        {
            "sequence": r.sequence,
            "batch_id": r.batch_id,
            "timestamp": r.timestamp,
            "label": L.EVENT_LABELS.get(r.event_type, r.event_type),
            "icon": ICONS.get(r.event_type, "bi-circle"),
            "summary": _summary(r, herb_names),
            "actor": r.actor,
            "current_hash": r.current_hash,
            "previous_hash": r.previous_hash,
            "event_type": r.event_type,
        }
        for r in records
    ]
