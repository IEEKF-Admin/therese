"""
Settings package entrypoint.

- Development (default): loads base + dev
- Production: set DJANGO_ENV=prod or ENVIRONMENT=production → base + prod
- Optional: local.py (gitignored) for machine-specific overrides
"""

import os

from .base import *  # noqa: F401,F403

_env = (
    os.getenv('DJANGO_ENV')
    or os.getenv('ENVIRONMENT')
    or 'dev'
).strip().lower()

if _env in ('prod', 'production'):
    from .prod import *  # noqa: F401,F403
else:
    from .dev import *  # noqa: F401,F403

try:
    from .local import *  # noqa: F401,F403
except ImportError:
    pass
