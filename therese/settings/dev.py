"""
therese/settings/dev.py
"""

from .base import *

DEBUG = True

# In der Entwicklung werden schnellere Passwort-Hasher verwendet.
# Die Datenbank-Konfiguration kommt aus base.py (MariaDB, wenn DB_HOST gesetzt).
PASSWORD_HASHERS = [
    'django.contrib.auth.hashers.MD5PasswordHasher',
]

# = AUTH REDIRECTS =
LOGIN_REDIRECT_URL = '/tasks/'           # ← nach Login immer zum Dashboard
LOGOUT_REDIRECT_URL = '/tasks/'          # ← nach Logout ebenfalls zum Dashboard
LOGIN_URL = '/accounts/login/'           # ← korrekter Login-Pfad

