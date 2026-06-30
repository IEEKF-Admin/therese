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
print(f"DEBUG: BASE_DIR = {BASE_DIR}")

SECRET_KEY = os.getenv('SECRET_KEY', 'django-insecure-fallback-key')

DEBUG = os.getenv('DEBUG', 'True') == 'True'

ALLOWED_HOSTS = os.getenv('ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',')

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
<<<<<<< HEAD
=======
    'whitenoise.runserver_nostatic',  # WhiteNoise for static files (dev + prod)
>>>>>>> new-main
    'django.contrib.staticfiles',

    # Custom apps
    'apps.core',
    'apps.accounts',
    'apps.hr',
    'apps.finances',
    'apps.tasks',
    'apps.documents',
    'widget_tweaks',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
<<<<<<< HEAD
=======
    'whitenoise.middleware.WhiteNoiseMiddleware',  # Serves static files in production (after Security, before others)
>>>>>>> new-main
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

# Database (wird in dev.py überschrieben)
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

# ====================== STATIC FILES ======================
STATIC_URL = '/static/'

# WICHTIG: Damit Django die Datei static/admin/js/contract_payscale.js findet
STATICFILES_DIRS = [
    BASE_DIR / 'static',
<<<<<<< HEAD
=======
    BASE_DIR / 'therese' / 'static',  # custom admin CSS/JS (admin_custom.css etc.)
>>>>>>> new-main
]

STATIC_ROOT = BASE_DIR / 'staticfiles'

<<<<<<< HEAD
=======
# WhiteNoise configuration (recommended for Gunicorn deploys)
# Use compressed + hashed filenames for better caching
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

# Optional: add to requirements: whitenoise
# On production server: pip install whitenoise
# Then after every code deploy: python manage.py collectstatic --noinput
# Restart gunicorn after collectstatic.

>>>>>>> new-main
# ====================== MEDIA FILES ======================
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# ====================== AUTH ======================
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
AUTH_USER_MODEL = 'accounts.CustomUser'