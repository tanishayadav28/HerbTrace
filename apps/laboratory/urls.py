from django.urls import path

from . import views

app_name = "laboratory"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("queue/", views.queue, name="queue"),
    path("test/<str:batch_id>/", views.test_create, name="test_create"),
    path("history/", views.history, name="history"),
]
