"""
therese/settings/dev.py
"""

from .base import *

DEBUG = True

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

PASSWORD_HASHERS = [
    'django.contrib.auth.hashers.MD5PasswordHasher',
]

# = AUTH REDIRECTS =
LOGIN_REDIRECT_URL = '/tasks/'           # â† nach Login immer zum Dashboard
LOGOUT_REDIRECT_URL = '/tasks/'          # â† nach Logout ebenfalls zum Dashboard
LOGIN_URL = '/accounts/login/'           # â† korrekter Login-Pfad

