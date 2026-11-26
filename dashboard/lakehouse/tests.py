from unittest.mock import patch

from django.test import Client, SimpleTestCase

from lakehouse import services


class CurrencyHelpersTests(SimpleTestCase):
    def test_convert_amount_between_currencies(self):
        rates = {"USD": 1.0, "EUR": 0.9, "INR": 90.0}
        self.assertEqual(services.convert_amount(100.0, "USD", "NATIVE", rates), 100.0)
        self.assertEqual(services.convert_amount(100.0, "EUR", "EUR", rates), 100.0)
        self.assertAlmostEqual(services.convert_amount(100.0, "USD", "EUR", rates), 90.0)
        self.assertAlmostEqual(services.convert_amount(90.0, "EUR", "INR", rates), 9000.0)
        self.assertIsNone(services.convert_amount(100.0, "USD", "XYZ", rates))
        self.assertIsNone(services.convert_amount(None, "USD", "EUR", rates))

    def test_quote_filtering(self):
        pairs = ["BTC-USD", "ETH-USD", "BTC-EUR", "BTC-GBP"]
        self.assertEqual(services.get_quote_currencies(pairs), ["USD", "EUR", "GBP"])
        self.assertEqual(services.filter_pairs_by_quote(pairs, "ALL"), pairs)
        self.assertEqual(services.filter_pairs_by_quote(pairs, "EUR"), ["BTC-EUR"])


class DashboardAndApiTests(SimpleTestCase):
    def setUp(self):
        self.client = Client()

    @patch("lakehouse.views.services.get_pipeline_status")
    @patch("lakehouse.views.services.get_pairs")
    @patch("lakehouse.views.services.get_fx_rates")
    @patch("lakehouse.views.services.get_hourly_ohlc")
    @patch("lakehouse.views.services.get_daily_volume")
    @patch("lakehouse.views.services.get_reconciliation")
    @patch("lakehouse.views.services.get_recent_trades")
    @patch("lakehouse.views.services.get_multi_pair_overview")
    @patch("lakehouse.views.services.get_multi_pair_series")
    def test_dashboard_renders_with_multi_currency(
        self,
        mock_compare,
        mock_overview,
        mock_trades,
        mock_recon,
        mock_vol,
        mock_ohlc,
        mock_fx,
        mock_pairs,
        mock_status,
    ):
        mock_status.return_value = {
            "db_connected": True,
            "error": None,
            "counts": {
                "raw_trades": 42,
                "raw_candles": 900,
                "fact_trades": 40,
                "reconciliation": 300,
            },
        }
        mock_pairs.return_value = ["BTC-USD", "ETH-USD", "BTC-EUR"]
        mock_fx.return_value = ({"USD": 1.0, "EUR": 0.9, "INR": 90.0}, True)
        mock_ohlc.return_value = [
            {
                "hour": "2026-11-25T08:00:00+00:00",
                "open": 8100000.0,
                "high": 8145000.0,
                "low": 8091000.0,
                "close": 8136000.0,
                "volume": 1.25,
                "trade_count": 40,
            }
        ]
        mock_vol.return_value = [
            {
                "trade_date": "2026-11-25",
                "total_volume": 1.25,
                "total_value_usd": 112500.0,
                "display_notional": 10125000.0,
                "trade_count": 40,
            }
        ]
        mock_recon.return_value = [
            {
                "day": "2026-11-25",
                "my_volume": 1.25,
                "official_volume": 5000.0,
                "volume_gap": 4998.75,
                "status": "DIVERGENT",
            }
        ]
        mock_trades.return_value = [
            {
                "trade_id": 1001,
                "side": "buy",
                "size": 0.1,
                "price": 8136000.0,
                "notional_value": 813600.0,
                "event_time": "2026-11-25T08:30:00+00:00",
            }
        ]
        mock_overview.return_value = [
            {
                "product_id": "BTC-EUR",
                "base_currency": "BTC",
                "quote_currency": "EUR",
                "display_currency": "INR",
                "currency_symbol": "₹",
                "display_price": 8136000.0,
                "stream_volume": 1.25,
                "trade_count": 40,
                "recon_status": "DIVERGENT",
            }
        ]
        mock_compare.return_value = {"BTC-EUR": mock_ohlc.return_value}

        response = self.client.get("/?quote=EUR&pair=BTC-EUR&currency=INR&compare=BTC-EUR")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Crypto Market Data Lakehouse")
        self.assertContains(response, "Live Coinbase FX")
        self.assertContains(response, "DIVERGENT")
        self.assertContains(response, "8136000.00")

    @patch("lakehouse.views.services.get_pipeline_status")
    def test_dashboard_handles_disconnected_db(self, mock_status):
        mock_status.return_value = {
            "db_connected": False,
            "error": "connection refused",
            "counts": {
                "raw_trades": None,
                "raw_candles": None,
                "fact_trades": None,
                "reconciliation": None,
            },
        }
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Warehouse Postgres is not reachable")

    @patch("lakehouse.views.services.get_pipeline_status")
    def test_health_api_status_codes(self, mock_status):
        mock_status.return_value = {"db_connected": True, "error": None, "counts": {}}
        ok_resp = self.client.get("/api/health/")
        self.assertEqual(ok_resp.status_code, 200)
        self.assertEqual(ok_resp.json()["db_connected"], True)

        mock_status.return_value = {"db_connected": False, "error": "down", "counts": {}}
        err_resp = self.client.get("/api/health/")
        self.assertEqual(err_resp.status_code, 503)

    @patch("lakehouse.views.services.get_pairs")
    @patch("lakehouse.views.services.get_fx_rates")
    @patch("lakehouse.views.services.get_multi_pair_overview")
    @patch("lakehouse.views.services.get_hourly_ohlc")
    @patch("lakehouse.views.services.get_reconciliation")
    @patch("lakehouse.views.services.get_daily_volume")
    def test_json_endpoints(
        self, mock_vol, mock_recon, mock_ohlc, mock_overview, mock_fx, mock_pairs
    ):
        mock_pairs.return_value = ["BTC-USD", "ETH-USD", "BTC-EUR"]
        mock_fx.return_value = ({"USD": 1.0, "EUR": 0.9}, True)
        mock_overview.return_value = [{"product_id": "BTC-EUR", "display_currency": "EUR"}]
        mock_ohlc.return_value = [{"hour": "2026-11-25T08:00:00+00:00", "close": 3000.0}]
        mock_recon.return_value = [{"day": "2026-11-25", "status": "OK"}]
        mock_vol.return_value = [{"trade_date": "2026-11-25", "total_volume": 10.0}]

        pairs_json = self.client.get("/api/pairs/?quote=EUR").json()
        self.assertEqual(pairs_json["pairs"], ["BTC-EUR"])
        self.assertEqual(pairs_json["quote_currencies"], ["USD", "EUR"])

        currencies_json = self.client.get("/api/currencies/").json()
        self.assertTrue(currencies_json["fx_live"])
        self.assertIn("INR", currencies_json["display_currencies"])

        overview_json = self.client.get("/api/overview/?quote=EUR&currency=EUR").json()
        self.assertEqual(overview_json["overview"][0]["product_id"], "BTC-EUR")

        ohlc_json = self.client.get("/api/ohlc/?pair=ETH-USD&currency=EUR").json()
        self.assertEqual(ohlc_json["pair"], "ETH-USD")
        self.assertEqual(ohlc_json["display_currency"], "EUR")
        self.assertEqual(ohlc_json["ohlc"][0]["close"], 3000.0)

        recon_json = self.client.get("/api/reconciliation/?pair=ETH-USD").json()
        self.assertEqual(recon_json["reconciliation"][0]["status"], "OK")

        vol_json = self.client.get("/api/daily-volume/?pair=ETH-USD").json()
        self.assertEqual(vol_json["daily_volume"][0]["total_volume"], 10.0)
