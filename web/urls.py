from django.conf.urls.i18n import i18n_patterns
from django.contrib import admin
from django.urls import include, path

from web.views import switch_language

# The admin and the social auth endpoints stay without a language prefix, so links in verification emails keep
# working whatever language they were sent in. Their language comes from the cookie or the browser.
urlpatterns = [
    path("admin/", admin.site.urls),
    path("auth/", include("social_django.urls", namespace="social")),
    path("language/", switch_language, name="set_language"),
]

urlpatterns += i18n_patterns(
    path("accounts/", include("accounts.urls")),
    path("", include("puzzles.urls")),
)
