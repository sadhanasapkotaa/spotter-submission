from django.contrib.gis.db import models


class Country(models.Model):
    name = models.CharField(max_length=100)
    iso_a3 = models.CharField(max_length=3, unique=True)
    geom = models.MultiPolygonField(srid=4326)  # GiST index is created automatically

    def __str__(self):
        return self.name
