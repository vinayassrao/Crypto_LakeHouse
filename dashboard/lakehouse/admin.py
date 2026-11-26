from django.contrib import admin

from .models import DimPair, FactTrade


class ReadOnlyWarehouseAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(DimPair)
class DimPairAdmin(ReadOnlyWarehouseAdmin):
    list_display = ("product_id", "base_currency", "quote_currency")
    list_filter = ("quote_currency", "base_currency")
    search_fields = ("product_id", "base_currency", "quote_currency")


@admin.register(FactTrade)
class FactTradeAdmin(ReadOnlyWarehouseAdmin):
    list_display = (
        "trade_id",
        "product_id",
        "quote_currency",
        "side",
        "price",
        "size",
        "notional_value",
        "event_time",
    )
    list_filter = ("product_id", "quote_currency", "side")
    search_fields = ("trade_id", "product_id")
