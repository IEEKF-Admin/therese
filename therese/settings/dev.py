"""
Development settings. Default when DJANGO_ENV is not 'prod'.
"""

from .base import *  # noqa: F401,F403

DEBUG = True

# Fast hasher for local development only (never use in production).
PASSWORD_HASHERS = [
    'django.contrib.auth.hashers.MD5PasswordHasher',
]

LOGIN_REDIRECT_URL = '/tasks/'
LOGOUT_REDIRECT_URL = '/tasks/'
LOGIN_URL = '/accounts/login/'
