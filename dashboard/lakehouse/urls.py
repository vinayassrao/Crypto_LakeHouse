from django.urls import path

from . import views

app_name = "lakehouse"

urlpatterns = [
    path("", views.dashboard_view, name="dashboard"),
    path("api/health/", views.health_api, name="health_api"),
    path("api/pairs/", views.pairs_api, name="pairs_api"),
    path("api/ohlc/", views.ohlc_api, name="ohlc_api"),
    path("api/reconciliation/", views.reconciliation_api, name="reconciliation_api"),
    path("api/daily-volume/", views.daily_volume_api, name="daily_volume_api"),
]
