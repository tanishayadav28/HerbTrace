from django.urls import path

from . import views

app_name = "processing"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("batches/", views.eligible, name="eligible"),
    path("batches/<str:batch_id>/add/", views.add, name="add"),
    path("history/", views.history, name="history"),
    path("records/<int:pk>/status/", views.set_status, name="set_status"),
]
