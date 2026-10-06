from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
urlpatterns=[path("django-admin/",admin.site.urls),path("",include("core.urls"))]
# Uploaded documents are served only by the authenticated document endpoint.
