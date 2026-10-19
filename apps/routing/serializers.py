from rest_framework import serializers


class LocationField(serializers.Field):
    """Passes the raw value through: a string ("lat,lng" or "City, ST") or {"lat", "lng"}.

    Not a JSONField: with a GET query string the value is plain text such as "40.71,-74.0",
    which is not valid JSON. Parsing happens in locations.parse_location.
    """

    def to_internal_value(self, data):
        if isinstance(data, (str, dict)):
            return data
        raise serializers.ValidationError("Use 'lat,lng', 'City, ST' or {'lat': .., 'lng': ..}.")

    def to_representation(self, value):
        return value


class RouteRequestSerializer(serializers.Serializer):
    start = LocationField()
    end = LocationField()
    start_fuel_gallons = serializers.FloatField(required=False, min_value=0)
    exclude_approximate = serializers.BooleanField(required=False, default=False)
