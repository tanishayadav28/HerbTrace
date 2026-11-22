from django.urls import path

from . import views

app_name = "manufacturing"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("new/", views.create, name="create"),
    path("history/", views.history, name="history"),
    path("formulation/<int:pk>/", views.detail, name="detail"),
]
