from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.utils.translation import gettext, gettext_lazy

from accounts.models import User


# Promotional email is opt-in. The box people see says the opposite, "don't send me promotional emails", and is
# ticked until they untick it, so nobody gets them without acting on it. Users store the choice as email_opt_in.

def no_promotions_field() -> forms.BooleanField:
    return forms.BooleanField(required=False, initial=True, label=gettext_lazy("accounts.email.no_promotions"))


class SignupForm(UserCreationForm):
    email = forms.EmailField(required=True, label=gettext_lazy("accounts.signup.email"))
    no_promotions = no_promotions_field()

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username", "email")

    def clean_email(self) -> str:
        email = self.cleaned_data["email"]
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError(gettext("accounts.signup.email_taken"))
        return email

    @property
    def email_opt_in(self) -> bool:
        return not self.cleaned_data["no_promotions"]


class EmailPreferencesForm(forms.Form):
    no_promotions = no_promotions_field()

    def __init__(self, *args, user: User, **kwargs):
        super().__init__(*args, initial={"no_promotions": not user.email_opt_in}, **kwargs)
        self.user = user

    def save(self) -> None:
        self.user.email_opt_in = not self.cleaned_data["no_promotions"]
        self.user.save(update_fields=["email_opt_in"])
