from django import template

register = template.Library()

STATUS_CLASSES = {
    # batch statuses
    "PENDING_REVIEW": "warning",
    "REGION_REJECTED": "danger",
    "AWAITING_LAB": "info",
    "LAB_PASSED": "success",
    "REJECTED": "danger",
    "PROCESSING": "primary",
    "PROCESSED": "success",
    "MANUFACTURED": "dark",
    # collection region statuses
    "APPROVED": "success",
    # lab results
    "PASS": "success",
    "FAIL": "danger",
    # processing statuses
    "IN_PROGRESS": "primary",
    "COMPLETED": "success",
}


@register.filter
def status_class(value):
    return STATUS_CLASSES.get(str(value), "secondary")


@register.filter
def short_hash(value, length=12):
    value = str(value or "")
    return f"{value[:length]}…" if len(value) > length else value


@register.filter
def pretty_json(value):
    import json

    return json.dumps(value, indent=2, sort_keys=True, default=str)
