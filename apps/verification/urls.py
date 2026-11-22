from django.urls import path

from . import views

app_name = "verification"

urlpatterns = [
    path("", views.lookup, name="lookup"),
    path("<uuid:public_id>/", views.public_verification, name="public"),
]
