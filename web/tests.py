import ast
import gettext
from pathlib import Path

from django.conf import settings
from django.template import engines
from django.test import TestCase

from accounts.models import User


APPS = ["web", "accounts", "puzzles"]
GETTEXT_FUNCTIONS = {"gettext", "gettext_lazy", "_", "ngettext", "ngettext_lazy", "pgettext", "npgettext"}


def used_messages() -> set[tuple[str, ...]]:
    """
    Every message id our templates and Python code ask for. Plurals are a tuple of the singular and plural id.
    """
    messages = set()
    environment = engines["jinja2"].env
    for app in APPS:
        for path in (Path(settings.BASE_DIR) / app / "htmx").rglob("*.htm*"):
            for _, function, message in environment.extract_translations(path.read_text()):
                # Keyword arguments show up as None
                message = message if isinstance(message, tuple) else (message,)
                messages.add(tuple(part for part in message if isinstance(part, str)))
        for path in (Path(settings.BASE_DIR) / app).rglob("*.py"):
            for node in ast.walk(ast.parse(path.read_text())):
                if isinstance(node, ast.Call) and getattr(node.func, "id", None) in GETTEXT_FUNCTIONS:
                    ids = tuple(arg.value for arg in node.args if isinstance(arg, ast.Constant))
                    if ids:
                        messages.add(ids[:2] if node.func.id.startswith("n") else ids[:1])
    return messages


class TestTranslations(TestCase):

    def test_every_message_is_translated(self):
        messages = used_messages()
        self.assertGreater(len(messages), 50)
        for code, _ in settings.LANGUAGES:
            catalog = gettext.translation("django", localedir=settings.LOCALE_PATHS[0], languages=[code])
            for message in messages:
                if len(message) == 2:
                    missing = catalog.ngettext(*message, 2) == message[1]
                else:
                    missing = catalog.gettext(message[0]) == message[0]
                self.assertFalse(missing, f"{message[0]} has no translation for {code} in locale/{code}")

    def test_language_from_browser(self):
        response = self.client.get("/", headers={"Accept-Language": "nl-NL,nl;q=0.9,en;q=0.8"})
        self.assertRedirects(response, "/nl/", fetch_redirect_response=False)
        response = self.client.get("/", headers={"Accept-Language": "de-DE,de;q=0.9"})
        self.assertRedirects(response, "/en/", fetch_redirect_response=False)

    def test_dutch_pages(self):
        response = self.client.get("/nl/accounts/login/")
        self.assertContains(response, '<html lang="nl">')
        self.assertContains(response, "Welkom terug")
        self.assertContains(response, 'href="/nl/accounts/signup/"')
        self.assertContains(response, "Gebruikersnaam", msg_prefix="Django translates its own forms")
        self.assertContains(response, "img/flags/gb.svg")
        self.assertContains(self.client.get("/en/accounts/login/"), "img/flags/nl.svg")

    def test_switch_language(self):
        user = User.objects.create_user("solver", password="secret-password")
        self.client.force_login(user)
        response = self.client.post("/language/", {"language": "nl", "next": "/en/accounts/profile/"})
        self.assertRedirects(response, "/nl/accounts/profile/")
        self.assertEqual(response.cookies[settings.LANGUAGE_COOKIE_NAME].value, "nl")
        response = self.client.get("/nl/accounts/profile/")
        self.assertContains(response, "Resultaten van Solver")
        self.assertContains(response, "Uitloggen")
        response = self.client.get("/", headers={"Accept-Language": "en"})
        self.assertRedirects(response, "/nl/", fetch_redirect_response=False, msg_prefix="the cookie wins")
