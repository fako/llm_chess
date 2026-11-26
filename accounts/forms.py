from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.utils.translation import gettext, gettext_lazy

from accounts.models import User


def email_opt_in_field(initial: bool = False) -> forms.BooleanField:
    return forms.BooleanField(required=False, initial=initial, label=gettext_lazy("accounts.email.promotions"))


class SignupForm(UserCreationForm):
    email = forms.EmailField(required=True, label=gettext_lazy("accounts.signup.email"))
    email_opt_in = email_opt_in_field(initial=True)  # ticked when signing up, people untick it to opt out

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username", "email")

    def clean_email(self) -> str:
        email = self.cleaned_data["email"]
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError(gettext("accounts.signup.email_taken"))
        return email


class EmailPreferencesForm(forms.ModelForm):
    email_opt_in = email_opt_in_field()  # shows what the user chose

    class Meta:
        model = User
        fields = ("email_opt_in",)
