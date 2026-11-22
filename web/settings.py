import os
from pathlib import Path
from django.urls import reverse_lazy
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(Path("/workspaces/secrets/llm_chess/.env"))
load_dotenv(BASE_DIR / ".env")

SECRET_KEY = os.environ["DJANGO_SECRET_KEY"]
DEBUG = os.environ.get("DJANGO_DEBUG", "false").strip().lower() in ("1", "true", "yes", "on")
ALLOWED_HOSTS = [
    "127.0.0.1",
    # The leading dot matches the domain and every subdomain, which covers both names this runtime
    # answers to: "llm-chess.localhost" from a browser on the host, and
    # "llm-chess.<runtime>.localhost" from another container through the /r/ router.
    # Real domains are added to the runtime's `domains` through management, and belong here too.
    ".localhost",
    "llm-chess.moko.local",
    "chess.fakoberkers.nl",
    "chess.leo65.fakoberkers.nl",
]
CSRF_TRUSTED_ORIGINS = [
    "http://llm-chess.localhost:7000",
    "http://llm-chess.moko.local",
    "http://llm-chess.moko.local:7000",
    "https://chess.fakoberkers.nl",
    "http://chess.leo65.fakoberkers.nl",
]
USE_X_FORWARDED_HOST = True
USE_X_FORWARDED_PORT = True

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django_htmx",
    "social_django",
    "web",
    "accounts",
    "puzzles",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "django_htmx.middleware.HtmxMiddleware",
    "social_django.middleware.SocialAuthExceptionMiddleware",
]

ROOT_URLCONF = "web.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.jinja2.Jinja2",
        "DIRS": [],
        "APP_DIRS": False,
        "OPTIONS": {
            "environment": "web.jinja2.environment",
            "context_processors": [
                "django.template.context_processors.request",
                "django.template.context_processors.i18n",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "django.template.context_processors.csrf",
            ],
        },
    },
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "web.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("POSTGRES_DB", "llm_chess"),
        "USER": os.environ.get("POSTGRES_USER", "llm_chess"),
        "PASSWORD": os.environ.get("POSTGRES_PASSWORD", ""),
        "HOST": os.environ.get("POSTGRES_HOST", "127.0.0.1"),
        "PORT": os.environ.get("POSTGRES_PORT", "5432"),
        "CONN_MAX_AGE": 60,
    }
}

AUTH_USER_MODEL = "accounts.User"
LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "puzzles:home"
LOGOUT_REDIRECT_URL = "accounts:login"

AUTHENTICATION_BACKENDS = [
    "social_core.backends.username.UsernameAuth",
    "django.contrib.auth.backends.ModelBackend",  # checks passwords for the login form and the admin
]

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]


# Translations
# Pages live under /en/ and /nl/. Without a prefix the language comes from the language cookie (set by the language
# switch) and otherwise the Accept-Language header of the browser, falling back to English.
# Our own messages use keys like "puzzles.home.title" instead of English text, so that changing English text doesn't
# invalidate the Dutch translations. That's why English has a catalog too: it maps the keys to English text, and
# languages that miss a key fall back to it. Edit locale/*/LC_MESSAGES/django.po and run "invoke web.compile-messages".

LANGUAGE_CODE = "en"
LANGUAGES = [
    ("en", "English"),
    ("nl", "Nederlands"),
]
LOCALE_PATHS = [BASE_DIR / "locale"]

TIME_ZONE = "UTC"

USE_I18N = True

USE_TZ = True


# Python social auth
# Users log in and sign up with a username and password through the "username" backend (see accounts/pipeline.py).

ACCOUNTS_EMAIL_VERIFICATION = os.environ.get("ACCOUNTS_EMAIL_VERIFICATION", "false").strip().lower() in \
    ("1", "true", "yes", "on")

SOCIAL_AUTH_USER_MODEL = AUTH_USER_MODEL
SOCIAL_AUTH_URL_NAMESPACE = "social"
SOCIAL_AUTH_STRATEGY = "accounts.strategy.AccountsStrategy"
SOCIAL_AUTH_USER_FIELDS = ["username", "email"]
# Lazy URLs resolve to the language of the current request
SOCIAL_AUTH_LOGIN_REDIRECT_URL = reverse_lazy("puzzles:home")
SOCIAL_AUTH_LOGIN_ERROR_URL = reverse_lazy("accounts:login")
SOCIAL_AUTH_USERNAME_FORM_URL = reverse_lazy("accounts:login")
SOCIAL_AUTH_USERNAME_FORCE_EMAIL_VALIDATION = ACCOUNTS_EMAIL_VERIFICATION
SOCIAL_AUTH_EMAIL_VALIDATION_FUNCTION = "accounts.mail.send_validation"
SOCIAL_AUTH_EMAIL_VALIDATION_URL = reverse_lazy("accounts:verify_email")
SOCIAL_AUTH_PIPELINE = (
    "social_core.pipeline.social_auth.social_details",
    "social_core.pipeline.social_auth.social_uid",
    "social_core.pipeline.social_auth.auth_allowed",
    "accounts.pipeline.require_password",
    "social_core.pipeline.social_auth.social_user",
    "social_core.pipeline.user.get_username",
    "social_core.pipeline.mail.mail_validation",
    "social_core.pipeline.user.create_user",
    "accounts.pipeline.set_password",
    "social_core.pipeline.social_auth.associate_user",
    "social_core.pipeline.social_auth.load_extra_data",
)

# Email is only sent to verify addresses. Without an EMAIL_HOST mails are printed to the log.
EMAIL_HOST = os.environ.get("EMAIL_HOST", "")
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend" if EMAIL_HOST else \
    "django.core.mail.backends.console.EmailBackend"
EMAIL_PORT = int(os.environ.get("EMAIL_PORT", "587"))
EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = os.environ.get("EMAIL_USE_TLS", "true").strip().lower() in ("1", "true", "yes", "on")
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", "webmaster@localhost")


STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# Puzzle generation

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
PUZZLE_GENERATION_DIR = BASE_DIR / "data" / "datagrowth"
