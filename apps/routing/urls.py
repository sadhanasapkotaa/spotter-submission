from django.urls import path

from . import views

urlpatterns = [
    path("api/route/", views.RouteView.as_view(), name="route"),
    path("api/route/map/", views.MapView.as_view(), name="route-map"),
]
