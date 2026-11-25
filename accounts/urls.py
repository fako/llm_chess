from django.contrib.auth import views as auth_views
from django.urls import path, reverse_lazy

from accounts import views
from accounts.mail import public_url


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
    # Forgotten passwords: an email with a link to choose a new one, which proves the account is yours
    path("password/reset/", auth_views.PasswordResetView.as_view(
        template_name="accounts/password_reset.htmx",
        subject_template_name="accounts/password_reset_subject.txt",
        email_template_name="accounts/password_reset_email.txt",
        extra_email_context={"public_url": public_url},
        success_url=reverse_lazy("accounts:password_reset_sent"),
    ), name="password_reset"),
    path("password/reset/sent/", auth_views.PasswordResetDoneView.as_view(
        template_name="accounts/password_reset_sent.htmx",
    ), name="password_reset_sent"),
    path("password/reset/<uidb64>/<token>/", auth_views.PasswordResetConfirmView.as_view(
        template_name="accounts/password_reset_confirm.htmx",
        success_url=reverse_lazy("accounts:password_reset_done"),
    ), name="password_reset_confirm"),
    path("password/reset/done/", auth_views.PasswordResetCompleteView.as_view(
        template_name="accounts/password_reset_done.htmx",
    ), name="password_reset_done"),
]
