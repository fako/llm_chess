import re
from email.utils import parseaddr

from django.conf import settings
from django.core import mail
from django.test import TestCase, override_settings
from django.utils import timezone
from social_django.models import Partial, UserSocialAuth

from accounts.models import User
from puzzles.models import ChessPuzzle, ChessPuzzleCategory, UserChessPuzzle


SIGNUP = {
    "username": "newcomer", "email": "newcomer@example.com",
    "password1": "a-long-passphrase-42", "password2": "a-long-passphrase-42",
}
SIGNUP_WITH_PROMOTIONS = {**SIGNUP, "email_opt_in": "on"}


class TestLogin(TestCase):

    def setUp(self):
        self.user = User.objects.create_user("solver", password="secret-password")

    def test_login_through_social_auth(self):
        response = self.client.get("/en/accounts/login/?next=/en/accounts/profile/")
        self.assertContains(response, 'value="/en/accounts/profile/"')
        response = self.client.post("/en/accounts/login/", {
            "username": "solver", "password": "secret-password", "next": "/en/accounts/profile/",
        })
        self.assertRedirects(response, "/en/accounts/profile/")
        self.assertEqual(self.client.session["_auth_user_id"], str(self.user.pk))
        social = UserSocialAuth.objects.get(provider="username", uid="solver")
        self.assertEqual(social.user, self.user, "existing users get associated on their first login")
        self.client.logout()
        response = self.client.post("/en/accounts/login/", {"username": "solver", "password": "secret-password"})
        self.assertRedirects(response, "/en/")
        self.assertEqual(UserSocialAuth.objects.count(), 1)

    def test_wrong_password(self):
        response = self.client.post("/en/accounts/login/", {"username": "solver", "password": "wrong"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "correct username and password")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_complete_without_password_is_forbidden(self):
        UserSocialAuth.objects.create(user=self.user, provider="username", uid="solver")
        response = self.client.post("/auth/complete/username/", {"username": "solver"})
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertRedirects(response, "/en/accounts/login/", fetch_redirect_response=False)

    def test_logout(self):
        self.client.force_login(self.user)
        response = self.client.get("/en/")
        self.assertContains(response, "My results")
        self.assertContains(response, "More puzzles")
        self.assertContains(response, "Sign out")
        response = self.client.post("/en/accounts/logout/")
        self.assertRedirects(response, "/en/accounts/login/")
        self.assertNotIn("_auth_user_id", self.client.session)


class TestSignup(TestCase):

    def test_email_verification_is_on_by_default(self):
        self.assertTrue(settings.ACCOUNTS_EMAIL_VERIFICATION)
        self.assertTrue(settings.SOCIAL_AUTH_USERNAME_FORCE_EMAIL_VALIDATION)

    @override_settings(SOCIAL_AUTH_USERNAME_FORCE_EMAIL_VALIDATION=False)
    def test_signup_without_email_verification(self):
        response = self.client.post("/en/accounts/signup/", SIGNUP)
        self.assertRedirects(response, "/en/")
        user = User.objects.get(username="newcomer")
        self.assertEqual(user.email, "newcomer@example.com")
        self.assertTrue(user.check_password("a-long-passphrase-42"))
        self.assertTrue(UserSocialAuth.objects.filter(user=user, provider="username", uid="newcomer").exists())
        self.assertEqual(len(mail.outbox), 0)

    @override_settings(SOCIAL_AUTH_USERNAME_FORCE_EMAIL_VALIDATION=False)
    def test_signup_with_email_opt_in_and_next(self):
        response = self.client.get("/en/accounts/signup/?next=/en/puzzles/1/")
        self.assertContains(response, "Send me promotional emails from Chess puzzles")
        self.assertContains(response, 'name="email_opt_in" class="mt-0.5 h-5 w-5 shrink-0 accent-walnut" '
                                      'id="id_email_opt_in">', msg_prefix="email is opt-in, so the box is unticked")
        self.assertContains(response, 'href="/en/accounts/login/?next=%2Fen%2Fpuzzles%2F1%2F"')
        response = self.client.post("/en/accounts/signup/", {**SIGNUP_WITH_PROMOTIONS, "next": "/en/puzzles/1/"})
        self.assertRedirects(response, "/en/puzzles/1/", fetch_redirect_response=False)
        self.assertTrue(User.objects.get(username="newcomer").email_opt_in)

    @override_settings(SOCIAL_AUTH_USERNAME_FORCE_EMAIL_VALIDATION=False)
    def test_signup_gets_no_emails_unless_asked(self):
        self.client.post("/en/accounts/signup/", SIGNUP)
        self.assertFalse(User.objects.get(username="newcomer").email_opt_in)

    def test_next_does_not_leave_the_site(self):
        User.objects.create_user("solver", password="secret-password")
        response = self.client.post("/en/accounts/login/", {
            "username": "solver", "password": "secret-password", "next": "https://evil.example.com/",
        })
        self.assertRedirects(response, "/en/", fetch_redirect_response=False)

    def test_invalid_signup(self):
        User.objects.create_user("taken", email="taken@example.com", password="secret-password")
        response = self.client.post("/en/accounts/signup/", {**SIGNUP, "username": "taken"})
        self.assertContains(response, "already exists")
        response = self.client.post("/en/accounts/signup/", {**SIGNUP, "email": "TAKEN@example.com"})
        self.assertContains(response, "email address already exists")
        response = self.client.post("/en/accounts/signup/", {**SIGNUP, "password2": "something else"})
        self.assertContains(response, "didn’t match")
        self.assertEqual(User.objects.count(), 1)

    @override_settings(PUBLIC_URL="https://chess.example.com/")
    def test_signup_with_email_verification(self):
        response = self.client.post("/en/accounts/signup/", SIGNUP)
        self.assertRedirects(response, "/en/accounts/verify-email/", fetch_redirect_response=False)
        self.assertFalse(User.objects.filter(username="newcomer").exists())
        self.assertContains(self.client.get("/en/accounts/verify-email/"), "newcomer@example.com")

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["newcomer@example.com"])
        self.assertTrue(mail.outbox[0].body.endswith("Kind regards,\n\nChess puzzles\n"))
        link = re.search(r"https://chess\.example\.com(/\S+)", mail.outbox[0].body).group(1)
        self.assertNotIn("a-long-passphrase-42", str(Partial.objects.get().data), "no plain passwords are stored")

        response = self.client.get(link)  # PSA asks to confirm a resume that comes from outside
        self.assertContains(response, "Confirm and continue")
        content = response.content.decode()
        form = re.search(r'<form method="post" action="(/auth/[^"]+)"(.*?)</form>', content, re.DOTALL)
        action = form.group(1)
        fields = dict(re.findall(r'<input type="hidden" name="([^"]+)" value="([^"]*)"', form.group(2)))
        response = self.client.post(action, fields)
        self.assertRedirects(response, "/en/", fetch_redirect_response=False)
        user = User.objects.get(username="newcomer")
        self.assertTrue(user.check_password("a-long-passphrase-42"))
        self.assertEqual(self.client.session["_auth_user_id"], str(user.pk))
        self.assertFalse(user.email_opt_in)

    def test_email_opt_in_and_next_survive_email_verification(self):
        self.client.post("/en/accounts/signup/", {**SIGNUP_WITH_PROMOTIONS, "next": "/en/puzzles/1/"})
        link = re.search(r"https?://[^/\s]+(/\S+)", mail.outbox[0].body).group(1)
        content = self.client.get(link).content.decode()
        form = re.search(r'<form method="post" action="(/auth/[^"]+)"(.*?)</form>', content, re.DOTALL)
        fields = dict(re.findall(r'<input type="hidden" name="([^"]+)" value="([^"]*)"', form.group(2)))
        response = self.client.post(form.group(1), fields)
        self.assertRedirects(response, "/en/puzzles/1/", fetch_redirect_response=False)
        self.assertTrue(User.objects.get(username="newcomer").email_opt_in)

        self.client.logout()
        response = self.client.post("/en/accounts/login/", {"username": "newcomer", "password": SIGNUP["password1"]})
        self.assertRedirects(response, "/en/", fetch_redirect_response=False, msg_prefix="next is used only once")


class TestPasswordReset(TestCase):

    def setUp(self):
        self.user = User.objects.create_user("solver", email="solver@example.com", password="secret-password")

    def request_link(self, language="en", **headers) -> tuple[str, str]:
        response = self.client.post(f"/{language}/accounts/password/reset/", {"email": "SOLVER@example.com"},
                                    headers=headers)
        self.assertRedirects(response, f"/{language}/accounts/password/reset/sent/")
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["solver@example.com"])
        return re.search(r"(https?://[^/\s]+)(/\S+)", mail.outbox[0].body).groups()

    def test_login_links_to_reset(self):
        self.assertContains(self.client.get("/en/accounts/login/"), 'href="/en/accounts/password/reset/"')
        self.assertContains(self.client.get("/en/accounts/password/reset/"), "Send link")

    @override_settings(PUBLIC_URL="https://chess.example.com/")
    def test_reset_password(self):
        base, link = self.request_link(host="internal.localhost")
        self.assertEqual(base, "https://chess.example.com", "links point at PUBLIC_URL, not the host of the request")
        message = mail.outbox[0]
        self.assertEqual(message.subject, "Reset your password for Chess puzzles")
        self.assertIn("Hi solver,", message.body)
        self.assertTrue(message.body.endswith("Kind regards,\n\nChess puzzles\n"))
        self.assertEqual(parseaddr(message.from_email), ("Fako Berkers", "noreply@mail.fakoberkers.nl"))
        self.assertNotIn("&#", message.body, "the plain text mail is not HTML escaped")

        response = self.client.get(link)  # Django moves the token out of the URL into the session
        response = self.client.get(response.url)
        self.assertContains(response, "Choose a new password")
        response = self.client.post(response.request["PATH_INFO"], {
            "new_password1": "another-passphrase-7", "new_password2": "another-passphrase-7",
        })
        self.assertRedirects(response, "/en/accounts/password/reset/done/")
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("another-passphrase-7"))
        self.assertContains(self.client.get("/en/accounts/password/reset/done/"), "Password changed")

        response = self.client.get(link, follow=True)
        self.assertContains(response, "doesn't work anymore", msg_prefix="links work only once")

    @override_settings(PUBLIC_URL="")
    def test_reset_link_without_public_url(self):
        base, link = self.request_link("nl", host="testserver", x_forwarded_proto="https")
        self.assertEqual(base, "https://testserver", "links follow the host and the scheme the edge reports")
        self.assertTrue(link.startswith("/nl/accounts/password/reset/"))
        self.assertEqual(mail.outbox[0].subject, "Herstel je wachtwoord voor Schaakpuzzeltjes")
        self.assertTrue(mail.outbox[0].body.endswith("Met vriendelijke groet,\n\nSchaakpuzzeltjes\n"))

    def test_unknown_email_sends_nothing(self):
        response = self.client.post("/en/accounts/password/reset/", {"email": "nobody@example.com"})
        self.assertRedirects(response, "/en/accounts/password/reset/sent/", msg_prefix="no hint whether it exists")
        self.assertEqual(len(mail.outbox), 0)

    def test_invalid_link(self):
        response = self.client.get("/en/accounts/password/reset/MQ/wrong-token/")
        self.assertContains(response, "Request a new link")


class TestProfile(TestCase):

    def setUp(self):
        self.user = User.objects.create_user("solver", password="secret-password")
        self.client.force_login(self.user)

    def test_results(self):
        category = ChessPuzzleCategory.objects.get(slug="mate-in-1")
        puzzle = ChessPuzzle.objects.create(category=category, fen="6k1/5ppp/8/8/8/8/5PPP/3R2K1 w - - 0 1",
                                            position="x", perspective="white", solution={"moves": {}},
                                            title_en="Back rank")
        UserChessPuzzle.objects.create(user=self.user, puzzle=puzzle, solved_at=timezone.now(), wrong_moves=2)
        response = self.client.get("/en/accounts/profile/")
        self.assertContains(response, "Results for Solver")
        self.assertContains(response, "Back rank")
        self.assertContains(response, "1 / 1")
        self.assertContains(response, "Change password")

    def test_email_opt_in(self):
        response = self.client.get("/en/accounts/profile/")
        self.assertContains(response, 'hx-post="/en/accounts/profile/email/"')
        self.assertContains(response, "Send me promotional emails from Chess puzzles")
        self.assertNotContains(response, " checked", msg_prefix="email is opt-in")
        response = self.client.post("/en/accounts/profile/email/", {"email_opt_in": "on"},
                                    headers={"HX-Request": "true"})
        self.assertContains(response, "Saved")
        self.assertContains(response, " checked")
        self.assertNotContains(response, "<html")
        self.user.refresh_from_db()
        self.assertTrue(self.user.email_opt_in)
        response = self.client.post("/en/accounts/profile/email/", {})  # unticked
        self.assertRedirects(response, "/en/accounts/profile/")
        self.user.refresh_from_db()
        self.assertFalse(self.user.email_opt_in)

    def test_change_password(self):
        response = self.client.post("/en/accounts/password/", {
            "old_password": "secret-password",
            "new_password1": "another-passphrase-7", "new_password2": "another-passphrase-7",
        })
        self.assertRedirects(response, "/en/accounts/password/changed/")
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("another-passphrase-7"))
