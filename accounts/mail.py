from django.core.mail import send_mail
from django.urls import reverse
from django.utils.http import urlencode
from django.utils.translation import gettext


def send_validation(strategy, backend, code, partial_token):
    """
    Sends the link that resumes a signup once the email address is verified. Configured as the EMAIL_VALIDATION_FUNCTION.
    """
    query = urlencode({"verification_code": code.code, "partial_token": partial_token})
    url = strategy.build_absolute_uri(reverse("social:complete", args=(backend.name,)) + "?" + query)
    send_mail(
        subject=gettext("accounts.mail.validation.subject"),
        message=gettext("accounts.mail.validation.body") % {"url": url} + "\n",
        from_email=None,
        recipient_list=[code.email],
    )
