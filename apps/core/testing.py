"""Small factories shared by the test-suite."""
import datetime as dt
import itertools
from decimal import Decimal

from django.utils import timezone

from apps.accounts.models import User
from apps.herbs.models import ApprovedRegion, Herb
from apps.laboratory.models import LaboratoryTest
from apps.laboratory.services import record_test
from apps.manufacturing.models import FinalFormulation, Manufacturing
from apps.manufacturing.services import create_formulation
from apps.processing.models import Processing
from apps.processing.services import add_processing, update_status
from apps.traceability.models import Collection
from apps.traceability.services import register_collection

PASSWORD = "Test#Pass2026"
_n = itertools.count(1)

# Centre of the test region (Mandsaur) and a point ~1 km away / far outside.
INSIDE = ("24.080000", "75.060000")
OUTSIDE = ("19.076000", "72.877700")


def make_user(role=User.Role.FARMER, approval=User.Approval.APPROVED, **kw):
    n = next(_n)
    return User.objects.create_user(
        username=kw.pop("username", f"user{n}"), email=kw.pop("email", f"user{n}@example.com"),
        password=PASSWORD, role=role, approval_status=approval, **kw)


def make_herb(name="Ashwagandha"):
    return Herb.objects.get_or_create(name=name, defaults={"botanical_name": "Withania somnifera"})[0]


def make_region(**kw):
    return ApprovedRegion.objects.get_or_create(
        name=kw.pop("name", "Test Region"),
        defaults=dict(center_latitude=Decimal("24.072"), center_longitude=Decimal("75.069"),
                      radius_km=Decimal(kw.pop("radius_km", "30")), **kw))[0]


def make_collection(farmer, herb=None, coords=INSIDE, source="CULTIVATED", permit=True):
    herb = herb or make_herb()
    return Collection(
        herb=herb, collector=farmer, collection_date=timezone.localdate() - dt.timedelta(days=5),
        collection_time=dt.time(8, 0), quantity=Decimal("10"), unit="kg", collection_method="HAND",
        source_type=source, sustainability_details="ok", permit_available=permit,
        permit_number="P-1" if permit else "",
        latitude=None if coords is None else Decimal(coords[0]),
        longitude=None if coords is None else Decimal(coords[1]),
        coordinate_source="GPS" if coords else "NONE", location_name="Test field")


def submit_batch(farmer, **kw):
    return register_collection(make_collection(farmer, **kw))


def lab_test(batch, lab, result="PASS"):
    return record_test(batch, lab, LaboratoryTest(
        test_date=timezone.localdate() - dt.timedelta(days=3), purity_percentage=Decimal("97"),
        moisture_percentage=Decimal("6"), result=result, remarks="r"))


def process(batch, proc, status=Processing.Status.COMPLETED):
    rec = add_processing(batch, proc, Processing(
        stage="DRYING", processing_date=timezone.localdate() - dt.timedelta(days=2),
        location="Unit", description="dried"))
    if status == Processing.Status.COMPLETED:
        update_status(rec, proc, status)
    batch.refresh_from_db()
    return rec


def manufacture(batches, mfr):
    return create_formulation(
        user=mfr, batches=batches,
        manufacturing=Manufacturing(
            manufacturer_name="Test Pharma", manufacturing_date=timezone.localdate() - dt.timedelta(days=1),
            location="Plant", details="blend"),
        formulation=FinalFormulation(
            product_name="Test Churna", formulation_date=timezone.localdate(), packaging_info="100 g jar"))


def full_chain():
    """Return (formulation, batch, users) for a batch taken all the way to a product."""
    farmer, lab, proc, mfr = (make_user(r) for r in ("FARMER", "LAB", "PROCESSOR", "MANUFACTURER"))
    make_region()
    batch = submit_batch(farmer)
    lab_test(batch, lab)
    process(batch, proc)
    return manufacture([batch], mfr), batch, dict(farmer=farmer, lab=lab, proc=proc, mfr=mfr)
