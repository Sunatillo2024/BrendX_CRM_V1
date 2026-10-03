"""
BrandX POS System - Django Settings
Multi-Business Clothes Shop Point of Sale System
"""

import os
from pathlib import Path
from decouple import config

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = config('SECRET_KEY', default='django-insecure-brandx-change-in-production')
DEBUG = config('DEBUG', default=True, cast=bool)
ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='localhost,127.0.0.1').split(',')

# Application definition
DJANGO_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
]

LOCAL_APPS = [
    'apps.web.apps.WebConfig',
    'apps.stores.apps.StoresConfig',
    'apps.audit.apps.AuditConfig',
    'apps.authentication.apps.AuthenticationConfig',
    'apps.products.apps.ProductsConfig',
    'apps.inventory.apps.InventoryConfig',
    'apps.vendors.apps.VendorsConfig',
    'apps.customers.apps.CustomersConfig',
    'apps.sales.apps.SalesConfig',
    'apps.finance.apps.FinanceConfig',
    'apps.reports.apps.ReportsConfig',
    'apps.ai_analysis.apps.AiAnalysisConfig',
]

INSTALLED_APPS = DJANGO_APPS + LOCAL_APPS

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.locale.LocaleMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'apps.stores.middleware.StoreContextMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'brandx_api.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'apps.web.context_processors.brandx_context',
            ],
        },
    },
]

WSGI_APPLICATION = 'brandx_api.wsgi.application'

# PostgreSQL is primary; MySQL is retained only for migration-source access.
# SQLite remains useful for fast unit tests, not concurrency verification.
DB_ENGINE = config('DB_ENGINE', default='django.db.backends.postgresql')
if DB_ENGINE == 'django.db.backends.sqlite3':
    DATABASES = {
        'default': {
            'ENGINE': DB_ENGINE,
            'NAME': config('DB_NAME', default=':memory:'),
        }
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': DB_ENGINE,
            'NAME': config('DB_NAME', default='brandx'),
            'USER': config('DB_USER', default=''),
            'PASSWORD': config('DB_PASSWORD', default=''),
            'HOST': config('DB_HOST', default='localhost'),
            'PORT': config('DB_PORT', default='3306' if DB_ENGINE == 'django.db.backends.mysql' else '5432'),
            'OPTIONS': ({
                'charset': 'utf8mb4',
                'init_command': "SET sql_mode='STRICT_TRANS_TABLES'",
            } if DB_ENGINE == 'django.db.backends.mysql' else {}),
        }
    }

# Custom User Model
AUTH_USER_MODEL = 'authentication.User'

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'uz'
TIME_ZONE = 'Asia/Tashkent'
USE_I18N = True
USE_TZ = True

# UI languages: Uzbek + Russian only (English is not offered).
from django.utils.translation import gettext_lazy as _  # noqa: E402

LANGUAGES = [
    ('uz', _('Uzbek')),
    ('ru', _('Russian')),
]
LOCALE_PATHS = [BASE_DIR / 'locale']

# Static & Media Files
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static']
import sys as _sys

# Manifest storage (hashed filenames) is for production only. Tests and local
# development use plain storage so templates do not require collectstatic first.
_TEST_RUN = 'test' in _sys.argv
STATICFILES_STORAGE = config(
    'STATICFILES_STORAGE',
    default=(
        'django.contrib.staticfiles.storage.StaticFilesStorage'
        if (DEBUG or _TEST_RUN)
        else 'whitenoise.storage.CompressedManifestStaticFilesStorage'
    ),
)

# Server-rendered UI authentication (session-based).
LOGIN_URL = '/store/login/'
LOGIN_REDIRECT_URL = '/dashboard/'
LOGOUT_REDIRECT_URL = '/store/login/'

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Required by Django for the admin (session/CSRF) when served from a different
# scheme/host than the container, e.g. https://pos.example.com behind Nginx.
CSRF_TRUSTED_ORIGINS = config(
    'CSRF_TRUSTED_ORIGINS',
    default='http://localhost:8000',
).split(',')

# AI Integration (Groq - Free)
GROQ_API_KEY = config('GROQ_API_KEY', default='')
AI_MODEL = 'llama3-8b-8192'

# Business Settings
BUSINESS_NAME = config('BUSINESS_NAME', default='BrandX')
CURRENCY_CODE = config('CURRENCY_CODE', default='KGS')
CURRENCY_SYMBOL = config('CURRENCY_SYMBOL', default='сом')
CURRENCY_LOCALE = config('CURRENCY_LOCALE', default='ky-KG')
DEFAULT_LANGUAGE = config('DEFAULT_LANGUAGE', default='uz')   # 'uz' | 'ru'
SUPPORTED_LANGUAGES = ['uz', 'ru']
TAX_RATE = 0.0  # Set to your local tax rate (e.g., 0.15 for 15%)

# PIN login security
PIN_MIN_LENGTH = 4
PIN_MAX_LENGTH = 8
PIN_MAX_ATTEMPTS = 10          # failed attempts before temporary lock
PIN_LOCKOUT_SECONDS = 300      # lock duration after too many failures

# LocMem cache is per-process; kept for lightweight use only.
# PIN throttling is backed by the database so it works across gunicorn workers.
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'brandx',
    }
}

# ---------------------------------------------------------------------------
# Reverse-proxy / production hardening.
# All values below keep the current behaviour by default and are enabled from
# the environment once the stack is served over HTTPS (see deploy/.env.prod).
# ---------------------------------------------------------------------------
# Trust the edge proxy's forwarded scheme so request.is_secure() and absolute
# URIs are correct behind Nginx / Caddy.
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

# Redirect http -> https. Keep disabled while the stack is reachable over plain
# HTTP (e.g. first boot by IP); the edge proxy normally performs this redirect.
SECURE_SSL_REDIRECT = config('SECURE_SSL_REDIRECT', default=False, cast=bool)

# Secure-cookie flags. Enable together with HTTPS so the admin session cookie
# is never sent in clear text.
SESSION_COOKIE_SECURE = config('SESSION_COOKIE_SECURE', default=False, cast=bool)
CSRF_COOKIE_SECURE = config('CSRF_COOKIE_SECURE', default=False, cast=bool)

# HTTP Strict Transport Security. Leave at 0 until HTTPS is confirmed working.
SECURE_HSTS_SECONDS = config('SECURE_HSTS_SECONDS', default=0, cast=int)

# Always safe (do not depend on TLS).
SECURE_CONTENT_TYPE_NOSNIFF = True
