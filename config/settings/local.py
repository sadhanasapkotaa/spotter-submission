"""Developer machine (docker compose or bare `uv run`)."""

from .base import *

DEBUG = True
ALLOWED_HOSTS = ["localhost", "127.0.0.1", "0.0.0.0", "[::1]"]  # noqa: S104
SECRET_KEY = env("DJANGO_SECRET_KEY", default="local-insecure-key-do-not-use-elsewhere")

# Plain static files, no manifest hashing, so no collectstatic needed locally.
STORAGES["staticfiles"] = {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
LOGGING["root"]["level"] = "DEBUG"
