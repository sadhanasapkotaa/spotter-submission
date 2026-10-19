"""The deployed settings modules differ from each other only in a few safe overrides."""

import importlib

import pytest


def load(name):
    return importlib.import_module(f"config.settings.{name}")


@pytest.mark.parametrize("name", ["prod", "staging", "dev"])
def test_deployed_environments_never_run_with_debug(name):
    assert load(name).DEBUG is False


def test_prod_forces_https_but_keeps_the_health_probe_reachable():
    prod = load("prod")
    assert prod.SECURE_SSL_REDIRECT is True
    assert prod.SESSION_COOKIE_SECURE is True and prod.CSRF_COOKIE_SECURE is True
    assert prod.SECURE_HSTS_SECONDS >= 31536000
    assert r"^health/$" in prod.SECURE_REDIRECT_EXEMPT


def test_staging_does_not_preload_hsts():
    staging = load("staging")
    assert staging.SECURE_HSTS_PRELOAD is False
    assert staging.SECURE_HSTS_SECONDS < 31536000


def test_dev_is_relaxed_for_plain_http():
    dev = load("dev")
    assert dev.SECURE_HSTS_SECONDS == 0
    assert dev.SESSION_COOKIE_SECURE is False
