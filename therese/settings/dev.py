from .base import *

DEBUG = True

# === Für die Entwicklung: SQLite statt PostgreSQL ===
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

# Schnellere Password-Hasher in der Entwicklung
PASSWORD_HASHERS = [
    'django.contrib.auth.hashers.MD5PasswordHasher',
]