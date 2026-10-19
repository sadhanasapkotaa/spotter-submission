from django.core.exceptions import ImproperlyConfigured
from django.views.generic import TemplateView
from rest_framework.response import Response
from rest_framework.views import APIView

from .errors import NotConfigured, TripError
from .locations import parse_location, require_in_usa
from .serializers import RouteRequestSerializer
from .service import plan_trip


class RouteView(APIView):
    """POST (JSON body) or GET (query string): optimal fuel plan for a US road trip."""

    def post(self, request):
        return self._run(request.data)

    def get(self, request):
        return self._run(request.query_params)

    def _run(self, data):
        ser = RouteRequestSerializer(data=data)
        if not ser.is_valid():
            return Response({"error": "invalid_request", "detail": ser.errors}, status=400)
        v = ser.validated_data
        try:
            start = parse_location(v["start"], "start")
            end = parse_location(v["end"], "end")
            require_in_usa(start=start, end=end)
            result = plan_trip(
                start,
                end,
                start_fuel_gallons=v.get("start_fuel_gallons"),
                exclude_approximate=v["exclude_approximate"],
            )
        except TripError as exc:
            return Response(exc.as_dict(), status=exc.status)
        except ImproperlyConfigured as exc:  # e.g. USA boundary not loaded yet
            err = NotConfigured(str(exc))
            return Response(err.as_dict(), status=err.status)
        return Response(result)


class MapView(TemplateView):
    template_name = "routing/map.html"
