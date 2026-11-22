from django.http import HttpRequest, HttpResponse
from django.utils import translation
from django.views.i18n import set_language


def switch_language(request: HttpRequest) -> HttpResponse:
    """
    Django's set_language, run in the language of the page the visitor switches from.
    Django can only translate the "next" URL while the language of its prefix is active. Without this, a visitor
    whose cookie says English but who opened a /nl/ link would be sent back to the same /nl/ page.
    """
    language = translation.get_language_from_path(request.POST.get("next", ""))
    if language:
        translation.activate(language)
    return set_language(request)
