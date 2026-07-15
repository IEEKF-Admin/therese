"""
therese/settings/__init__.py

Temporarily simplified settings to avoid split_settings import error.
We will switch back to split_settings later if needed.
"""

from .base import *
from .dev import *

# Optional local overrides (see local.py.example; local.py is gitignored).
try:
    from .local import *  # noqa: F403
except ImportError:
    pass

