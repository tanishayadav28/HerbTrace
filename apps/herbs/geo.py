"""Small geographic helpers (no external GIS dependency)."""
from decimal import Decimal
from math import asin, cos, radians, sin, sqrt

EARTH_RADIUS_KM = 6371.0088


def haversine_km(lat1, lng1, lat2, lng2) -> float:
    """Great-circle distance between two WGS84 points in kilometres."""
    lat1, lng1, lat2, lng2 = (radians(float(v)) for v in (lat1, lng1, lat2, lng2))
    dlat, dlng = lat2 - lat1, lng2 - lng1
    a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlng / 2) ** 2
    return 2 * EARTH_RADIUS_KM * asin(sqrt(a))


def valid_coordinates(lat, lng) -> bool:
    try:
        lat, lng = Decimal(str(lat)), Decimal(str(lng))
    except Exception:
        return False
    return Decimal("-90") <= lat <= Decimal("90") and Decimal("-180") <= lng <= Decimal("180")
