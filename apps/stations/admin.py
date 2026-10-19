from django.contrib import admin

from .models import Place, Station


@admin.register(Station)
class StationAdmin(admin.ModelAdmin):
    list_display = ("name", "city", "state", "price", "geocode_source", "station_key")
    list_filter = ("state", "geocode_source")
    search_fields = ("name", "city", "address", "station_key")
    exclude = ("location",)


@admin.register(Place)
class PlaceAdmin(admin.ModelAdmin):
    list_display = ("name", "state")
    search_fields = ("name",)
    exclude = ("location",)
