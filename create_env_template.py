"""Create .env from .env.example for fresh THERESE installs (never overwrites existing .env)."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent
EXAMPLE = ROOT / '.env.example'
TARGET = ROOT / '.env'


def generate_secret_key() -> str:
    try:
        from django.core.management.utils import get_random_secret_key
        return get_random_secret_key()
    except Exception:
        import secrets
        return secrets.token_urlsafe(50)


def main() -> None:
    if TARGET.exists():
        print('.env already exists — not overwritten.')
        return

    if not EXAMPLE.exists():
        raise SystemExit('Missing .env.example — cannot create .env')

    content = EXAMPLE.read_text(encoding='utf-8')
    placeholder = 'change-me-generate-your-own'
    if placeholder in content:
        content = content.replace(placeholder, generate_secret_key(), 1)

    TARGET.write_text(content, encoding='utf-8')
    print('.env created from .env.example — please review ALLOWED_HOSTS and DB_* for your environment.')


if __name__ == '__main__':
    main()