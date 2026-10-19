"""API-level errors. Each carries an HTTP status and a stable machine-readable code."""


class TripError(Exception):
    status = 400
    code = "bad_request"

    def __init__(self, message: str, **extra):
        super().__init__(message)
        self.message = message
        self.extra = extra

    def as_dict(self) -> dict:
        return {"error": self.code, "detail": self.message, **self.extra}


class InvalidRequest(TripError):
    status, code = 400, "invalid_request"


class LocationError(TripError):
    status, code = 400, "invalid_location"


class OutsideUSA(TripError):
    status, code = 422, "outside_usa"


class RouteNotFound(TripError):
    status, code = 422, "route_not_found"


class NoFeasiblePlan(TripError):
    status, code = 422, "no_feasible_fuel_plan"


class ProviderUnavailable(TripError):
    status, code = 502, "routing_provider_unavailable"


class ProviderTimeout(TripError):
    status, code = 504, "routing_provider_timeout"


class NotConfigured(TripError):
    status, code = 503, "service_not_ready"
