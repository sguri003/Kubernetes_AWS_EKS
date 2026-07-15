from django.urls import path
from . import views

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("api/summary/", views.api_summary, name="api_summary"),
    path("api/prices/", views.api_prices, name="api_prices"),
    path("api/live/", views.api_live, name="api_live"),
]
