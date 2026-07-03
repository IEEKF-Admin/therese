"""
therese/settings/base.py
Base settings for THERESE project.
"""

from pathlib import Path
import os
from dotenv import load_dotenv

load_dotenv()

# === BASE_DIR - zeigt auf den Ordner mit manage.py ===
BASE_DIR = Path(__file__).resolve().parent.parent.parent
# print(f"DEBUG: BASE_DIR = {BASE_DIR}")  # Nur für Debugging aktivieren

SECRET_KEY = os.getenv('SECRET_KEY', 'django-insecure-fallback-key')

DEBUG = os.getenv('DEBUG', 'True') == 'True'

# ALLOWED_HOSTS should be set via .env (recommended for production)
# Use exact hostnames/IPs. For IP ranges (e.g. 172.26.70.*) a custom patch is needed.
ALLOWED_HOSTS = [h.strip() for h in os.getenv('ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',') if h.strip()]

# Patch to support IP range wildcards like '172.26.70.*' (Django doesn't support natively)
import django.utils.http as _http_utils
_original_is_same = _http_utils.is_same_domain

def _ip_range_is_same(host, pattern):
    if pattern.endswith('.*'):
        base = pattern[:-2]
        if host == base or host.startswith(base + '.'):
            suffix = host[len(base):].lstrip('.')
            if suffix.isdigit():
                return True
    return _original_is_same(host, pattern)

_http_utils.is_same_domain = _ip_range_is_same

import django.http.request as _req
_req.is_same_domain = _ip_range_is_same

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',


    'whitenoise.runserver_nostatic',  # WhiteNoise for static files (dev + prod)

    'django.contrib.staticfiles',

    # Custom apps
    'apps.core',
    'apps.accounts',
    'apps.finances',
    'apps.hr',
    'apps.tasks',
    'apps.documents',
    'widget_tweaks',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',


    'whitenoise.middleware.WhiteNoiseMiddleware',  # Serves static files in production (after Security, before others)

    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'apps.accounts.middleware.ForcePasswordChangeMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'therese.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'therese' / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'therese.context_processors.user_groups',   # ← NEU
            ],
        },
    },
]

WSGI_APPLICATION = 'therese.wsgi.application'

# Database
# Verwendet MariaDB/MySQL, wenn DB_HOST in .env gesetzt ist.
# Ansonsten Fallback auf SQLite (nur für lokale Entwicklung ohne DB-Server).
db_host = os.getenv('DB_HOST', '').strip()
if db_host:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.mysql',
            'NAME': os.getenv('DB_NAME', 'therese'),
            'USER': os.getenv('DB_USER', 'root'),
            'PASSWORD': os.getenv('DB_PASSWORD', ''),
            'HOST': db_host,
            'PORT': os.getenv('DB_PORT', '3306'),
            'OPTIONS': {
                'charset': 'utf8mb4',
                'init_command': "SET sql_mode='STRICT_TRANS_TABLES'",
            },
        }
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'de-de'
TIME_ZONE = 'Europe/Berlin'
USE_I18N = True
USE_TZ = True

# = STATIC FILES =
STATIC_URL = '/static/'

# WICHTIG: Damit Django die Datei static/admin/js/contract_payscale.js findet
STATICFILES_DIRS = [
    BASE_DIR / 'static',


    BASE_DIR / 'therese' / 'static',  # custom admin CSS/JS (admin_custom.css etc.)

]

STATIC_ROOT = BASE_DIR / 'staticfiles'



# WhiteNoise configuration (recommended for Gunicorn deploys)
# Use compressed + hashed filenames for better caching
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

# = MEDIA FILES =
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# = AUTH =
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
AUTH_USER_MODEL = 'accounts.CustomUser'

# = AUTH REDIRECTS (used in both dev and prod) =
LOGIN_REDIRECT_URL = '/tasks/'
LOGOUT_REDIRECT_URL = '/tasks/'
LOGIN_URL = '/accounts/login/'

# = HTTPS / Security Einstellungen =
# Diese Einstellungen sind besonders wichtig, wenn der Server über HTTPS läuft.
# Für direkten Gunicorn + self-signed Certs oder hinter einem Proxy.
if not DEBUG:
    # SSL Redirect nur aktivieren, wenn wirklich gewünscht (kann bei gemischtem Setup Probleme machen)
    # SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 31536000  # 1 Jahr
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_BROWSER_XSS_FILTER = True
    X_FRAME_OPTIONS = 'DENY'

# Wenn hinter einem Reverse-Proxy (Nginx etc.) der TLS terminiert:
# SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

