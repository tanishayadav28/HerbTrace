from django.urls import path

from . import views

app_name = "herbs"

urlpatterns = [
    path("herbs/", views.herb_list, name="herb_list"),
    path("herbs/new/", views.herb_create, name="herb_create"),
    path("herbs/<int:pk>/edit/", views.herb_edit, name="herb_edit"),
    path("herbs/<int:pk>/delete/", views.herb_delete, name="herb_delete"),
    path("regions/", views.region_list, name="region_list"),
    path("regions/new/", views.region_create, name="region_create"),
    path("regions/<int:pk>/edit/", views.region_edit, name="region_edit"),
    path("regions/<int:pk>/delete/", views.region_delete, name="region_delete"),
]
