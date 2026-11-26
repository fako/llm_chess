from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.utils.translation import gettext, gettext_lazy

from accounts.models import User


def email_opt_out_field() -> forms.BooleanField:
    return forms.BooleanField(
        required=False,
        label=gettext_lazy("accounts.email_opt_out.label"),
        help_text=gettext_lazy("accounts.email_opt_out.help"),
    )


class SignupForm(UserCreationForm):
    email = forms.EmailField(required=True, label=gettext_lazy("accounts.signup.email"))
    email_opt_out = email_opt_out_field()

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username", "email")

    def clean_email(self) -> str:
        email = self.cleaned_data["email"]
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError(gettext("accounts.signup.email_taken"))
        return email


class EmailPreferencesForm(forms.ModelForm):
    email_opt_out = email_opt_out_field()

    class Meta:
        model = User
        fields = ("email_opt_out",)
