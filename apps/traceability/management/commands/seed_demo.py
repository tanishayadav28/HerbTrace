"""Create clearly-marked DEMONSTRATION data for local development.

    python manage.py seed_demo            # create demo users, herbs, regions and batches
    python manage.py seed_demo --reset    # wipe all traceability data first, then seed

Every record created here has ``is_demo=True`` (or is a demo account) and the
public pages show a "Demonstration data" label. None of it is a real collection
or laboratory result. The demo passwords below are for local development ONLY.
"""
import datetime as dt
from decimal import Decimal

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.herbs.models import ApprovedRegion, Herb
from apps.laboratory.models import LaboratoryTest
from apps.laboratory.services import record_test
from apps.manufacturing.models import (
    BatchManufacturing, FinalFormulation, Manufacturing, QRCode,
)
from apps.manufacturing.services import create_formulation
from apps.processing.models import Processing
from apps.processing.services import add_processing, update_status
from apps.traceability import ledger
from apps.traceability.models import Batch, BlockchainRecord, Collection, LedgerState
from apps.traceability.services import register_collection, review_region
from apps.verification.models import Verification

DEMO_PASSWORD = "DemoPass#2026"

DEMO_USERS = [
    # username, role, first, last, approval
    ("demo_admin", User.Role.ADMIN, "Asha", "Admin", User.Approval.APPROVED),
    ("demo_farmer", User.Role.FARMER, "Ramesh", "Patel", User.Approval.APPROVED),
    ("demo_farmer2", User.Role.FARMER, "Sunita", "Rawat", User.Approval.APPROVED),
    ("demo_lab", User.Role.LAB, "Lata", "Iyer", User.Approval.APPROVED),
    ("demo_processor", User.Role.PROCESSOR, "Pooja", "Nair", User.Approval.APPROVED),
    ("demo_manufacturer", User.Role.MANUFACTURER, "Manoj", "Verma", User.Approval.APPROVED),
    ("demo_pending", User.Role.FARMER, "Pending", "Farmer", User.Approval.PENDING),
]

HERBS = [
    ("Ashwagandha", "Withania somnifera", "root", "Adaptogenic root used in Ayurvedic tonics."),
    ("Tulsi", "Ocimum tenuiflorum", "leaf", "Holy basil leaf used for respiratory and general wellness formulations."),
    ("Brahmi", "Bacopa monnieri", "whole plant", "Herb traditionally used in memory and nervine tonics."),
    ("Guduchi", "Tinospora cordifolia", "stem", "Climber whose stem is used in immunity-supporting formulations."),
    ("Amla", "Phyllanthus emblica", "fruit", "Vitamin C rich fruit used in Rasayana preparations."),
    ("Neem", "Azadirachta indica", "leaf", "Bitter leaf used in skin-care and purifying formulations."),
    ("Shatavari", "Asparagus racemosus", "root", "Tuberous root used in women's health formulations."),
    ("Guggul", "Commiphora wightii", "resin", "Oleo-gum resin; collection is regulated and permit-controlled."),
]

# name, state, lat, lng, radius_km, herbs (empty = all)
REGIONS = [
    ("Mandsaur Medicinal Belt", "Madhya Pradesh", "24.072000", "75.069000", "45", ["Ashwagandha", "Shatavari", "Amla"]),
    ("Doon Valley Forest Zone", "Uttarakhand", "30.316500", "78.032200", "55", []),
    ("Wayanad Herbal Zone", "Kerala", "11.685400", "76.132000", "45", ["Brahmi", "Tulsi", "Guduchi", "Neem"]),
]


class Command(BaseCommand):
    help = "Create demonstration users, herbs, regions and sample batches (local development only)."

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true",
                            help="Delete ALL traceability data (including the ledger) before seeding.")
        parser.add_argument("--force", action="store_true",
                            help="Allow running when DJANGO_DEBUG is False (not recommended).")

    # ------------------------------------------------------------------
    def handle(self, *args, **opts):
        if not settings.DEBUG and not opts["force"]:
            raise CommandError("Refusing to seed demo data while DEBUG is off. Use --force if you are sure.")
        if opts["reset"]:
            self._wipe()
        elif Collection.objects.filter(is_demo=True).exists():
            self.stdout.write(self.style.WARNING(
                "Demo data already exists. Run with --reset to rebuild it from scratch."))
            self._print_credentials()
            return

        with transaction.atomic():
            users = self._users()
            herbs = self._herbs()
            self._regions(herbs)
            self._batches(users, herbs)
        report = ledger.verify_chain()
        self.stdout.write(self.style.SUCCESS(
            f"Seeded demonstration data. Ledger: {report.total} records, {report.status_label}."))
        self._print_credentials()

    # ------------------------------------------------------------------
    def _wipe(self):
        self.stdout.write("Removing existing traceability data…")
        with transaction.atomic():
            for model in (QRCode, BatchManufacturing, FinalFormulation, Manufacturing, Processing,
                          LaboratoryTest, BlockchainRecord, Verification, Batch, Collection):
                model.objects.all().delete()
            LedgerState.objects.all().delete()

    def _users(self):
        users = {}
        for username, role, first, last, approval in DEMO_USERS:
            user, created = User.objects.get_or_create(
                username=username,
                defaults=dict(email=f"{username}@example.invalid", role=role, first_name=first,
                              last_name=last, approval_status=approval, organization="DEMO DATA",
                              is_staff=False),
            )
            if created:
                user.set_password(DEMO_PASSWORD)
                user.save()
            users[username] = user
        return users

    def _herbs(self):
        herbs = {}
        for name, botanical, part, desc in HERBS:
            herb, _ = Herb.objects.get_or_create(
                name=name, defaults=dict(botanical_name=botanical, part_used=part, description=desc))
            herbs[name] = herb
        return herbs

    def _regions(self, herbs):
        for name, state, lat, lng, radius, herb_names in REGIONS:
            region, created = ApprovedRegion.objects.get_or_create(
                name=name,
                defaults=dict(state=state, center_latitude=Decimal(lat), center_longitude=Decimal(lng),
                              radius_km=Decimal(radius), notes="Demonstration region (not an official boundary)."),
            )
            if created and herb_names:
                region.herbs.set([herbs[n] for n in herb_names])

    # ------------------------------------------------------------------
    def _collect(self, farmer, herb, days_ago, qty, lat, lng, place, *, source="CULTIVATED",
                 permit=True, method="HAND", coord_source="GPS"):
        day = timezone.localdate() - dt.timedelta(days=days_ago)
        c = Collection(
            herb=herb, collector=farmer, collection_date=day, collection_time=dt.time(7, 30),
            quantity=Decimal(qty), unit="kg", collection_method=method, source_type=source,
            sustainability_details="DEMO: harvested below 30% of stand, regrowth period observed.",
            permit_available=permit, permit_number="DEMO-PERMIT-001" if permit else "",
            latitude=None if lat is None else Decimal(lat), longitude=None if lng is None else Decimal(lng),
            coordinate_source=coord_source if lat is not None else "NONE",
            gps_accuracy_m=8 if coord_source == "GPS" and lat is not None else None,
            location_name=place, is_demo=True,
        )
        return register_collection(c)

    def _test(self, lab, batch, days_ago, purity, moisture, result, **extra):
        t = LaboratoryTest(
            test_date=timezone.localdate() - dt.timedelta(days=days_ago),
            purity_percentage=Decimal(purity), moisture_percentage=Decimal(moisture), result=result,
            observations=extra.get("observations", "DEMO: sample result for demonstration."),
            contamination_details=extra.get("contamination", ""),
            remarks=extra.get("remarks", "DEMO DATA: not an actual laboratory result."), is_demo=True,
        )
        return record_test(batch, lab, t)

    def _process(self, proc, batch, steps):
        """steps: list of (stage, days_ago, location, description, final_status)."""
        for stage, days_ago, place, desc, final in steps:
            rec = Processing(
                stage=stage, processing_date=timezone.localdate() - dt.timedelta(days=days_ago),
                location=place, description=desc, status=Processing.Status.IN_PROGRESS, is_demo=True,
            )
            rec = add_processing(batch, proc, rec)
            if final == Processing.Status.COMPLETED:
                update_status(rec, proc, Processing.Status.COMPLETED)
        batch.refresh_from_db()

    def _batches(self, u, h):
        farmer, farmer2 = u["demo_farmer"], u["demo_farmer2"]
        lab, proc, mfr, admin = u["demo_lab"], u["demo_processor"], u["demo_manufacturer"], u["demo_admin"]
        DONE, OPEN = Processing.Status.COMPLETED, Processing.Status.IN_PROGRESS

        # 1. Ashwagandha, fully through to a product
        ash = self._collect(farmer, h["Ashwagandha"], 40, "42.500", "24.081200", "75.058800",
                            "Demo field, Mandsaur", source="CULTIVATED")
        self._test(lab, ash, 36, "98.40", "6.10", "PASS")
        self._process(proc, ash, [
            ("CLEANING", 33, "Mandsaur Processing Unit (demo)", "Sorted and washed roots.", DONE),
            ("DRYING", 31, "Mandsaur Processing Unit (demo)", "Shade-dried for 6 days.", DONE),
            ("GRINDING", 24, "Mandsaur Processing Unit (demo)", "Milled to 80-mesh powder.", DONE),
        ])

        # 2. Tulsi, fully through to the same product
        tulsi = self._collect(farmer2, h["Tulsi"], 38, "18.000", "11.690100", "76.140500",
                              "Demo plot, Wayanad", source="CULTIVATED")
        self._test(lab, tulsi, 34, "97.80", "5.40", "PASS")
        self._process(proc, tulsi, [
            ("CLEANING", 30, "Wayanad Processing Unit (demo)", "Leaves sorted, stems removed.", DONE),
            ("DRYING", 28, "Wayanad Processing Unit (demo)", "Low-temperature drying.", DONE),
        ])
        create_formulation(
            user=mfr, batches=[ash, tulsi],
            manufacturing=Manufacturing(
                manufacturer_name="Demo Ayurveda Pharmacy (sample)", manufacturing_date=timezone.localdate() - dt.timedelta(days=15),
                location="Indore Plant (demo)", details="DEMO: blended powders, GMP-style batch record. Not a real manufacturing run.",
                is_demo=True),
            formulation=FinalFormulation(
                product_name="Ashwagandha-Tulsi Vitality Churna (DEMO)",
                formulation_date=timezone.localdate() - dt.timedelta(days=14),
                packaging_info="DEMO: 100 g amber glass jar, tamper seal, lot printed on label.", is_demo=True),
        )

        # 3. Amla, processed and waiting for the manufacturer
        amla = self._collect(farmer, h["Amla"], 25, "60.000", "24.060500", "75.080100",
                             "Demo orchard, Mandsaur", source="CULTIVATED")
        self._test(lab, amla, 21, "96.90", "7.20", "PASS")
        self._process(proc, amla, [
            ("CLEANING", 19, "Mandsaur Processing Unit (demo)", "Washed and deseeded.", DONE),
            ("DRYING", 17, "Mandsaur Processing Unit (demo)", "Sun-dried.", DONE),
        ])

        # 4. Shatavari, lab passed but processing in progress
        shat = self._collect(farmer2, h["Shatavari"], 14, "30.000", "24.090000", "75.050000",
                             "Demo plot, Mandsaur", source="CULTIVATED", coord_source="MANUAL")
        self._test(lab, shat, 10, "95.50", "8.00", "PASS")
        self._process(proc, shat, [
            ("CLEANING", 8, "Mandsaur Processing Unit (demo)", "Washed and sliced.", DONE),
            ("DRYING", 6, "Mandsaur Processing Unit (demo)", "Drying in progress.", OPEN),
        ])

        # 5. Neem, lab passed and waiting for the processor
        neem = self._collect(farmer, h["Neem"], 9, "22.000", "11.680000", "76.120000",
                             "Demo grove, Wayanad", source="WILD", permit=True, method="TOOLS")
        self._test(lab, neem, 5, "94.00", "9.00", "PASS")

        # 6. Brahmi, awaiting the laboratory
        self._collect(farmer2, h["Brahmi"], 3, "12.500", "11.700000", "76.150000",
                      "Demo wetland edge, Wayanad", source="WILD", permit=True)

        # 7. Guduchi, FAILED laboratory test -> rejected
        gud = self._collect(farmer, h["Guduchi"], 20, "15.000", "11.688000", "76.128000",
                            "Demo hedgerow, Wayanad", source="WILD", permit=True)
        self._test(lab, gud, 16, "71.20", "14.80", "FAIL",
                   contamination="DEMO: sample showed excess moisture and foreign matter.",
                   remarks="DEMO DATA: rejected batch example.")

        # 8. Neem outside every approved region -> admin review (pending)
        self._collect(farmer, h["Neem"], 2, "10.000", "19.076000", "72.877700",
                      "Demo roadside outside any approved region", source="WILD", permit=False)

        # 9. Wild collection without permit inside a region, then admin APPROVES it
        g = self._collect(farmer2, h["Shatavari"], 7, "8.000", "24.070000", "75.070000",
                          "Demo wild patch, Mandsaur", source="WILD", permit=False)
        review_region(g, admin, True, "DEMO: permit confirmed offline by administrator.")

        # 10. No GPS at all -> admin review (pending)
        self._collect(farmer2, h["Tulsi"], 1, "5.000", None, None, "Demo backyard (GPS unavailable)")

    # ------------------------------------------------------------------
    def _print_credentials(self):
        out = self.stdout
        out.write("")
        out.write(self.style.MIGRATE_HEADING("Demo logins (local development ONLY, never use in production)"))
        out.write(f"  Password for every demo account: {DEMO_PASSWORD}")
        for username, role, _f, _l, approval in DEMO_USERS:
            note = "  (pending approval: cannot log in until the admin approves)" if approval == User.Approval.PENDING else ""
            out.write(f"  {username:<18} {role.label if hasattr(role, 'label') else role}{note}")
        formulation = FinalFormulation.objects.filter(is_demo=True).first()
        if formulation:
            out.write("")
            out.write(f"  Public demo product page: {settings.PUBLIC_BASE_URL}/verify/{formulation.public_id}/")
