"""QR-code generation for final formulations."""
from io import BytesIO

import qrcode
from django.conf import settings
from django.core.files.base import ContentFile
from django.urls import reverse
from qrcode.constants import ERROR_CORRECT_M

from .models import FinalFormulation, QRCode


def public_url(formulation: FinalFormulation) -> str:
    """Absolute public URL encoded in the QR (base URL comes from PUBLIC_BASE_URL)."""
    path = reverse("verification:public", args=[formulation.public_id])
    return f"{settings.PUBLIC_BASE_URL}{path}"


def build_qr_png(url: str) -> bytes:
    qr = qrcode.QRCode(version=None, error_correction=ERROR_CORRECT_M, box_size=10, border=3)
    qr.add_data(url)
    qr.make(fit=True)
    image = qr.make_image(fill_color="#14452f", back_color="white")
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def generate_qr(formulation: FinalFormulation) -> QRCode:
    url = public_url(formulation)
    png = build_qr_png(url)
    qr_obj, _ = QRCode.objects.get_or_create(formulation=formulation, defaults={"url": url})
    qr_obj.url = url
    qr_obj.image.save(f"{formulation.formulation_code}.png", ContentFile(png), save=False)
    qr_obj.save()
    return qr_obj
