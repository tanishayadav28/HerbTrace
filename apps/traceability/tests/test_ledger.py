import hashlib
import json
import threading

from django.test import TestCase, TransactionTestCase

from apps.core.testing import full_chain, make_region, make_user, submit_batch
from apps.traceability import ledger
from apps.traceability.models import BlockchainRecord, LedgerState


class HashTests(TestCase):
    def setUp(self):
        self.user = make_user("FARMER")

    def append(self, batch="HB-X", event="COLLECTION_REGISTERED", data=None):
        return ledger.append_record(batch_id=batch, event_type=event, actor_user=self.user, event_data=data or {"a": 1})

    def test_sha256_matches_independent_computation(self):
        r = self.append()
        payload = json.dumps({
            "sequence": r.sequence, "batch_id": r.batch_id, "event_type": r.event_type, "actor": r.actor,
            "timestamp": r.timestamp.astimezone(__import__("datetime").timezone.utc).isoformat(timespec="microseconds"),
            "event_data": r.event_data, "previous_hash": r.previous_hash}, sort_keys=True, separators=(",", ":"))
        self.assertEqual(r.current_hash, hashlib.sha256(payload.encode()).hexdigest())
        self.assertEqual(len(r.current_hash), 64)

    def test_hash_is_deterministic_and_order_independent(self):
        kw = dict(sequence=1, batch_id="b", event_type="e", actor="a", timestamp=__import__("django").utils.timezone.now(),
                  previous_hash=ledger.GENESIS_HASH)
        self.assertEqual(ledger.compute_hash(event_data={"x": 1, "y": 2}, **kw), ledger.compute_hash(event_data={"y": 2, "x": 1}, **kw))
        self.assertNotEqual(ledger.compute_hash(event_data={"x": 1}, **kw), ledger.compute_hash(event_data={"x": 2}, **kw))

    def test_first_record_uses_genesis_and_links_follow(self):
        a, b, c = self.append(), self.append(), self.append()
        self.assertEqual(a.previous_hash, ledger.GENESIS_HASH)
        self.assertEqual(b.previous_hash, a.current_hash)
        self.assertEqual(c.previous_hash, b.current_hash)
        self.assertEqual([a.sequence, b.sequence, c.sequence], [1, 2, 3])
        state = LedgerState.objects.get(); self.assertEqual((state.head_sequence, state.head_hash), (3, c.current_hash))

    def test_empty_ledger_is_valid(self):
        r = ledger.verify_chain(); self.assertTrue(r.valid); self.assertEqual(r.total, 0)


class IntegrityTests(TestCase):
    def setUp(self):
        self.formulation, self.batch, self.users = full_chain()
        self.records = list(BlockchainRecord.objects.order_by("sequence"))

    def kinds(self):
        return {i["kind"] for i in ledger.verify_chain().issues}

    def test_untouched_chain_is_valid(self):
        r = ledger.verify_chain(); self.assertTrue(r.valid, r.issues); self.assertEqual(r.total, len(self.records))
        self.assertTrue(ledger.integrity_report([self.batch.batch_id])["valid"])

    def test_every_workflow_step_was_recorded(self):
        types = [r.event_type for r in self.records]
        for t in (ledger.COLLECTION_REGISTERED, ledger.LAB_TEST_RECORDED, ledger.PROCESSING_RECORDED,
                  ledger.PROCESSING_STATUS_UPDATED, ledger.MANUFACTURING_RECORDED, ledger.FORMULATION_CREATED):
            self.assertIn(t, types)

    def test_modified_event_data_detected(self):
        target = self.records[1]
        data = dict(target.event_data); data["tampered"] = True
        BlockchainRecord.objects.filter(pk=target.pk).update(event_data=data)
        r = ledger.verify_chain(); self.assertFalse(r.valid)
        self.assertIn("DATA_MODIFIED", {i["kind"] for i in r.issues})
        self.assertIn(target.sequence, {i["sequence"] for i in r.issues})

    def test_modified_batch_id_or_actor_detected(self):
        BlockchainRecord.objects.filter(pk=self.records[0].pk).update(actor="someone-else")
        self.assertIn("DATA_MODIFIED", self.kinds())

    def test_broken_previous_hash_link_detected(self):
        BlockchainRecord.objects.filter(pk=self.records[2].pk).update(previous_hash="f" * 64)
        self.assertIn("BROKEN_LINK", self.kinds())

    def test_deleted_middle_record_detected(self):
        BlockchainRecord.objects.filter(pk=self.records[2].pk).delete()
        k = self.kinds(); self.assertIn("MISSING_RECORD", k); self.assertIn("BROKEN_LINK", k)

    def test_deleted_last_record_detected(self):
        BlockchainRecord.objects.filter(pk=self.records[-1].pk).delete()
        self.assertIn("TRUNCATED", self.kinds())

    def test_rewritten_hash_alone_is_detected(self):
        BlockchainRecord.objects.filter(pk=self.records[1].pk).update(current_hash="a" * 64)
        self.assertFalse(ledger.verify_chain().valid)

    def test_edited_table_row_without_ledger_update_detected(self):
        test = self.batch.lab_tests.first()
        type(test).objects.filter(pk=test.pk).update(purity_percentage=50)   # bypasses the application
        report = ledger.integrity_report([self.batch.batch_id])
        self.assertTrue(report["chain"].valid)                                 # ledger itself untouched
        self.assertFalse(report["valid"])
        self.assertIn("ROW_MODIFIED", {i["kind"] for i in report["data_issues"]})

    def test_deleted_table_row_detected(self):
        from apps.manufacturing.models import QRCode, BatchManufacturing
        self.batch.lab_tests.all()  # sanity
        type(self.batch.lab_tests.first()).objects.all().delete()
        report = ledger.integrity_report([self.batch.batch_id])
        self.assertIn("ROW_DELETED", {i["kind"] for i in report["data_issues"]})

    def test_admin_verify_button_records_result(self):
        from apps.verification.models import Verification
        self.client.force_login(make_user("ADMIN"))
        self.client.post("/trace/ledger/verify/")
        self.assertTrue(Verification.objects.get().is_valid)
        BlockchainRecord.objects.filter(pk=self.records[1].pk).update(batch_id="HB-FORGED")
        self.client.post("/trace/ledger/verify/")
        self.assertFalse(Verification.objects.first().is_valid)

    def test_ledger_page_is_admin_only_and_never_trusts_client_hash(self):
        self.client.force_login(make_user("FARMER"))
        self.assertEqual(self.client.get("/trace/ledger/").status_code, 403)
        self.assertEqual(self.client.post("/trace/ledger/verify/", {"current_hash": "x"}).status_code, 403)
        self.client.force_login(make_user("ADMIN"))
        resp = self.client.get("/trace/ledger/")
        self.assertContains(resp, "VALID"); self.assertContains(resp, self.records[0].current_hash[:12])
