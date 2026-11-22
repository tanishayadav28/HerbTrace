"""Template context: role-aware sidebar navigation."""
from apps.accounts.models import User

NAV = {
    User.Role.ADMIN: [
        ("Dashboard", "accounts:admin_dashboard", "bi-speedometer2"),
        ("Users & roles", "accounts:user_list", "bi-people"),
        ("Herbs", "herbs:herb_list", "bi-flower1"),
        ("Approved regions", "herbs:region_list", "bi-geo-alt"),
        ("Region reviews", "traceability:region_reviews", "bi-patch-question"),
        ("All batches", "traceability:batch_list", "bi-boxes"),
        ("Ledger integrity", "traceability:ledger", "bi-link-45deg"),
        ("Reports", "traceability:reports", "bi-bar-chart-line"),
    ],
    User.Role.FARMER: [
        ("Dashboard", "traceability:farmer_dashboard", "bi-speedometer2"),
        ("New collection", "traceability:collection_create", "bi-plus-circle"),
        ("My collections", "traceability:my_collections", "bi-basket"),
    ],
    User.Role.LAB: [
        ("Dashboard", "laboratory:dashboard", "bi-speedometer2"),
        ("Test queue", "laboratory:queue", "bi-hourglass-split"),
        ("Test history", "laboratory:history", "bi-clipboard2-data"),
    ],
    User.Role.PROCESSOR: [
        ("Dashboard", "processing:dashboard", "bi-speedometer2"),
        ("Approved batches", "processing:eligible", "bi-check2-square"),
        ("Processing history", "processing:history", "bi-clock-history"),
    ],
    User.Role.MANUFACTURER: [
        ("Dashboard", "manufacturing:dashboard", "bi-speedometer2"),
        ("New formulation", "manufacturing:create", "bi-capsule"),
        ("Manufacturing history", "manufacturing:history", "bi-archive"),
    ],
}


def navigation(request):
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return {}
    items = NAV.get(user.effective_role, [])
    match = getattr(request, "resolver_match", None)
    current = f"{match.namespace}:{match.url_name}" if match and match.namespace else ""
    nav = [
        {"label": label, "url": url, "icon": icon, "active": url == current}
        for (label, url, icon) in items
    ]
    return {"nav_items": nav}
