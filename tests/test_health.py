import pytest

from apps.core import views


@pytest.mark.django_db
def test_health_ok(client):
    response = client.get("/health/")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.django_db
def test_health_reports_503_when_the_database_is_down(client, monkeypatch):
    class BrokenConnection:
        def cursor(self):
            raise RuntimeError("database is down")

    monkeypatch.setattr(views, "connection", BrokenConnection())
    response = client.get("/health/")
    assert response.status_code == 503
    assert response.json()["status"] == "error"
