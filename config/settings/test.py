"""Used by pytest / CI."""

import os

os.environ.setdefault("DJANGO_SECRET_KEY", "test-key")
os.environ.setdefault("DATABASE_URL", "sqlite:///test.sqlite3")

from .base import *

SECRET_KEY = "test-key"  # noqa: S105
DEBUG = False
ALLOWED_HOSTS = ["testserver", "localhost"]
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]  # fast tests
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
STORAGES["staticfiles"] = {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}
