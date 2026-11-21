from django.contrib.auth import views as auth_views
from django.urls import path, reverse_lazy

from accounts import views


app_name = "accounts"
urlpatterns = [
    path("login/", views.login, name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("signup/", views.signup, name="signup"),
    path("verify-email/", views.verify_email, name="verify_email"),
    path("profile/", views.profile, name="profile"),
    path("password/", auth_views.PasswordChangeView.as_view(
        template_name="accounts/password_change.htmx",
        success_url=reverse_lazy("accounts:password_changed"),
    ), name="password_change"),
    path("password/changed/", auth_views.PasswordChangeDoneView.as_view(
        template_name="accounts/password_changed.htmx",
    ), name="password_changed"),
]
