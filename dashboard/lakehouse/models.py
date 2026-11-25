from django.db import models


class DimPair(models.Model):
    """Unmanaged mapping to the dbt mart analytics.dim_pair."""

    product_id = models.TextField(primary_key=True)
    base_currency = models.TextField()
    quote_currency = models.TextField()

    class Meta:
        managed = False
        db_table = '"analytics"."dim_pair"'
        verbose_name = "Trading Pair"
        verbose_name_plural = "Trading Pairs"

    def __str__(self) -> str:
        return self.product_id


class FactTrade(models.Model):
    """Unmanaged mapping to the dbt mart analytics.fact_trades."""

    trade_id = models.BigIntegerField(primary_key=True)
    product_id = models.TextField()
    side = models.TextField()
    size = models.FloatField()
    price = models.FloatField()
    trade_value_usd = models.FloatField()
    event_time = models.DateTimeField()
    trade_date = models.DateField()

    class Meta:
        managed = False
        db_table = '"analytics"."fact_trades"'
        verbose_name = "Fact Trade"
        verbose_name_plural = "Fact Trades"
        ordering = ("-event_time",)

    def __str__(self) -> str:
        return f"{self.product_id} #{self.trade_id} @ {self.price}"
