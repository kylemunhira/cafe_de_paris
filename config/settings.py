import os
from decimal import Decimal
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

# Project .env wins over machine/user env (same server may host other apps).
load_dotenv(BASE_DIR / ".env", override=True)

SECRET_KEY = os.getenv(
    "DJANGO_SECRET_KEY",
    "django-insecure-byq87o4!*6jet@qa9wtb33vlm16!ov1mw%b9ayd=+^56%+n40k",
)

DEBUG = os.getenv("DJANGO_DEBUG", "true").lower() == "true"

ALLOWED_HOSTS = [
    host.strip()
    for host in os.getenv("DJANGO_ALLOWED_HOSTS", "127.0.0.1,localhost").split(",")
    if host.strip()
]

CSRF_TRUSTED_ORIGINS = [
    origin.strip()
    for origin in os.getenv("DJANGO_CSRF_TRUSTED_ORIGINS", "").split(",")
    if origin.strip()
]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "corsheaders",
    "accounts",
    "branches",
    "catalog",
    "customers",
    "inventory",
    "purchasing",
    "orders",
    "payments",
    "zimra_fiscal",
    "bakery",
    "reports",
    "sync",
    "ui",
    "audit",
    "rest_framework.authtoken",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "ui" / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.template.context_processors.i18n",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "accounts.context_processors.nav_access",
                "ui.context_processors.asset_version",
                "ui.context_processors.i18n_js_catalog",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

if os.getenv("DB_ENGINE") == "postgresql":
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.getenv("DB_NAME", "cafe_de_paris"),
            "USER": os.getenv("DB_USER", "postgres"),
            "PASSWORD": os.getenv("DB_PASSWORD", ""),
            "HOST": os.getenv("DB_HOST", "localhost"),
            "PORT": os.getenv("DB_PORT", "5432"),
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 4},
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

LANGUAGE_CODE = "en"
LANGUAGES = [
    ("en", "English"),
    ("fr", "Français"),
    ("es", "Español"),
    ("ar", "العربية"),
    ("zh-hans", "中文"),
]
LOCALE_PATHS = [BASE_DIR / "locale"]
TIME_ZONE = "Africa/Harare"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedStaticFilesStorage",
    },
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGIN_URL = "ui:login"
LOGIN_REDIRECT_URL = "ui:dashboard"
LOGOUT_REDIRECT_URL = "ui:login"

AUTHENTICATION_BACKENDS = [
    "accounts.backends.CaseInsensitiveModelBackend",
    "accounts.backends.AccessCodeBackend",
]

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.TokenAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.AllowAny",
    ],
    "DEFAULT_PAGINATION_CLASS": "config.pagination.StandardPagination",
}

CORS_ALLOW_ALL_ORIGINS = DEBUG

ZIMRA_FISCAL_BASE_URL = os.getenv(
    "ZIMRA_FISCAL_BASE_URL",
    "http://192.168.100.8:5008",
)
ZIMRA_DEFAULT_DEVICE_ID = os.getenv("ZIMRA_DEFAULT_DEVICE_ID", "30541")
ZIMRA_SUBMIT_TIMEOUT = int(os.getenv("ZIMRA_SUBMIT_TIMEOUT", "30"))
ZIMRA_GET_STATUS_ACTION = os.getenv("ZIMRA_GET_STATUS_ACTION", "getstatus")
ZIMRA_GET_STATUS_FALLBACKS = os.getenv("ZIMRA_GET_STATUS_FALLBACKS", "")
ZIMRA_OPEN_DAY_ACTION = os.getenv("ZIMRA_OPEN_DAY_ACTION", "openday")
ZIMRA_OPEN_DAY_FALLBACKS = os.getenv("ZIMRA_OPEN_DAY_FALLBACKS", "")
ZIMRA_CLOSE_DAY_ACTION = os.getenv("ZIMRA_CLOSE_DAY_ACTION", "close_day")

# ZIMRA tax profile: test → standard tax ID 517; production → 515.
# Optional per-field overrides below take precedence over the profile.
ZIMRA_ENV = os.getenv("ZIMRA_ENV", "test").strip().lower() or "test"
_ZIMRA_TAX_EMPTY = object()


def _zimra_tax_env(name, default=_ZIMRA_TAX_EMPTY):
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return None if default is _ZIMRA_TAX_EMPTY else default
    return raw.strip()


ZIMRA_STANDARD_TAX_PERCENT = _zimra_tax_env("ZIMRA_STANDARD_TAX_PERCENT")
ZIMRA_STANDARD_TAX_CODE = _zimra_tax_env("ZIMRA_STANDARD_TAX_CODE")
_raw_standard_tax_id = _zimra_tax_env("ZIMRA_STANDARD_TAX_ID")
ZIMRA_STANDARD_TAX_ID = (
    int(_raw_standard_tax_id) if _raw_standard_tax_id is not None else None
)
ZIMRA_ZERO_RATED_TAX_PERCENT = _zimra_tax_env("ZIMRA_ZERO_RATED_TAX_PERCENT")
ZIMRA_ZERO_RATED_TAX_CODE = _zimra_tax_env("ZIMRA_ZERO_RATED_TAX_CODE")
_raw_zero_tax_id = _zimra_tax_env("ZIMRA_ZERO_RATED_TAX_ID")
ZIMRA_ZERO_RATED_TAX_ID = (
    int(_raw_zero_tax_id) if _raw_zero_tax_id is not None else None
)

# Prices are tax-inclusive; receipt subtotal = total / (1 + rate/100).
INCLUSIVE_TAX_RATE = Decimal(os.getenv("INCLUSIVE_TAX_RATE", "15.5"))
# ZTA levy on fiscal branches: 2% of the amount before VAT, already inside the selling price.
ZTA_LEVY_RATE = Decimal(os.getenv("ZTA_LEVY_RATE", "2"))

# Android kitchen app OTA updates — copy APK to releases/ and bump version here.
RELEASES_DIR = BASE_DIR / "releases"
KITCHEN_APP_VERSION_CODE = int(os.getenv("KITCHEN_APP_VERSION_CODE", "2"))
KITCHEN_APP_VERSION_NAME = os.getenv("KITCHEN_APP_VERSION_NAME", "1.2.0")
KITCHEN_APP_MIN_VERSION_CODE = int(os.getenv("KITCHEN_APP_MIN_VERSION_CODE", "1"))
KITCHEN_APP_APK_FILENAME = os.getenv("KITCHEN_APP_APK_FILENAME", "kitchen.apk")
KITCHEN_APP_RELEASE_NOTES = os.getenv("KITCHEN_APP_RELEASE_NOTES", "")
KITCHEN_APP_FORCE_UPDATE = os.getenv("KITCHEN_APP_FORCE_UPDATE", "false").lower() == "true"

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "[{asctime}] {levelname} {name}: {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
    },
    "loggers": {
        "zimra_fiscal": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
    },
}
