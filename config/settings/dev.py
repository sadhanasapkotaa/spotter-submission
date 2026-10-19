"""Shared, deployed development server. Production-like, but easier to debug."""

from .prod import *

SECURE_HSTS_SECONDS = 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_HSTS_PRELOAD = False
SECURE_SSL_REDIRECT = env.bool("DJANGO_SECURE_SSL_REDIRECT", default=False)
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
LOGGING["root"]["level"] = env("DJANGO_LOG_LEVEL", default="DEBUG")
