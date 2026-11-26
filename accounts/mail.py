from django.conf import settings
from django.core.mail import send_mail
from django.urls import reverse
from django.utils.http import urlencode
from django.utils.translation import gettext


def public_url(path: str, fallback: str) -> str:
    """
    The full URL of a path, for links in emails. Links point at PUBLIC_URL whatever host the request came in on.
    The fallback is the scheme and host of the request, for installations without a PUBLIC_URL.
    """
    return (settings.PUBLIC_URL or fallback).rstrip("/") + path


def send_validation(strategy, backend, code, partial_token):
    """
    Sends the link that resumes a signup once the email address is verified. Configured as the EMAIL_VALIDATION_FUNCTION.
    """
    query = urlencode({"verification_code": code.code, "partial_token": partial_token})
    path = reverse("social:complete", args=(backend.name,)) + "?" + query
    url = public_url(path, strategy.build_absolute_uri("/"))
    send_mail(
        subject=gettext("accounts.mail.validation.subject"),
        message=gettext("accounts.mail.validation.body") % {"url": url} + "\n\n" + gettext("accounts.mail.closing") + "\n",
        from_email=None,
        recipient_list=[code.email],
    )
