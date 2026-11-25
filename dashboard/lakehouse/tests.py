from unittest.mock import patch

from django.test import Client, SimpleTestCase


class DashboardAndApiTests(SimpleTestCase):
    def setUp(self):
        self.client = Client()

    @patch("lakehouse.views.services.get_pipeline_status")
    @patch("lakehouse.views.services.get_pairs")
    @patch("lakehouse.views.services.get_hourly_ohlc")
    @patch("lakehouse.views.services.get_daily_volume")
    @patch("lakehouse.views.services.get_reconciliation")
    @patch("lakehouse.views.services.get_recent_trades")
    def test_dashboard_renders_with_data(
        self,
        mock_trades,
        mock_recon,
        mock_vol,
        mock_ohlc,
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
        mock_pairs.return_value = ["BTC-USD", "ETH-USD", "SOL-USD"]
        mock_ohlc.return_value = [
            {
                "hour": "2026-11-25T08:00:00+00:00",
                "open": 90000.0,
                "high": 90500.0,
                "low": 89900.0,
                "close": 90400.0,
                "volume": 1.25,
                "trade_count": 40,
            }
        ]
        mock_vol.return_value = [
            {
                "trade_date": "2026-11-25",
                "total_volume": 1.25,
                "total_value_usd": 112500.0,
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
                "price": 90400.0,
                "trade_value_usd": 9040.0,
                "event_time": "2026-11-25T08:30:00+00:00",
            }
        ]

        response = self.client.get("/?pair=BTC-USD")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Crypto Market Data Lakehouse")
        self.assertContains(response, "DIVERGENT")
        self.assertContains(response, "90400.0")

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
    @patch("lakehouse.views.services.get_hourly_ohlc")
    @patch("lakehouse.views.services.get_reconciliation")
    @patch("lakehouse.views.services.get_daily_volume")
    def test_json_endpoints(self, mock_vol, mock_recon, mock_ohlc, mock_pairs):
        mock_pairs.return_value = ["BTC-USD", "ETH-USD"]
        mock_ohlc.return_value = [{"hour": "2026-11-25T08:00:00+00:00", "close": 3000.0}]
        mock_recon.return_value = [{"day": "2026-11-25", "status": "OK"}]
        mock_vol.return_value = [{"trade_date": "2026-11-25", "total_volume": 10.0}]

        self.assertEqual(self.client.get("/api/pairs/").json()["pairs"], ["BTC-USD", "ETH-USD"])
        ohlc_json = self.client.get("/api/ohlc/?pair=ETH-USD").json()
        self.assertEqual(ohlc_json["pair"], "ETH-USD")
        self.assertEqual(ohlc_json["ohlc"][0]["close"], 3000.0)

        recon_json = self.client.get("/api/reconciliation/?pair=ETH-USD").json()
        self.assertEqual(recon_json["reconciliation"][0]["status"], "OK")

        vol_json = self.client.get("/api/daily-volume/?pair=ETH-USD").json()
        self.assertEqual(vol_json["daily_volume"][0]["total_volume"], 10.0)
