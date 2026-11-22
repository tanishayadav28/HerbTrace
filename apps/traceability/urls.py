from django.urls import path

from . import views

app_name = "traceability"

urlpatterns = [
    # farmer
    path("farmer/", views.farmer_dashboard, name="farmer_dashboard"),
    path("collections/new/", views.collection_create, name="collection_create"),
    path("collections/mine/", views.my_collections, name="my_collections"),
    # shared
    path("batch/<str:batch_id>/", views.batch_detail, name="batch_detail"),
    # admin
    path("batches/", views.batch_list, name="batch_list"),
    path("region-reviews/", views.region_reviews, name="region_reviews"),
    path("region-reviews/<str:batch_id>/<str:decision>/", views.region_review_decide, name="region_review_decide"),
    path("ledger/", views.ledger_view, name="ledger"),
    path("ledger/verify/", views.ledger_verify, name="ledger_verify"),
    path("reports/", views.reports, name="reports"),
    path("reports/export.csv", views.reports_export, name="reports_export"),
]
