import re

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


class TestLogin(TestCase):

    def setUp(self):
        self.user = User.objects.create_user("solver", password="secret-password")

    def test_login_through_social_auth(self):
        response = self.client.get("/accounts/login/?next=/accounts/profile/")
        self.assertContains(response, 'value="/accounts/profile/"')
        response = self.client.post("/accounts/login/", {
            "username": "solver", "password": "secret-password", "next": "/accounts/profile/",
        })
        self.assertRedirects(response, "/accounts/profile/")
        self.assertEqual(self.client.session["_auth_user_id"], str(self.user.pk))
        social = UserSocialAuth.objects.get(provider="username", uid="solver")
        self.assertEqual(social.user, self.user, "existing users get associated on their first login")
        self.client.logout()
        response = self.client.post("/accounts/login/", {"username": "solver", "password": "secret-password"})
        self.assertRedirects(response, "/")
        self.assertEqual(UserSocialAuth.objects.count(), 1)

    def test_wrong_password(self):
        response = self.client.post("/accounts/login/", {"username": "solver", "password": "wrong"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "correct username and password")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_complete_without_password_is_forbidden(self):
        UserSocialAuth.objects.create(user=self.user, provider="username", uid="solver")
        response = self.client.post("/auth/complete/username/", {"username": "solver"})
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertRedirects(response, "/accounts/login/", fetch_redirect_response=False)

    def test_logout(self):
        self.client.force_login(self.user)
        response = self.client.get("/")
        self.assertContains(response, "My results")
        self.assertContains(response, "More puzzles")
        self.assertContains(response, "Sign out")
        response = self.client.post("/accounts/logout/")
        self.assertRedirects(response, "/accounts/login/")
        self.assertNotIn("_auth_user_id", self.client.session)


class TestSignup(TestCase):

    def test_signup(self):
        response = self.client.post("/accounts/signup/", SIGNUP)
        self.assertRedirects(response, "/")
        user = User.objects.get(username="newcomer")
        self.assertEqual(user.email, "newcomer@example.com")
        self.assertTrue(user.check_password("a-long-passphrase-42"))
        self.assertTrue(UserSocialAuth.objects.filter(user=user, provider="username", uid="newcomer").exists())
        self.assertEqual(len(mail.outbox), 0, "email verification is off by default")

    def test_invalid_signup(self):
        User.objects.create_user("taken", email="taken@example.com", password="secret-password")
        response = self.client.post("/accounts/signup/", {**SIGNUP, "username": "taken"})
        self.assertContains(response, "already exists")
        response = self.client.post("/accounts/signup/", {**SIGNUP, "email": "TAKEN@example.com"})
        self.assertContains(response, "email address already exists")
        response = self.client.post("/accounts/signup/", {**SIGNUP, "password2": "something else"})
        self.assertContains(response, "didn’t match")
        self.assertEqual(User.objects.count(), 1)

    @override_settings(SOCIAL_AUTH_USERNAME_FORCE_EMAIL_VALIDATION=True)
    def test_signup_with_email_verification(self):
        response = self.client.post("/accounts/signup/", SIGNUP)
        self.assertRedirects(response, "/accounts/verify-email/", fetch_redirect_response=False)
        self.assertFalse(User.objects.filter(username="newcomer").exists())
        self.assertContains(self.client.get("/accounts/verify-email/"), "newcomer@example.com")

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["newcomer@example.com"])
        link = re.search(r"http://testserver(\S+)", mail.outbox[0].body).group(1)
        self.assertNotIn("a-long-passphrase-42", str(Partial.objects.get().data), "no plain passwords are stored")

        response = self.client.get(link)  # PSA asks to confirm a resume that comes from outside
        self.assertContains(response, "Confirm and continue")
        content = response.content.decode()
        action = re.search(r'<form method="post" action="([^"]+)"', content).group(1)
        fields = dict(re.findall(r'<input type="hidden" name="([^"]+)" value="([^"]*)"', content))
        response = self.client.post(action, fields)
        self.assertRedirects(response, "/", fetch_redirect_response=False)
        user = User.objects.get(username="newcomer")
        self.assertTrue(user.check_password("a-long-passphrase-42"))
        self.assertEqual(self.client.session["_auth_user_id"], str(user.pk))


class TestProfile(TestCase):

    def setUp(self):
        self.user = User.objects.create_user("solver", password="secret-password")
        self.client.force_login(self.user)

    def test_results(self):
        category = ChessPuzzleCategory.objects.get(slug="mate-in-1")
        puzzle = ChessPuzzle.objects.create(category=category, fen="6k1/5ppp/8/8/8/8/5PPP/3R2K1 w - - 0 1",
                                            position="x", perspective="white", solution={"moves": {}},
                                            title="Back rank")
        UserChessPuzzle.objects.create(user=self.user, puzzle=puzzle, solved_at=timezone.now(), wrong_moves=2)
        response = self.client.get("/accounts/profile/")
        self.assertContains(response, "Results for Solver")
        self.assertContains(response, "Back rank")
        self.assertContains(response, "1 / 1")
        self.assertContains(response, "Change password")

    def test_change_password(self):
        response = self.client.post("/accounts/password/", {
            "old_password": "secret-password",
            "new_password1": "another-passphrase-7", "new_password2": "another-passphrase-7",
        })
        self.assertRedirects(response, "/accounts/password/changed/")
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("another-passphrase-7"))
