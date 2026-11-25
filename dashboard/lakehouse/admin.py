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
    search_fields = ("product_id", "base_currency", "quote_currency")


@admin.register(FactTrade)
class FactTradeAdmin(ReadOnlyWarehouseAdmin):
    list_display = ("trade_id", "product_id", "side", "price", "size", "trade_value_usd", "event_time")
    list_filter = ("product_id", "side")
    search_fields = ("trade_id", "product_id")
