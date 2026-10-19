from django.db import connection
from django.http import JsonResponse


def health(request):
    """Liveness/readiness probe: confirms the app is up and the DB is reachable."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
    except Exception:  # noqa: BLE001
        return JsonResponse({"status": "error", "database": "unavailable"}, status=503)
    return JsonResponse({"status": "ok"})
