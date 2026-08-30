from datetime import timedelta
from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env(DEBUG=(bool, False))
environ.Env.read_env(BASE_DIR / ".env")

SECRET_KEY = env("SECRET_KEY")
DEBUG = env.bool("DEBUG", default=False)

ALLOWED_HOSTS = [
    host.strip()
    for host in env(
        "ALLOWED_HOSTS", default="localhost,127.0.0.1,0.0.0.0"
    ).split(",")
    if host.strip()
]

CSRF_TRUSTED_ORIGINS = [
    origin.strip()
    for origin in env("CSRF_TRUSTED_ORIGINS", default="").split(",")
    if origin.strip()
]

WEBAUTHN_ALLOWED_ORIGINS = [
    origin.strip()
    for origin in env("WEBAUTHN_ALLOWED_ORIGINS", default="").split(",")
    if origin.strip()
]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "corsheaders",
    "rest_framework",
    "rest_framework_simplejwt.token_blacklist",
    "drf_spectacular",
    "patients",
    "api.apps.ApiConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "patients.middleware.AuditAndSessionSecurityMiddleware",
    "patient_registry.middleware.BrowserSecurityMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "patient_registry.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "patient_registry.context_processors.app_version",
                "patient_registry.context_processors.global_theme",
            ],
        },
    },
]

WSGI_APPLICATION = "patient_registry.wsgi.application"

if env("DATABASE_URL", default=""):
    DATABASES = {"default": env.db("DATABASE_URL")}
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": env("POSTGRES_DB", default="patient_registry"),
            "USER": env("POSTGRES_USER", default="patient_registry"),
            "PASSWORD": env("POSTGRES_PASSWORD"),
            "HOST": env("POSTGRES_HOST", default="db"),
            "PORT": env("POSTGRES_PORT", default="5432"),
        }
    }

DATABASES["default"]["ATOMIC_REQUESTS"] = True

# Bound request metadata in memory and spool larger uploads to disk. Patient-data
# imports have a stricter 32 MiB application ceiling in patients.database_bundle.
DATA_UPLOAD_MAX_MEMORY_SIZE = env.int("DATA_UPLOAD_MAX_MEMORY_SIZE", default=2_621_440)
FILE_UPLOAD_MAX_MEMORY_SIZE = env.int("FILE_UPLOAD_MAX_MEMORY_SIZE", default=2_621_440)
DATA_UPLOAD_MAX_NUMBER_FILES = 1

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

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Kolkata"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "api.authentication.AuthVersionJWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticated",
    ),
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "EXCEPTION_HANDLER": "api.exceptions.mobile_api_exception_handler",
    "DEFAULT_THROTTLE_RATES": {
        "patient_search": "30/min",
    },
}

AUTH_THROTTLE_ACCOUNT_LIMIT = env.int("AUTH_THROTTLE_ACCOUNT_LIMIT", default=5)
AUTH_THROTTLE_IP_LIMIT = env.int("AUTH_THROTTLE_IP_LIMIT", default=30)
AUTH_THROTTLE_WINDOW_SECONDS = env.int("AUTH_THROTTLE_WINDOW_SECONDS", default=900)
AUTH_THROTTLE_BLOCK_SECONDS = env.int("AUTH_THROTTLE_BLOCK_SECONDS", default=900)
AUTH_THROTTLE_IDENTIFIER_MAX_LENGTH = env.int("AUTH_THROTTLE_IDENTIFIER_MAX_LENGTH", default=256)
AUTH_THROTTLE_RETENTION_SECONDS = env.int("AUTH_THROTTLE_RETENTION_SECONDS", default=86400)
AUTH_THROTTLE_CLEANUP_BATCH_SIZE = env.int("AUTH_THROTTLE_CLEANUP_BATCH_SIZE", default=1000)
AUTH_TRUSTED_PROXY_CIDRS = [
    value.strip()
    for value in env("AUTH_TRUSTED_PROXY_CIDRS", default="").split(",")
    if value.strip()
]
AUTH_CLIENT_IP_HEADER = env("AUTH_CLIENT_IP_HEADER", default="HTTP_X_FORWARDED_FOR").strip().upper()
PATIENT_MERGE_RECOVERY_HOURS = env.int("PATIENT_MERGE_RECOVERY_HOURS", default=72)
ALLOW_MOCK_DATA_SEEDING = env.bool("ALLOW_MOCK_DATA_SEEDING", default=DEBUG)

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=15),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=30),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
}

SPECTACULAR_SETTINGS = {
    "TITLE": "MEDTRACK Mobile API",
    "DESCRIPTION": "Native Android companion API for MEDTRACK case follow-up workflows.",
    "VERSION": "1.0.0",
    "COMPONENT_SPLIT_PATCH": False,
}

CORS_ALLOWED_ORIGINS = [
    origin.strip()
    for origin in env("CORS_ALLOWED_ORIGINS", default="").split(",")
    if origin.strip()
]

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "patients:dashboard"
LOGOUT_REDIRECT_URL = "login"

SESSION_COOKIE_AGE = env.int("SESSION_TIMEOUT_SECONDS", default=43200)
SESSION_SAVE_EVERY_REQUEST = env.bool("SESSION_SAVE_EVERY_REQUEST", default=True)
SESSION_EXPIRE_AT_BROWSER_CLOSE = False
DEVICE_APPROVAL_TRUST_COOKIE_NAME = env("DEVICE_APPROVAL_TRUST_COOKIE_NAME", default="medtrack_trusted_device")
DEVICE_APPROVAL_TRUST_COOKIE_AGE = env.int("DEVICE_APPROVAL_TRUST_COOKIE_AGE", default=315360000)
WEBAUTHN_RP_ID = env("WEBAUTHN_RP_ID", default="")
WEBAUTHN_RP_NAME = env("WEBAUTHN_RP_NAME", default="MEDTRACK")
FCM_ENABLED = env.bool("FCM_ENABLED", default=False)
FCM_CREDENTIALS_FILE = env("FCM_CREDENTIALS_FILE", default="")
FCM_PROJECT_ID = env("FCM_PROJECT_ID", default="")

# Deployment hardening toggles (set secure values in production environment).
SECURE_SSL_REDIRECT = env.bool("SECURE_SSL_REDIRECT", default=False)
SECURE_HSTS_SECONDS = env.int("SECURE_HSTS_SECONDS", default=0)
SECURE_HSTS_INCLUDE_SUBDOMAINS = env.bool("SECURE_HSTS_INCLUDE_SUBDOMAINS", default=False)
SECURE_HSTS_PRELOAD = env.bool("SECURE_HSTS_PRELOAD", default=False)
SESSION_COOKIE_SECURE = env.bool("SESSION_COOKIE_SECURE", default=False)
CSRF_COOKIE_SECURE = env.bool("CSRF_COOKIE_SECURE", default=False)
SECURE_CONTENT_TYPE_NOSNIFF = env.bool("SECURE_CONTENT_TYPE_NOSNIFF", default=True)
SECURE_REFERRER_POLICY = env("SECURE_REFERRER_POLICY", default="same-origin")
X_FRAME_OPTIONS = env("X_FRAME_OPTIONS", default="DENY")

if env.bool("USE_X_FORWARDED_PROTO", default=False):
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
