from django.contrib.gis.db import models


class Station(models.Model):
    """One physical fuel stop. `station_key` is OUR stable id; `opis_id` is informational only."""

    station_key = models.CharField(max_length=40, unique=True)
    opis_id = models.IntegerField(null=True, blank=True, db_index=True)
    rack_id = models.IntegerField(null=True, blank=True)
    name = models.CharField(max_length=255)
    address = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=2)
    price = models.DecimalField(max_digits=6, decimal_places=4)
    location = models.PointField(geography=True, srid=4326, null=True, blank=True)
    geocode_source = models.CharField(
        max_length=20, blank=True
    )  # census | census_approx | city_centroid
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [models.Index(fields=["state", "city"])]

    def __str__(self):
        return f"{self.name} ({self.city}, {self.state})"


class StationAlias(models.Model):
    """Every identity key ever seen for a station, so re-imports map back to the same row."""

    key = models.CharField(max_length=40, unique=True)
    station = models.ForeignKey(Station, on_delete=models.CASCADE, related_name="aliases")

    def __str__(self):
        return self.key


class Place(models.Model):
    """US city centroids (Census Gazetteer), used as the geocoding fallback."""

    name = models.CharField(max_length=120)  # normalised: upper-case, no punctuation
    state = models.CharField(max_length=2)
    location = models.PointField(srid=4326)
    land_sq_mi = models.FloatField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["name", "state"], name="uniq_place")]

    def __str__(self):
        return f"{self.name}, {self.state}"
