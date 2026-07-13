"""Create a default .env file for fresh THERESE installs."""
from pathlib import Path

try:
    from django.core.management.utils import get_random_secret_key
    secret_key = get_random_secret_key()
except Exception:
    import secrets
    secret_key = secrets.token_urlsafe(50)

content = f"""# THERESE - Umgebungsvariablen (bitte anpassen)
DEBUG=True
SECRET_KEY={secret_key}

# SQLite (Entwicklung): DB_HOST leer lassen
# MariaDB/MySQL (Produktion):
# DB_HOST=localhost
# DB_NAME=therese
# DB_USER=therese
# DB_PASSWORD=geheim
# DB_PORT=3306

ALLOWED_HOSTS=localhost,127.0.0.1
"""

Path('.env').write_text(content, encoding='utf-8')
print('.env created')