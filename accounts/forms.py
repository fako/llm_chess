from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.utils.translation import gettext, gettext_lazy

from accounts.models import User


class SignupForm(UserCreationForm):
    email = forms.EmailField(required=True, label=gettext_lazy("accounts.signup.email"))

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username", "email")

    def clean_email(self) -> str:
        email = self.cleaned_data["email"]
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError(gettext("accounts.signup.email_taken"))
        return email
