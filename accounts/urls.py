from django.contrib.auth import views as auth_views
from django.urls import path

from accounts import views


app_name = "accounts"
urlpatterns = [
    path("login/", auth_views.LoginView.as_view(template_name="accounts/login.htmx", redirect_authenticated_user=True),
         name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("signup/", views.signup, name="signup"),
]
