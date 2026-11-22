from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path, re_path
from django.views.static import serve as media_serve

from apps.accounts import views as account_views

urlpatterns = [
    path("", account_views.home, name="home"),
    path("django-admin/", admin.site.urls),
    path("accounts/", include("apps.accounts.urls")),
    path("manage/", include("apps.herbs.urls")),
    path("trace/", include("apps.traceability.urls")),
    path("lab/", include("apps.laboratory.urls")),
    path("processing/", include("apps.processing.urls")),
    path("manufacturing/", include("apps.manufacturing.urls")),
    path("verify/", include("apps.verification.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
else:
    # Demo hosting: serve the small generated QR images straight from Django.
    urlpatterns += [re_path(r"^media/(?P<path>.*)$", media_serve, {"document_root": settings.MEDIA_ROOT})]

handler403 = "apps.core.views.permission_denied"