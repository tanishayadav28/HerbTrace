"""Application-level SHA-256 hash-linked ledger.

What this IS: an append-only list of records where every record stores the
hash of the previous record, so editing, reordering or removing a record in the
middle of the chain is detectable.

What this is NOT: a distributed or decentralised blockchain. There is no
mining, no consensus and no smart contract. Anyone with full write access to
the database *and* knowledge of the algorithm could rebuild the whole chain, and
the ledger cannot prove that physical herbs match their records. It provides
record integrity and modification detection only.
"""
import hashlib
import json
from dataclasses import dataclass, field
from datetime import timezone as dt_timezone

from django.apps import apps
from django.db import transaction
from django.utils import timezone

from .models import BlockchainRecord, LedgerState

# The "previous hash" of record #1. 64 zeros, defined once, documented in the UI.
GENESIS_HASH = "0" * 64

# Event types
COLLECTION_REGISTERED = "COLLECTION_REGISTERED"
REGION_REVIEWED = "REGION_REVIEWED"
LAB_TEST_RECORDED = "LAB_TEST_RECORDED"
PROCESSING_RECORDED = "PROCESSING_RECORDED"
PROCESSING_STATUS_UPDATED = "PROCESSING_STATUS_UPDATED"
MANUFACTURING_RECORDED = "MANUFACTURING_RECORDED"
FORMULATION_CREATED = "FORMULATION_CREATED"

EVENT_LABELS = {
    COLLECTION_REGISTERED: "Collection registered",
    REGION_REVIEWED: "Region reviewed by admin",
    LAB_TEST_RECORDED: "Laboratory test recorded",
    PROCESSING_RECORDED: "Processing step recorded",
    PROCESSING_STATUS_UPDATED: "Processing status updated",
    MANUFACTURING_RECORDED: "Manufacturing recorded",
    FORMULATION_CREATED: "Final formulation created",
}


# ----------------------------------------------------------------- hashing
def _utc_iso(dt) -> str:
    return dt.astimezone(dt_timezone.utc).isoformat(timespec="microseconds")


def canonical_payload(*, sequence, batch_id, event_type, actor, timestamp, event_data, previous_hash) -> str:
    """Deterministic serialisation: sorted keys, no whitespace, UTC timestamp."""
    return json.dumps(
        {
            "sequence": int(sequence),
            "batch_id": batch_id,
            "event_type": event_type,
            "actor": actor,
            "timestamp": _utc_iso(timestamp),
            "event_data": event_data,
            "previous_hash": previous_hash,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )


def compute_hash(**fields) -> str:
    return hashlib.sha256(canonical_payload(**fields).encode("utf-8")).hexdigest()


def record_hash(record: BlockchainRecord) -> str:
    return compute_hash(
        sequence=record.sequence,
        batch_id=record.batch_id,
        event_type=record.event_type,
        actor=record.actor,
        timestamp=record.timestamp,
        event_data=record.event_data,
        previous_hash=record.previous_hash,
    )


# ----------------------------------------------------------------- writing
def _actor_label(user) -> str:
    if user is None:
        return "system"
    return f"{user.username} ({user.effective_role})"


@transaction.atomic
def append_record(*, batch_id, event_type, actor_user, event_data) -> BlockchainRecord:
    """Append one record. The hash is always computed here, on the server.

    ``LedgerState`` is locked with SELECT … FOR UPDATE, so two concurrent
    writers are serialised and cannot fork the chain. The unique constraint on
    ``sequence`` is a second line of defence.
    """
    state, _ = LedgerState.objects.select_for_update().get_or_create(
        id=1, defaults={"head_sequence": 0, "head_hash": GENESIS_HASH}
    )
    sequence = state.head_sequence + 1
    previous_hash = state.head_hash
    # Round-trip through JSON so the stored value equals the hashed value.
    event_data = json.loads(json.dumps(event_data, sort_keys=True, default=str))
    timestamp = timezone.now()
    actor = _actor_label(actor_user)
    current_hash = compute_hash(
        sequence=sequence, batch_id=batch_id, event_type=event_type, actor=actor,
        timestamp=timestamp, event_data=event_data, previous_hash=previous_hash,
    )
    record = BlockchainRecord.objects.create(
        sequence=sequence, batch_id=batch_id, event_type=event_type, actor=actor,
        actor_user=actor_user, timestamp=timestamp, event_data=event_data,
        previous_hash=previous_hash, current_hash=current_hash,
    )
    state.head_sequence = sequence
    state.head_hash = current_hash
    state.save(update_fields=["head_sequence", "head_hash"])
    return record


def record_event(*, batch_id, event_type, actor_user, obj=None, extra=None) -> BlockchainRecord:
    """Append an event, snapshotting ``obj`` so data tables can be cross-checked."""
    data = dict(extra or {})
    if obj is not None:
        # Snapshot what the database actually stores (e.g. Decimal "12.5" -> "12.500"),
        # otherwise the later consistency check would see false differences.
        obj.refresh_from_db()
        data["ref"] = {"model": obj._meta.label, "pk": obj.pk}
        data["snapshot"] = obj.ledger_snapshot()
    return append_record(
        batch_id=batch_id, event_type=event_type, actor_user=actor_user, event_data=data
    )


# ------------------------------------------------------------ verification
@dataclass
class ChainResult:
    valid: bool
    total: int
    issues: list = field(default_factory=list)
    head_sequence: int = 0
    head_hash: str = GENESIS_HASH
    checked_at: object = None

    @property
    def status_label(self) -> str:
        return "VALID" if self.valid else "INVALID"


def verify_chain() -> ChainResult:
    """Re-compute the whole chain and report every problem found."""
    issues = []
    expected_seq = 1
    previous = GENESIS_HASH
    total = 0
    last_seq = 0
    last_hash = GENESIS_HASH

    for rec in BlockchainRecord.objects.order_by("sequence").iterator():
        total += 1
        if rec.sequence != expected_seq:
            issues.append({
                "sequence": rec.sequence,
                "kind": "MISSING_RECORD",
                "message": f"Expected record #{expected_seq} but found #{rec.sequence}: "
                           "one or more records are missing.",
            })
            expected_seq = rec.sequence
        if rec.previous_hash != previous:
            issues.append({
                "sequence": rec.sequence,
                "kind": "BROKEN_LINK",
                "message": f"Record #{rec.sequence} does not link to the hash of the "
                           "record before it.",
            })
        if record_hash(rec) != rec.current_hash:
            issues.append({
                "sequence": rec.sequence,
                "kind": "DATA_MODIFIED",
                "message": f"Record #{rec.sequence} content no longer matches its stored hash "
                           "(data was modified).",
            })
        previous = rec.current_hash
        last_seq, last_hash = rec.sequence, rec.current_hash
        expected_seq = rec.sequence + 1

    state = LedgerState.objects.filter(id=1).first()
    if state:
        if state.head_sequence > last_seq:
            issues.append({
                "sequence": state.head_sequence,
                "kind": "TRUNCATED",
                "message": f"The ledger head says record #{state.head_sequence} exists but the "
                           f"last stored record is #{last_seq}: trailing records were removed.",
            })
        elif state.head_sequence == last_seq and state.head_hash != last_hash:
            issues.append({
                "sequence": last_seq,
                "kind": "HEAD_MISMATCH",
                "message": "The stored chain head hash does not match the last record.",
            })
    elif total:
        issues.append({"sequence": None, "kind": "HEAD_MISSING",
                       "message": "Ledger records exist but the chain head anchor is missing."})

    return ChainResult(
        valid=not issues, total=total, issues=issues,
        head_sequence=last_seq, head_hash=last_hash, checked_at=timezone.now(),
    )


def verify_data_consistency(batch_ids) -> list:
    """Compare live table rows with the newest ledger snapshot of the same row.

    The hash chain protects the ledger itself. This extra check notices when a
    row in an ordinary table (e.g. a lab result) was edited *without* the
    ledger being updated.
    """
    issues = []
    records = BlockchainRecord.objects.filter(batch_id__in=list(batch_ids)).order_by("sequence")
    latest = {}
    for rec in records:
        ref = rec.event_data.get("ref")
        if ref and "snapshot" in rec.event_data:
            latest[(ref["model"], ref["pk"])] = rec
    for (label, pk), rec in latest.items():
        model = apps.get_model(label)
        obj = model.objects.filter(pk=pk).first()
        if obj is None:
            issues.append({"sequence": rec.sequence, "kind": "ROW_DELETED",
                           "message": f"{label} #{pk} referenced by ledger record #{rec.sequence} no longer exists."})
            continue
        if obj.ledger_snapshot() != rec.event_data["snapshot"]:
            issues.append({"sequence": rec.sequence, "kind": "ROW_MODIFIED",
                           "message": f"{label} #{pk} differs from what ledger record "
                                      f"#{rec.sequence} certified (database row edited outside the application)."})
    return issues


def integrity_report(batch_ids=None) -> dict:
    """Chain verification plus (optionally) data-row consistency for given batches."""
    chain = verify_chain()
    data_issues = verify_data_consistency(batch_ids) if batch_ids else []
    return {
        "chain": chain,
        "data_issues": data_issues,
        "valid": chain.valid and not data_issues,
    }
