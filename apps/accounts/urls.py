from django.contrib.auth.views import LogoutView
from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("login/", views.RoleLoginView.as_view(), name="login"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("register/", views.register, name="register"),
    path("dashboard/", views.dashboard_router, name="dashboard"),
    path("password/", views.PasswordChange.as_view(), name="password_change"),
    path("admin-dashboard/", views.admin_dashboard, name="admin_dashboard"),
    path("users/", views.user_list, name="user_list"),
    path("users/new/", views.user_create, name="user_create"),
    path("users/<int:pk>/edit/", views.user_edit, name="user_edit"),
    path("users/<int:pk>/<str:decision>/", views.user_approval, name="user_approval"),
]
