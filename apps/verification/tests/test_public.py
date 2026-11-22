import uuid

from django.test import TestCase, override_settings
from django.urls import reverse

from apps.core.testing import full_chain, make_user
from apps.manufacturing.qr import public_url
from apps.traceability.models import BlockchainRecord
import tempfile

TMP_MEDIA = tempfile.mkdtemp()


@override_settings(MEDIA_ROOT=TMP_MEDIA, PUBLIC_BASE_URL="http://example.test:8000")
class QRTests(TestCase):
    def setUp(self):
        self.formulation, self.batch, self.users = full_chain()

    def test_qr_url_points_to_public_page(self):
        url = public_url(self.formulation)
        self.assertEqual(url, f"http://example.test:8000/verify/{self.formulation.public_id}/")
        self.assertEqual(self.formulation.qr_code.url, url)

    def test_qr_png_generated_and_unique_per_formulation(self):
        qr = self.formulation.qr_code
        with qr.image.open("rb") as fh:
            self.assertEqual(fh.read(8), b"\x89PNG\r\n\x1a\n")
        other, *_ = full_chain()
        self.assertNotEqual(other.public_id, self.formulation.public_id)
        self.assertNotEqual(other.qr_code.url, qr.url)

    def test_public_id_is_unguessable_uuid(self):
        self.assertIsInstance(self.formulation.public_id, uuid.UUID)


@override_settings(MEDIA_ROOT=TMP_MEDIA)
class PublicPageTests(TestCase):
    def setUp(self):
        self.formulation, self.batch, self.users = full_chain()
        self.url = reverse("verification:public", args=[self.formulation.public_id])

    def test_no_login_required_and_shows_required_content(self):
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        c = self.batch.collection
        for text in ("Test Churna", "Test Pharma", "100 g jar", self.batch.batch_id, c.herb.name,
                     c.location_name, "Test Region", "Purity", "Traceability timeline",
                     "Ledger integrity: VALID", str(c.latitude)):
            self.assertContains(resp, text)
        self.assertContains(resp, "data-markers-id")

    def test_no_private_data_exposed(self):
        resp = self.client.get(self.url)
        for secret in (self.users["farmer"].email, self.users["lab"].email, self.users["farmer"].username,
                       self.users["proc"].username, self.users["mfr"].username, "pbkdf2"):
            self.assertNotContains(resp, secret)

    def test_tampering_shows_clear_warning_not_valid(self):
        rec = BlockchainRecord.objects.filter(batch_id=self.batch.batch_id).order_by("sequence").first()
        BlockchainRecord.objects.filter(pk=rec.pk).update(event_data={"forged": True})
        resp = self.client.get(self.url)
        self.assertContains(resp, "WARNING")
        self.assertNotContains(resp, "Ledger integrity: VALID")

    def test_edited_lab_result_flags_warning(self):
        t = self.batch.lab_tests.first()
        type(t).objects.filter(pk=t.pk).update(result="FAIL")
        self.assertContains(self.client.get(self.url), "WARNING")

    def test_unknown_id_is_404(self):
        self.assertEqual(self.client.get(reverse("verification:public", args=[uuid.uuid4()])).status_code, 404)

    def test_lookup_by_product_code_and_batch_id(self):
        r = self.client.post(reverse("verification:lookup"), {"code": self.formulation.formulation_code.lower()})
        self.assertRedirects(r, self.url)
        r = self.client.post(reverse("verification:lookup"), {"code": self.batch.batch_id})
        self.assertRedirects(r, self.url)
        self.assertContains(self.client.post(reverse("verification:lookup"), {"code": "NOPE"}), "No product or batch")

    def test_gps_missing_is_stated_honestly(self):
        from apps.traceability.models import Collection
        Collection.objects.filter(pk=self.batch.collection_id).update(latitude=None, longitude=None, coordinate_source="NONE")
        resp = self.client.get(self.url)
        self.assertContains(resp, "No exact location is claimed")
