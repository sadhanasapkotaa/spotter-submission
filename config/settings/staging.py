"""Staging: production clone. Keep differences minimal so staging stays a faithful rehearsal."""

from .prod import *

# Don't pin HSTS preload from a non-production hostname.
SECURE_HSTS_PRELOAD = False
SECURE_HSTS_SECONDS = env.int("DJANGO_SECURE_HSTS_SECONDS", default=3600)
