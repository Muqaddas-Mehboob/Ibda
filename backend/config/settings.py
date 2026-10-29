"""
Django settings for config project.
"""

import environ
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# Environment variables
env = environ.Env(
    DJANGO_DEBUG=(bool, True),
)

environ.Env.read_env(BASE_DIR / ".env")

# Security
SECRET_KEY = env(
    "DJANGO_SECRET_KEY",
    default="unsafe-development-key",
)

DEBUG = env("DJANGO_DEBUG")

ALLOWED_HOSTS = env.list(
    "DJANGO_ALLOWED_HOSTS",
    default=["127.0.0.1", "localhost"],
)

# Supabase configuration
SUPABASE_URL = env("SUPABASE_URL", default="").rstrip("/")
SUPABASE_PUBLISHABLE_KEY = env(
    "SUPABASE_PUBLISHABLE_KEY",
    default="",
)

# AI credentials are server-only and must never be exposed to the mobile app.
AI_PROVIDER = env("AI_PROVIDER", default="openai")
AI_API_KEY = env("AI_API_KEY", default="")
AI_MODEL = env("AI_MODEL", default="")
AI_BASE_URL = env(
    "AI_BASE_URL",
    default="https://api.openai.com/v1",
).rstrip("/")

# Social credentials remain server-side; OAuth adapters are enabled only when
# implemented and configured for a provider.
SOCIAL_TOKEN_ENCRYPTION_KEY = env(
    "SOCIAL_TOKEN_ENCRYPTION_KEY",
    default="",
)

# Provider-neutral payment settings remain for the generic webhook adapter.
PAYMENT_PROVIDER = env("PAYMENT_PROVIDER", default="")
PAYMENT_WEBHOOK_SECRET = env("PAYMENT_WEBHOOK_SECRET", default="")
PAYMENT_PRODUCT_PREMIUM_MONTHLY = env(
    "PAYMENT_PRODUCT_PREMIUM_MONTHLY",
    default="",
)
PAYMENT_PRODUCT_PREMIUM_ANNUAL = env(
    "PAYMENT_PRODUCT_PREMIUM_ANNUAL",
    default="",
)

# Stripe credentials and catalog identifiers are server-only. The legacy
# PREMIUM price settings remain fallbacks for existing Pro subscriptions.
STRIPE_SECRET_KEY = env("STRIPE_SECRET_KEY", default="")
STRIPE_WEBHOOK_SECRET = env("STRIPE_WEBHOOK_SECRET", default="")
STRIPE_CHECKOUT_SUCCESS_URL = env("STRIPE_CHECKOUT_SUCCESS_URL", default="")
STRIPE_CHECKOUT_CANCEL_URL = env("STRIPE_CHECKOUT_CANCEL_URL", default="")
STRIPE_PRICE_STARTER_MONTHLY = env("STRIPE_PRICE_STARTER_MONTHLY", default="")
STRIPE_PRICE_STARTER_ANNUAL = env(
    "STRIPE_PRICE_STARTER_ANNUAL",
    default=env("STRIPE_PRICE_STARTER_YEARLY", default=""),
)
STRIPE_PRICE_PRO_MONTHLY = env(
    "STRIPE_PRICE_PRO_MONTHLY",
    default=PAYMENT_PRODUCT_PREMIUM_MONTHLY,
)
STRIPE_PRICE_PRO_ANNUAL = env(
    "STRIPE_PRICE_PRO_ANNUAL",
    default=env(
        "STRIPE_PRICE_PRO_YEARLY",
        default=PAYMENT_PRODUCT_PREMIUM_ANNUAL,
    ),
)
STRIPE_PRICE_ENTERPRISE_MONTHLY = env(
    "STRIPE_PRICE_ENTERPRISE_MONTHLY",
    default="",
)
STRIPE_PRICE_ENTERPRISE_ANNUAL = env(
    "STRIPE_PRICE_ENTERPRISE_ANNUAL",
    default=env("STRIPE_PRICE_ENTERPRISE_YEARLY", default=""),
)
SUBSCRIPTION_ENTITLEMENT_LIMITS = env(
    "SUBSCRIPTION_ENTITLEMENT_LIMITS",
    default="{}",
)

# Django applications
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "corsheaders",
    "core.apps.CoreConfig",
]

# Middleware
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "corsheaders.middleware.CorsMiddleware",
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

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# Django REST Framework
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "core.authentication.SupabaseAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
    ],
}

# Database: Supabase PostgreSQL when DATABASE_URL is configured
database_url = env("DATABASE_URL", default="").strip()

if database_url:
    import dj_database_url

    DATABASES = {
        "default": dj_database_url.parse(
            database_url,
            conn_max_age=60,
            ssl_require=database_url.lower().startswith(
                ("postgres://", "postgresql://")
            ),
        )
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": (
            "django.contrib.auth.password_validation."
            "UserAttributeSimilarityValidator"
        )
    },
    {
        "NAME": (
            "django.contrib.auth.password_validation."
            "MinimumLengthValidator"
        )
    },
    {
        "NAME": (
            "django.contrib.auth.password_validation."
            "CommonPasswordValidator"
        )
    },
    {
        "NAME": (
            "django.contrib.auth.password_validation."
            "NumericPasswordValidator"
        )
    },
]

# Internationalization
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# Static files
STATIC_URL = "static/"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# CORS
CORS_ALLOWED_ORIGINS = env.list(
    "CORS_ALLOWED_ORIGINS",
    default=[
        "http://localhost:8081",
        "http://127.0.0.1:8081",
    ],
)