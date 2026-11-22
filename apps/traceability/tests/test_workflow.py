import re
from decimal import Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase
from django.urls import reverse

from apps.core.testing import *  # noqa: F401,F403
from apps.core.testing import (INSIDE, OUTSIDE, full_chain, lab_test, make_collection, make_herb,
                               make_region, make_user, manufacture, process, submit_batch)
from apps.herbs.geo import haversine_km
from apps.processing.models import Processing
from apps.processing.services import add_processing, update_status
from apps.traceability.models import Batch, BlockchainRecord, Collection
from apps.traceability.services import review_region


class BatchIdTests(TestCase):
    def test_format_and_uniqueness(self):
        farmer = make_user("FARMER"); make_region()
        ids = {submit_batch(farmer).batch_id for _ in range(25)}
        self.assertEqual(len(ids), 25)
        for i in ids:
            self.assertRegex(i, r"^HB-\d{8}-[A-HJ-NP-Z2-9]{6}$")


class CollectionTests(TestCase):
    def setUp(self):
        self.farmer = make_user("FARMER"); make_region()

    def test_farmer_can_submit_collection_and_receives_batch_id(self):
        self.client.force_login(self.farmer)
        herb = make_herb()
        resp = self.client.post(reverse("traceability:collection_create"), {
            "herb": herb.pk, "collection_date": "2026-10-01", "collection_time": "08:15",
            "quantity": "12.5", "unit": "kg", "collection_method": "HAND", "source_type": "CULTIVATED",
            "sustainability_details": "ok", "location_name": "Field A", "latitude": INSIDE[0],
            "longitude": INSIDE[1], "coordinate_source": "GPS", "gps_accuracy_m": "9"}, follow=True)
        batch = Batch.objects.get()
        self.assertRedirects(resp, reverse("traceability:batch_detail", args=[batch.batch_id]))
        self.assertContains(resp, batch.batch_id)
        self.assertEqual(batch.collection.collector, self.farmer)
        self.assertEqual(batch.status, Batch.Status.AWAITING_LAB)

    def test_manual_coordinates_work_and_invalid_rejected(self):
        self.client.force_login(self.farmer)
        base = {"herb": make_herb().pk, "collection_date": "2026-10-01", "collection_time": "08:15",
                "quantity": "1", "unit": "kg", "collection_method": "HAND", "source_type": "CULTIVATED",
                "location_name": "X"}
        bad = self.client.post(reverse("traceability:collection_create"), {**base, "latitude": "95", "longitude": "75"})
        self.assertEqual(bad.status_code, 200); self.assertEqual(Collection.objects.count(), 0)
        half = self.client.post(reverse("traceability:collection_create"), {**base, "latitude": "24"})
        self.assertEqual(Collection.objects.count(), 0)
        self.client.post(reverse("traceability:collection_create"), {**base, "latitude": INSIDE[0], "longitude": INSIDE[1]})
        self.assertEqual(Collection.objects.get().coordinate_source, "MANUAL")

    def test_wild_collection_requires_sustainability_info(self):
        self.client.force_login(self.farmer)
        resp = self.client.post(reverse("traceability:collection_create"), {
            "herb": make_herb().pk, "collection_date": "2026-10-01", "collection_time": "08:15",
            "quantity": "1", "unit": "kg", "collection_method": "HAND", "source_type": "WILD", "location_name": "X"})
        self.assertContains(resp, "Sustainability information is required")

    def test_future_date_and_negative_quantity_rejected(self):
        self.client.force_login(self.farmer)
        resp = self.client.post(reverse("traceability:collection_create"), {
            "herb": make_herb().pk, "collection_date": "2099-01-01", "collection_time": "08:15",
            "quantity": "-1", "unit": "kg", "collection_method": "HAND", "source_type": "CULTIVATED", "location_name": "X"})
        self.assertEqual(Collection.objects.count(), 0)

    def test_farmer_sees_only_own_batches(self):
        other = make_user("FARMER")
        theirs = submit_batch(other)
        self.client.force_login(self.farmer)
        self.assertEqual(self.client.get(reverse("traceability:batch_detail", args=[theirs.batch_id])).status_code, 404)


class RegionVerificationTests(TestCase):
    def setUp(self):
        self.farmer = make_user("FARMER"); self.region = make_region()

    def test_inside_region_is_approved_and_goes_to_lab(self):
        b = submit_batch(self.farmer)
        self.assertEqual(b.collection.region, self.region)
        self.assertEqual((b.collection.region_status, b.status), ("APPROVED", Batch.Status.AWAITING_LAB))
        self.assertIn("Inside approved region", b.collection.region_reason)

    def test_outside_region_is_pending_with_clear_reason(self):
        b = submit_batch(self.farmer, coords=OUTSIDE)
        self.assertEqual((b.collection.region_status, b.status), ("PENDING_REVIEW", Batch.Status.PENDING_REVIEW))
        self.assertIn("Outside all approved regions", b.collection.region_reason)

    def test_missing_gps_is_pending_and_makes_no_location_claim(self):
        b = submit_batch(self.farmer, coords=None)
        self.assertEqual(b.status, Batch.Status.PENDING_REVIEW)
        self.assertFalse(b.collection.has_coordinates)
        self.assertIn("No GPS coordinates", b.collection.region_reason)

    def test_wild_without_permit_needs_review(self):
        b = submit_batch(self.farmer, source="WILD", permit=False)
        self.assertEqual(b.status, Batch.Status.PENDING_REVIEW)

    def test_region_restricted_to_listed_herbs(self):
        other = make_herb("Brahmi")
        self.region.herbs.set([make_herb()])
        self.assertEqual(submit_batch(self.farmer, herb=other).status, Batch.Status.PENDING_REVIEW)

    def test_inactive_region_not_used(self):
        self.region.is_active = False; self.region.save()
        self.assertEqual(submit_batch(self.farmer).status, Batch.Status.PENDING_REVIEW)

    def test_boundary_uses_radius(self):
        self.assertLess(haversine_km(24.072, 75.069, 24.072, 75.069), 0.001)
        near = self.region.contains(Decimal("24.30"), Decimal("75.069"))   # ~25 km, radius 30
        far = self.region.contains(Decimal("24.60"), Decimal("75.069"))    # ~58 km
        self.assertTrue(near); self.assertFalse(far)

    def test_pending_batch_cannot_be_tested_until_admin_approves(self):
        lab = make_user("LAB"); admin = make_user("ADMIN")
        b = submit_batch(self.farmer, coords=OUTSIDE)
        with self.assertRaises(ValidationError):
            lab_test(b, lab)
        review_region(b, admin, True, "ok"); b.refresh_from_db()
        self.assertEqual(b.status, Batch.Status.AWAITING_LAB)
        lab_test(b, lab)

    def test_admin_rejection_is_final(self):
        admin = make_user("ADMIN"); lab = make_user("LAB")
        b = submit_batch(self.farmer, coords=OUTSIDE)
        review_region(b, admin, False); b.refresh_from_db()
        self.assertEqual(b.status, Batch.Status.REGION_REJECTED)
        with self.assertRaises(ValidationError):
            lab_test(b, lab)
        with self.assertRaises(ValidationError):
            review_region(b, admin, True)


class LabWorkflowTests(TestCase):
    def setUp(self):
        self.farmer, self.lab = make_user("FARMER"), make_user("LAB"); make_region()

    def test_pass_moves_to_processing_queue(self):
        b = submit_batch(self.farmer); t = lab_test(b, self.lab, "PASS"); b.refresh_from_db()
        self.assertEqual(b.status, Batch.Status.LAB_PASSED); self.assertEqual(t.tested_by, self.lab)

    def test_fail_rejects_batch(self):
        b = submit_batch(self.farmer); lab_test(b, self.lab, "FAIL"); b.refresh_from_db()
        self.assertEqual(b.status, Batch.Status.REJECTED)

    def test_cannot_test_twice(self):
        b = submit_batch(self.farmer); lab_test(b, self.lab)
        with self.assertRaises(ValidationError):
            lab_test(b, self.lab)

    def test_lab_form_validation_and_post(self):
        b = submit_batch(self.farmer); self.client.force_login(self.lab)
        url = reverse("laboratory:test_create", args=[b.batch_id])
        data = {"test_date": "2026-10-20", "purity_percentage": "101", "moisture_percentage": "5", "result": "PASS"}
        self.client.post(url, data); b.refresh_from_db()
        self.assertEqual(b.status, Batch.Status.AWAITING_LAB)           # purity > 100 refused
        self.client.post(url, {**data, "purity_percentage": "98"}); b.refresh_from_db()
        self.assertEqual(b.status, Batch.Status.LAB_PASSED)

    def test_fail_requires_a_reason(self):
        b = submit_batch(self.farmer); self.client.force_login(self.lab)
        self.client.post(reverse("laboratory:test_create", args=[b.batch_id]),
                         {"test_date": "2026-10-20", "purity_percentage": "50", "moisture_percentage": "5", "result": "FAIL"})
        b.refresh_from_db(); self.assertEqual(b.status, Batch.Status.AWAITING_LAB)


class ProcessingRestrictionTests(TestCase):
    def setUp(self):
        self.farmer, self.lab, self.proc = make_user("FARMER"), make_user("LAB"), make_user("PROCESSOR")
        make_region()

    def _rec(self):
        import datetime as dt
        return Processing(stage="DRYING", processing_date=dt.date(2026, 10, 1), location="U", description="d")

    def test_unlabbed_batch_cannot_be_processed(self):
        b = submit_batch(self.farmer)
        with self.assertRaises(ValidationError):
            add_processing(b, self.proc, self._rec())

    def test_failed_batch_cannot_be_processed(self):
        b = submit_batch(self.farmer); lab_test(b, self.lab, "FAIL")
        with self.assertRaises(ValidationError):
            add_processing(b, self.proc, self._rec())
        self.client.force_login(self.proc)
        resp = self.client.post(reverse("processing:add", args=[b.batch_id]), {
            "stage": "DRYING", "processing_date": "2026-10-01", "location": "U", "description": "d", "status": "IN_PROGRESS"})
        self.assertEqual(Processing.objects.count(), 0)

    def test_multiple_steps_and_status_sync(self):
        b = submit_batch(self.farmer); lab_test(b, self.lab)
        r1 = add_processing(b, self.proc, self._rec()); b.refresh_from_db()
        self.assertEqual(b.status, Batch.Status.PROCESSING)
        r2 = add_processing(b, self.proc, self._rec())
        update_status(r1, self.proc, "COMPLETED"); b.refresh_from_db()
        self.assertEqual(b.status, Batch.Status.PROCESSING)
        update_status(r2, self.proc, "COMPLETED"); b.refresh_from_db()
        self.assertEqual(b.status, Batch.Status.PROCESSED)
        self.assertEqual(b.processing_records.count(), 2)

    def test_cannot_modify_another_processors_record(self):
        b = submit_batch(self.farmer); lab_test(b, self.lab)
        rec = add_processing(b, self.proc, self._rec())
        with self.assertRaises(PermissionDenied):
            update_status(rec, make_user("PROCESSOR"), "COMPLETED")

    def test_manufactured_batch_is_frozen(self):
        formulation, batch, users = full_chain()
        rec = batch.processing_records.first()
        with self.assertRaises(ValidationError):
            update_status(rec, users["proc"], "IN_PROGRESS")


class ManufacturingRestrictionTests(TestCase):
    def setUp(self):
        self.farmer, self.lab, self.proc, self.mfr = (make_user(r) for r in ("FARMER", "LAB", "PROCESSOR", "MANUFACTURER"))
        make_region()

    def test_failed_batch_cannot_be_manufactured(self):
        b = submit_batch(self.farmer); lab_test(b, self.lab, "FAIL")
        with self.assertRaises(ValidationError):
            manufacture([b], self.mfr)

    def test_unprocessed_batch_cannot_be_manufactured(self):
        b = submit_batch(self.farmer); lab_test(b, self.lab)
        with self.assertRaises(ValidationError):
            manufacture([b], self.mfr)

    def test_in_progress_batch_cannot_be_manufactured(self):
        b = submit_batch(self.farmer); lab_test(b, self.lab); process(b, self.proc, "IN_PROGRESS")
        with self.assertRaises(ValidationError):
            manufacture([b], self.mfr)

    def test_one_bad_batch_blocks_whole_run_atomically(self):
        good = submit_batch(self.farmer); lab_test(good, self.lab); process(good, self.proc)
        bad = submit_batch(self.farmer); lab_test(bad, self.lab, "FAIL")
        before = BlockchainRecord.objects.count()
        with self.assertRaises(ValidationError):
            manufacture([good, bad], self.mfr)
        good.refresh_from_db()
        self.assertEqual(good.status, Batch.Status.PROCESSED)
        self.assertEqual(BlockchainRecord.objects.count(), before)

    def test_batch_cannot_be_manufactured_twice(self):
        formulation, batch, users = full_chain()
        with self.assertRaises(ValidationError):
            manufacture([batch], users["mfr"])

    def test_tampered_form_cannot_submit_ineligible_batch(self):
        b = submit_batch(self.farmer); lab_test(b, self.lab, "FAIL")
        self.client.force_login(self.mfr)
        resp = self.client.post(reverse("manufacturing:create"), {
            "batches": [b.pk], "manufacturer_name": "M", "manufacturing_date": "2026-10-01", "location": "L",
            "details": "d", "product_name": "P", "formulation_date": "2026-10-02", "packaging_info": "p"})
        self.assertEqual(resp.status_code, 200)
        from apps.manufacturing.models import FinalFormulation
        self.assertEqual(FinalFormulation.objects.count(), 0)

    def test_full_manufacturer_form_flow(self):
        b = submit_batch(self.farmer); lab_test(b, self.lab); process(b, self.proc)
        self.client.force_login(self.mfr)
        resp = self.client.post(reverse("manufacturing:create"), {
            "batches": [b.pk], "manufacturer_name": "M", "manufacturing_date": "2026-10-01", "location": "L",
            "details": "d", "product_name": "Prod", "formulation_date": "2026-10-02", "packaging_info": "p"})
        from apps.manufacturing.models import FinalFormulation
        f = FinalFormulation.objects.get()
        self.assertRedirects(resp, reverse("manufacturing:detail", args=[f.pk]))
        b.refresh_from_db(); self.assertEqual(b.status, Batch.Status.MANUFACTURED)
        self.assertTrue(f.qr_code.image.name)
