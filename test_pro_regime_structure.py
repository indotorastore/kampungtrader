import http.client
import io
import json
import re
import tempfile
import threading
import unittest
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import numpy as np
import pandas as pd

import pro_regime_structure as monitor
from pro_regime_structure import (
    Config,
    calculate_indicators,
    calculate_score,
    analyze_latest,
    build_dashboard_history,
    create_dashboard_server,
    account_snapshot,
    evaluate_structure,
    is_valid_volume,
    is_pivot_high,
    is_pivot_low,
    initialize_signal_journal,
    record_signal,
    run_historical_backtest,
    signal_journal_snapshot,
    update_signal_outcomes,
)


class IndicatorTests(unittest.TestCase):
    def test_gemini_api_key_is_read_from_dotenv_without_changing_other_values(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            env_path = Path(directory) / ".env"
            env_path.write_text(
                "OTHER_SETTING=value\nGEMINI_API_KEY=test-key_123\n",
                encoding="utf-8",
            )
            with patch.dict(monitor.os.environ, {}, clear=False):
                monitor.os.environ.pop("GEMINI_API_KEY", None)
                self.assertEqual(
                    monitor.load_gemini_api_key(env_path),
                    "test-key_123",
                )
            self.assertIn("OTHER_SETTING=value", env_path.read_text(encoding="utf-8"))

    def test_gemini_api_key_environment_variable_overrides_dotenv(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            env_path = Path(directory) / ".env"
            env_path.write_text("GEMINI_API_KEY=from-file\n", encoding="utf-8")
            with patch.dict(monitor.os.environ, {"GEMINI_API_KEY": "from-process"}):
                self.assertEqual(
                    monitor.load_gemini_api_key(env_path),
                    "from-process",
                )

    def test_gemini_model_is_loaded_from_dotenv_and_environment(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            env_path = Path(directory) / ".env"
            env_path.write_text(
                "GEMINI_MODEL='gemini-3.5-flash-lite'\n",
                encoding="utf-8",
            )
            with patch.dict(monitor.os.environ, {}, clear=False):
                monitor.os.environ.pop("GEMINI_MODEL", None)
                self.assertEqual(
                    monitor.load_gemini_model(env_path),
                    "gemini-3.5-flash-lite",
                )
            with patch.dict(
                monitor.os.environ, {"GEMINI_MODEL": "gemini-3.1-flash-lite"}
            ):
                self.assertEqual(
                    monitor.load_gemini_model(env_path),
                    "gemini-3.1-flash-lite",
                )

    def test_gemini_model_rejects_invalid_path_content(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            env_path = Path(directory) / ".env"
            env_path.write_text("GEMINI_MODEL=../other\n", encoding="utf-8")
            with patch.dict(monitor.os.environ, {}, clear=False):
                monitor.os.environ.pop("GEMINI_MODEL", None)
                with self.assertRaisesRegex(ValueError, "Nama model Gemini"):
                    monitor.load_gemini_model(env_path)

    def test_gemini_dotenv_file_is_ignored_by_git(self) -> None:
        gitignore = Path(monitor.__file__).with_name(".gitignore").read_text(
            encoding="utf-8"
        )
        self.assertIn(".env", gitignore.splitlines())

    def test_watch_setup_cannot_be_journaled_or_sized_for_an_order(self) -> None:
        setup = monitor.Setup(
            bar_time=pd.Timestamp("2025-01-01T00:00:00Z"),
            status="WATCH BUY",
            trend="BULLISH",
            structure="BOS bullish",
            score=65,
            buy_score=65,
            sell_score=10,
            rsi=55,
            adx=25,
            band_width_percent=1,
            relative_volume=1.2,
            atr=1,
            spread_points=2,
            macd=0.2,
            macd_signal=0.1,
            stochastic_k=60,
            components={},
            entry=None,
            stop=None,
            target1=None,
            target2=None,
        )
        with tempfile.TemporaryDirectory() as directory:
            journal_path = Path(directory) / "signals.sqlite"
            initialize_signal_journal(journal_path)
            self.assertFalse(record_signal(journal_path, "TEST", "M5", setup, 0.01))
            self.assertEqual(
                signal_journal_snapshot(journal_path, "TEST", "M5")["total_signals"],
                0,
            )

        with patch.object(monitor.mt5, "symbol_info") as symbol_info:
            volume, message = monitor.calculate_risk_based_volume(
                setup, "TEST", 0.25
            )
        self.assertIsNone(volume)
        self.assertIn("tidak valid", message)
        symbol_info.assert_not_called()

    def test_manual_order_uses_explicit_levels_and_enforces_risk(self) -> None:
        symbol_info = SimpleNamespace(
            volume_min=0.01,
            volume_max=10.0,
            volume_step=0.01,
            digits=2,
            filling_mode=0,
        )
        tick = SimpleNamespace(ask=100.1, bid=100.0)
        account = SimpleNamespace(
            equity=10000.0, margin_free=5000.0, trade_allowed=True
        )
        terminal = SimpleNamespace(connected=True, trade_allowed=True)
        with (
            patch.object(monitor.mt5, "symbol_info", return_value=symbol_info),
            patch.object(monitor.mt5, "symbol_info_tick", return_value=tick),
            patch.object(monitor.mt5, "account_info", return_value=account),
            patch.object(monitor.mt5, "terminal_info", return_value=terminal),
            patch.object(monitor.mt5, "positions_get", return_value=()),
            patch.object(monitor.mt5, "orders_get", return_value=()),
            patch.object(monitor.mt5, "order_calc_profit", return_value=-20.0),
            patch.object(monitor.mt5, "order_calc_margin", return_value=100.0),
            patch.object(monitor.mt5, "SYMBOL_FILLING_IOC", 2, create=True),
            patch.object(monitor.mt5, "SYMBOL_FILLING_FOK", 1, create=True),
            patch.object(
                monitor.mt5, "order_check", return_value=SimpleNamespace(retcode=0)
            ),
        ):
            request, detail, risk_percent = monitor.prepare_manual_order(
                "BUY", "TEST", 0.1, 99.0, 102.0, Config(max_risk_percent=1.0), 20
            )
            self.assertIsNotNone(request)
            self.assertEqual(request["type"], monitor.mt5.ORDER_TYPE_BUY)
            self.assertEqual(request["sl"], 99.0)
            self.assertEqual(request["tp"], 102.0)
            self.assertEqual(request["comment"], "AtlasManual")
            self.assertEqual(risk_percent, 0.2)
            self.assertIn("Estimasi rugi SL", detail)

            invalid_request, message, invalid_risk = monitor.prepare_manual_order(
                "BUY", "TEST", 0.1, 101.0, 102.0, Config(), 20
            )
        self.assertIsNone(invalid_request)
        self.assertIn("sisi harga", message)
        self.assertIsNone(invalid_risk)

    def test_dashboard_symbol_endpoint_validates_and_selects_only_allowed_symbol(self) -> None:
        server, state, lock = create_dashboard_server(0)
        state["symbols"] = ["TEST", "OTHER"]
        state["symbol"] = "TEST"
        state["requested_symbol"] = "TEST"
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            host, port = server.server_address
            connection = http.client.HTTPConnection(host, port, timeout=3)
            connection.request("GET", "/")
            page = connection.getresponse()
            token = re.search(
                r'const DASHBOARD_TOKEN = "([^"]+)"',
                page.read().decode("utf-8"),
            ).group(1)
            headers = {
                "Content-Type": "application/json",
                "Origin": f"http://{host}:{port}",
                "X-Dashboard-Token": token,
            }

            with patch.object(monitor.mt5, "symbol_select", return_value=True) as select:
                connection.request(
                    "POST",
                    "/api/symbol",
                    body=json.dumps({"symbol": "OTHER"}),
                    headers=headers,
                )
                response = connection.getresponse()
                self.assertEqual(response.status, 200)
                response.read()
                select.assert_called_once_with("OTHER", True)
            self.assertEqual(state["requested_symbol"], "OTHER")

            connection.request(
                "POST",
                "/api/symbol",
                body=json.dumps({"symbol": "NOT_LISTED"}),
                headers=headers,
            )
            response = connection.getresponse()
            self.assertEqual(response.status, 400)
            response.read()
            self.assertEqual(state["requested_symbol"], "OTHER")

            with lock:
                state["actions_enabled"] = True
                state["status"] = "WATCH BUY"
                state["setup"] = {
                    "status": "WATCH BUY",
                    "bar_time": "2025-01-01T00:00:00Z",
                }
            with patch.object(monitor.mt5, "order_send") as send:
                connection.request(
                    "POST",
                    "/api/order",
                    body=json.dumps({"volume": 0.1, "confirm": "KIRIM"}),
                    headers=headers,
                )
                response = connection.getresponse()
                self.assertEqual(response.status, 409)
                response.read()
                send.assert_not_called()

            with lock:
                state["auto_pilot_enabled"] = True
            with patch.object(monitor.mt5, "symbol_select") as select:
                connection.request(
                    "POST",
                    "/api/symbol",
                    body=json.dumps({"symbol": "TEST"}),
                    headers=headers,
                )
                response = connection.getresponse()
                self.assertEqual(response.status, 409)
                response.read()
                select.assert_not_called()
            connection.close()
        finally:
            server.shutdown()
            server.server_close()

    def test_telegram_settings_keep_token_out_of_status_and_test_sends_only_on_request(self) -> None:
        server, state, lock = create_dashboard_server(0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            host, port = server.server_address
            connection = http.client.HTTPConnection(host, port, timeout=3)
            connection.request("GET", "/")
            page = connection.getresponse()
            html = page.read().decode("utf-8")
            token = re.search(r'const DASHBOARD_TOKEN = "([^"]+)"', html).group(1)
            headers = {
                "Content-Type": "application/json",
                "Origin": f"http://{host}:{port}",
                "X-Dashboard-Token": token,
            }
            bot_token = "123456789:abcdefghijklmnopqrstuvwxyzABCDEFGHI"
            with patch.object(monitor, "save_telegram_settings") as save_settings:
                connection.request(
                    "POST",
                    "/api/telegram-settings",
                    body=json.dumps(
                        {
                            "bot_token": bot_token,
                            "chat_id": "123456789",
                            "enabled": True,
                        }
                    ),
                    headers=headers,
                )
                response = connection.getresponse()
                self.assertEqual(response.status, 200)
                response.read()
                save_settings.assert_called_once_with(
                    bot_token, "123456789", True
                )
            self.assertTrue(state["telegram_enabled"])
            self.assertTrue(state["telegram_configured"])
            self.assertNotIn(bot_token, json.dumps(state))

            with patch.object(
                monitor,
                "send_telegram_message",
                return_value=(True, "Pesan Telegram berhasil dikirim."),
            ) as send_message:
                connection.request(
                    "POST",
                    "/api/telegram-test",
                    body=json.dumps({}),
                    headers=headers,
                )
                response = connection.getresponse()
                self.assertEqual(response.status, 200)
                self.assertTrue(json.loads(response.read())["ok"])
                send_message.assert_called_once_with(
                    bot_token,
                    "123456789",
                    "Tes koneksi Telegram dari Atlas MT5 berhasil.",
                )

            connection.request("GET", "/api/status")
            response = connection.getresponse()
            status_json = response.read().decode("utf-8")
            self.assertEqual(response.status, 200)
            self.assertNotIn(bot_token, status_json)

            with patch.object(monitor, "save_telegram_settings") as save_settings:
                connection.request(
                    "POST",
                    "/api/telegram-settings",
                    body=json.dumps({"enabled": False}),
                    headers=headers,
                )
                response = connection.getresponse()
                self.assertEqual(response.status, 200)
                response.read()
                save_settings.assert_called_once_with(
                    bot_token, "123456789", False
                )
            self.assertFalse(state["telegram_enabled"])
            connection.close()
        finally:
            server.shutdown()
            server.server_close()

    def test_telegram_settings_persist_encrypted_and_reload(self) -> None:
        bot_token = "123456789:abcdefghijklmnopqrstuvwxyzABCDEFGHI"
        chat_id = "123456789"

        def fake_dpapi(payload: bytes, protect: bool) -> bytes:
            if protect:
                return b"encrypted:" + payload[::-1]
            return payload.removeprefix(b"encrypted:")[::-1]

        with tempfile.TemporaryDirectory() as directory:
            settings_path = Path(directory) / "telegram.bin"
            with patch.object(monitor, "_dpapi_crypt", side_effect=fake_dpapi):
                monitor.save_telegram_settings(
                    bot_token, chat_id, True, settings_path
                )
                encrypted = settings_path.read_bytes()
                restored = monitor.load_telegram_settings(settings_path)

        self.assertNotIn(bot_token.encode("utf-8"), encrypted)
        self.assertEqual(
            restored,
            {"bot_token": bot_token, "chat_id": chat_id, "enabled": True},
        )
        with patch.object(monitor, "load_telegram_settings", return_value=restored):
            server, state, _ = create_dashboard_server(0)
        try:
            self.assertTrue(state["telegram_configured"])
            self.assertTrue(state["telegram_enabled"])
            self.assertNotIn(bot_token, json.dumps(state))
        finally:
            server.server_close()

    @unittest.skipUnless(monitor.os.name == "nt", "Windows DPAPI is only available on Windows")
    def test_telegram_settings_use_windows_dpapi_encryption(self) -> None:
        bot_token = "123456789:abcdefghijklmnopqrstuvwxyzABCDEFGHI"
        with tempfile.TemporaryDirectory() as directory:
            settings_path = Path(directory) / "telegram.bin"
            monitor.save_telegram_settings(
                bot_token, "123456789", True, settings_path
            )
            encrypted = settings_path.read_bytes()
            restored = monitor.load_telegram_settings(settings_path)

        self.assertNotIn(bot_token.encode("utf-8"), encrypted)
        self.assertEqual(restored["bot_token"], bot_token)
        self.assertTrue(restored["enabled"])

    def test_telegram_sender_posts_json_and_handles_api_rejection(self) -> None:
        response = io.BytesIO(b'{"ok": true}')
        with patch.object(monitor.urllib.request, "urlopen", return_value=response) as urlopen:
            sent, message = monitor.send_telegram_message(
                "123456:secret-token", "123", "Atlas test"
            )

        self.assertTrue(sent)
        self.assertIn("berhasil", message)
        request = urlopen.call_args.args[0]
        self.assertEqual(request.full_url, "https://api.telegram.org/bot123456:secret-token/sendMessage")
        self.assertEqual(
            json.loads(request.data.decode("utf-8")),
            {"chat_id": "123", "text": "Atlas test"},
        )

        rejected = io.BytesIO(b'{"ok": false, "error_code": 401}')
        with patch.object(monitor.urllib.request, "urlopen", return_value=rejected):
            sent, message = monitor.send_telegram_message(
                "123456:secret-token", "123", "Atlas test"
            )
        self.assertFalse(sent)
        self.assertIn("401", message)

    def test_free_economic_calendar_filters_and_normalizes_events(self) -> None:
        now = datetime(2026, 10, 22, 12, tzinfo=monitor.timezone.utc)
        feed = [
            {
                "title": "Old release",
                "country": "USD",
                "date": "2026-10-20T12:00:00-04:00",
                "impact": "High",
            },
            {
                "title": "CPI y/y",
                "country": "USD",
                "date": "2026-10-22T10:00:00-04:00",
                "impact": "High",
                "forecast": "2.4%",
                "previous": "2.5%",
            },
        ]
        response = io.BytesIO(json.dumps(feed).encode("utf-8"))
        with patch.object(monitor.urllib.request, "urlopen", return_value=response):
            events = monitor.fetch_economic_calendar(now)

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["title"], "CPI y/y")
        self.assertEqual(events[0]["country"], "USD")
        self.assertEqual(events[0]["date"], "2026-10-22T14:00:00+00:00")
        self.assertEqual(events[0]["forecast"], "2.4%")

    def test_fred_series_parser_returns_latest_change_and_cpi_yoy(self) -> None:
        dates = pd.date_range("2025-09-01", periods=13, freq="MS")
        cpi_rows = ["observation_date,CPIAUCSL"] + [
            f"{date:%Y-%m-%d},{100 + index}"
            for index, date in enumerate(dates)
        ]
        series_by_url = {
            "DGS10": b"observation_date,DGS10\n2026-10-20,4.00\n2026-10-21,4.15\n",
            "CPIAUCSL": ("\n".join(cpi_rows) + "\n").encode("utf-8"),
        }

        def fake_urlopen(request: Any, timeout: int) -> io.BytesIO:
            series_id = request.full_url.split("id=")[1].split("&")[0]
            return io.BytesIO(series_by_url[series_id])

        current_time = datetime(2026, 10, 22, tzinfo=monitor.timezone.utc)
        with patch.object(
            monitor.urllib.request, "urlopen", side_effect=fake_urlopen
        ):
            treasury = monitor._fetch_fred_series(
                next(series for series in monitor.MACRO_SERIES if series["id"] == "DGS10"),
                current_time,
            )
            cpi = monitor._fetch_fred_series(
                next(series for series in monitor.MACRO_SERIES if series["id"] == "CPIAUCSL"),
                current_time,
            )

        self.assertEqual(treasury["value"], 4.15)
        self.assertAlmostEqual(treasury["change"], 0.15)
        self.assertEqual(treasury["observation_date"], "2026-10-21")
        self.assertEqual(cpi["value"], 112.0)
        self.assertAlmostEqual(cpi["inflation_yoy_percent"], 12.0)
        self.assertEqual(cpi["inflation_yoy_base_date"], "2025-09-01")

    def test_macro_indicator_fetch_returns_partial_data_and_source_errors(self) -> None:
        def fetch_series(series: dict[str, Any], now: datetime) -> dict[str, str]:
            if series["id"] == "UNRATE":
                raise RuntimeError("test source unavailable")
            return {"id": series["id"], "label": series["label"]}

        with patch.object(monitor, "_fetch_fred_series", side_effect=fetch_series):
            result = monitor.fetch_macro_indicators(
                datetime(2026, 10, 22, tzinfo=monitor.timezone.utc)
            )

        self.assertEqual(len(result["indicators"]), len(monitor.MACRO_SERIES) - 1)
        self.assertEqual(result["errors"], [{"id": "UNRATE", "message": "test source unavailable"}])
        self.assertEqual(
            result["source_url"],
            "https://fred.stlouisfed.org/",
        )

    def test_gemini_analysis_sends_context_with_api_key_header(self) -> None:
        response_payload = json.dumps(
            {
                "candidates": [
                    {
                        "content": {
                            "parts": [{"text": "Bias makro netral; tunggu data aktual."}]
                        }
                    }
                ]
            }
        ).encode("utf-8")
        response = io.BytesIO(
            response_payload
        )
        event = {
            "title": "CPI y/y",
            "country": "USD",
            "date": "2026-10-22T14:00:00+00:00",
            "impact": "High",
            "actual": "",
            "forecast": "2.4%",
            "previous": "2.5%",
        }
        with patch.object(
            monitor.urllib.request, "urlopen", return_value=response
        ) as urlopen:
            analysis = monitor.analyze_macro_with_gemini(
                "gemini-secret",
                {"symbol": "GBPUSD.m", "timeframe": "M5"},
                [event],
            )

        request = urlopen.call_args.args[0]
        self.assertEqual(analysis, "Bias makro netral; tunggu data aktual.")
        self.assertEqual(
            request.full_url,
            f"{monitor.GEMINI_API_BASE_URL}{monitor.DEFAULT_GEMINI_MODEL}:generateContent",
        )
        self.assertEqual(request.get_header("X-goog-api-key"), "gemini-secret")
        self.assertNotIn("gemini-secret", request.data.decode("utf-8"))
        prompt = json.loads(request.data.decode("utf-8"))["contents"][0]["parts"][0]["text"]
        self.assertIn("GBPUSD.m", prompt)
        self.assertIn("CPI y/y", prompt)
        self.assertIn("Jangan menjanjikan profit", prompt)
        self.assertIn("Markdown standar", prompt)
        self.assertIn("## Ringkasan", prompt)
        macro_data = {
            "source": "FRED",
            "indicators": [{"id": "DGS10", "value": 4.15}],
        }
        with patch.object(
            monitor.urllib.request,
            "urlopen",
            return_value=io.BytesIO(response_payload),
        ) as urlopen:
            monitor.analyze_macro_with_gemini(
                "gemini-secret",
                {"symbol": "GBPUSD.m"},
                [event],
                macro_data=macro_data,
            )
        prompt = json.loads(urlopen.call_args.args[0].data.decode("utf-8"))["contents"][0]["parts"][0]["text"]
        self.assertIn('"official_macro_data": {"source": "FRED"', prompt)
        self.assertIn('"id": "DGS10"', prompt)

    def test_gemini_http_error_explains_provider_reason_without_leaking_key(self) -> None:
        api_key = "private-gemini-key"
        body = json.dumps(
            {
                "error": {
                    "code": 403,
                    "status": "PERMISSION_DENIED",
                    "message": f"API key {api_key} has insufficient permissions.",
                }
            }
        ).encode("utf-8")
        error = monitor.urllib.error.HTTPError(
            monitor.GEMINI_API_BASE_URL,
            403,
            "Forbidden",
            {},
            io.BytesIO(body),
        )
        with patch.object(monitor.urllib.request, "urlopen", side_effect=error):
            with self.assertRaises(RuntimeError) as raised:
                monitor.analyze_macro_with_gemini(
                    api_key,
                    {"symbol": "GBPUSD"},
                    [],
                    "gemini-3.5-flash-lite",
                )

        self.assertIn("HTTP 403", str(raised.exception))
        self.assertIn("PERMISSION_DENIED", str(raised.exception))
        self.assertIn("[redacted]", str(raised.exception))
        self.assertNotIn(api_key, str(raised.exception))

    def test_strategy_modes_use_distinct_presets_and_journal_scopes(self) -> None:
        trend = Config()
        scalping = monitor.config_for_mode(trend, "scalping")

        self.assertEqual((trend.fast_ema_period, trend.slow_ema_period), (50, 200))
        self.assertEqual((scalping.fast_ema_period, scalping.slow_ema_period), (9, 21))
        self.assertEqual(scalping.rsi_period, 9)
        self.assertEqual(scalping.target2_risk_reward, 1.2)
        self.assertEqual(scalping.swing_strength, 2)
        self.assertEqual(scalping.structure_lookback, 60)
        self.assertTrue(scalping.allow_rsi_momentum_pullback)
        self.assertFalse(trend.allow_rsi_momentum_pullback)
        self.assertEqual(monitor.journal_timeframe_scope("M5", "trend"), "M5")
        self.assertEqual(
            monitor.journal_timeframe_scope("M5", "scalping"), "M5:scalping"
        )
        with self.assertRaises(ValueError):
            monitor.config_for_mode(trend, "unknown")

    def test_scalping_pullback_accepts_continuation_not_only_rsi_midline_cross(self) -> None:
        self.assertTrue(
            monitor.pullback_momentum_valid(True, 58, 54, 101, 100)
        )
        self.assertTrue(
            monitor.pullback_momentum_valid(False, 43, 47, 99, 100)
        )
        self.assertFalse(
            monitor.pullback_momentum_valid(True, 58, 59, 101, 100)
        )
        self.assertFalse(
            monitor.pullback_momentum_valid(True, 48, 47, 101, 100)
        )
        self.assertFalse(
            monitor.pullback_momentum_valid(False, 55, 56, 99, 100)
        )

    def test_auto_pilot_sizes_volume_down_to_risk_and_refuses_broker_minimum_overrisk(self) -> None:
        setup = monitor.Setup(
            bar_time=pd.Timestamp("2025-01-01T00:00:00Z"),
            status="BUY",
            trend="BULLISH MTF",
            structure="BOS bullish",
            score=80,
            buy_score=80,
            sell_score=0,
            rsi=55,
            adx=25,
            band_width_percent=1,
            relative_volume=1.5,
            atr=1,
            spread_points=2,
            macd=0.2,
            macd_signal=0.1,
            stochastic_k=60,
            components={},
            entry=100,
            stop=99,
            target1=101,
            target2=102,
        )
        symbol_info = SimpleNamespace(
            volume_min=0.01,
            volume_max=100.0,
            volume_step=0.01,
        )
        account = SimpleNamespace(equity=10000.0)
        with (
            patch.object(monitor.mt5, "symbol_info", return_value=symbol_info),
            patch.object(
                monitor.mt5,
                "symbol_info_tick",
                return_value=SimpleNamespace(ask=100.1, bid=100.0),
            ),
            patch.object(monitor.mt5, "account_info", return_value=account),
            patch.object(monitor.mt5, "order_calc_profit", return_value=-100.0),
        ):
            volume, message = monitor.calculate_risk_based_volume(
                setup, "TEST", 0.25
            )
            smallest_volume, smallest_message = monitor.calculate_risk_based_volume(
                setup, "TEST", 0.005
            )

        self.assertEqual(volume, 0.25)
        self.assertIn("risiko target 0.25%", message)
        self.assertIsNone(smallest_volume)
        self.assertIn("Lot minimum broker", smallest_message)

    def test_daily_risk_snapshot_includes_closed_deal_costs_and_floating_loss(self) -> None:
        account = SimpleNamespace(balance=9900.0, equity=9800.0)
        deals = (
            SimpleNamespace(profit=-90.0, commission=-5.0, swap=-5.0, fee=0.0),
        )
        with (
            patch.object(monitor.mt5, "account_info", return_value=account),
            patch.object(monitor.mt5, "history_deals_get", return_value=deals),
        ):
            snapshot = monitor.daily_risk_snapshot(
                datetime(2025, 1, 2, 12, tzinfo=monitor.timezone.utc)
            )

        self.assertEqual(snapshot["date_utc"], "2025-01-02")
        self.assertEqual(snapshot["start_equity"], 10000.0)
        self.assertEqual(snapshot["loss_amount"], 200.0)
        self.assertEqual(snapshot["loss_percent"], 2.0)

    def test_daily_risk_snapshot_fails_closed_when_deal_history_unavailable(self) -> None:
        with (
            patch.object(
                monitor.mt5,
                "account_info",
                return_value=SimpleNamespace(balance=10000.0, equity=10000.0),
            ),
            patch.object(monitor.mt5, "history_deals_get", return_value=None),
            patch.object(monitor.mt5, "last_error", return_value=(-1, "history unavailable")),
        ):
            with self.assertRaisesRegex(RuntimeError, "riwayat transaksi"):
                monitor.daily_risk_snapshot(
                    datetime(2025, 1, 2, 12, tzinfo=monitor.timezone.utc)
                )

    def test_auto_pilot_sends_only_after_risk_and_daily_checks(self) -> None:
        setup = monitor.Setup(
            bar_time=pd.Timestamp("2025-01-01T00:00:00Z"),
            status="BUY",
            trend="BULLISH MTF",
            structure="BOS bullish",
            score=80,
            buy_score=80,
            sell_score=0,
            rsi=55,
            adx=25,
            band_width_percent=1,
            relative_volume=1.5,
            atr=1,
            spread_points=2,
            macd=0.2,
            macd_signal=0.1,
            stochastic_k=60,
            components={},
            entry=100,
            stop=99,
            target1=101,
            target2=102,
        )
        terminal = SimpleNamespace(connected=True, trade_allowed=True)
        account = SimpleNamespace(
            trade_allowed=True,
            trade_mode=monitor.mt5.ACCOUNT_TRADE_MODE_DEMO,
        )
        order_result = SimpleNamespace(
            retcode=monitor.mt5.TRADE_RETCODE_DONE,
            order=321,
        )
        with (
            patch.object(
                monitor,
                "daily_risk_snapshot",
                return_value={"loss_percent": 0.25, "date_utc": "2025-01-01"},
            ),
            patch.object(monitor.mt5, "terminal_info", return_value=terminal),
            patch.object(monitor.mt5, "account_info", return_value=account),
            patch.object(monitor.mt5, "positions_get", return_value=()),
            patch.object(monitor.mt5, "orders_get", return_value=()),
            patch.object(
                monitor,
                "calculate_risk_based_volume",
                return_value=(0.1, "lot ok"),
            ),
            patch.object(
                monitor,
                "prepare_signal_order",
                return_value=({"action": "deal"}, "risk ok", 0.2),
            ),
            patch.object(monitor.mt5, "order_send", return_value=order_result) as send,
        ):
            sent, message, risk = monitor.execute_auto_pilot_order(
                setup, "TEST", Config(), 20, 0.25, 1.0, "2025-01-01"
            )
            self.assertTrue(sent)
            self.assertIn("ticket 321", message)
            self.assertEqual(risk, 0.2)
            send.assert_called_once_with({"action": "deal"})

            monitor.daily_risk_snapshot.return_value = {
                "loss_percent": 1.0,
                "date_utc": "2025-01-01",
            }
            sent, message, risk = monitor.execute_auto_pilot_order(
                setup, "TEST", Config(), 20, 0.25, 1.0, "2025-01-01"
            )
            self.assertFalse(sent)
            self.assertIn("Batas rugi harian", message)
            self.assertIsNone(risk)
            send.assert_called_once()

            monitor.daily_risk_snapshot.return_value = {
                "loss_percent": 0.0,
                "date_utc": "2025-01-02",
            }
            sent, message, risk = monitor.execute_auto_pilot_order(
                setup, "TEST", Config(), 20, 0.25, 1.0, "2025-01-01"
            )
            self.assertFalse(sent)
            self.assertIn("Hari UTC berganti", message)
            self.assertIsNone(risk)
            send.assert_called_once()

    def test_dashboard_auto_pilot_requires_explicit_confirmation_and_blocks_settings(self) -> None:
        server, state, lock = create_dashboard_server(
            0,
            auto_pilot_available=True,
            auto_risk_percent=0.25,
            daily_loss_limit_percent=1.0,
        )
        state["symbol"] = "TEST"
        state["account"] = {
            "connected": True,
            "trade_allowed": True,
            "trade_mode": "DEMO",
        }
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            host, port = server.server_address
            connection = http.client.HTTPConnection(host, port, timeout=3)
            connection.request("GET", "/")
            page = connection.getresponse()
            html = page.read().decode("utf-8")
            token = re.search(r'const DASHBOARD_TOKEN = "([^"]+)"', html).group(1)
            self.assertIn("Settings Auto Pilot", html)
            self.assertIn('id="auto-risk-setting"', html)
            self.assertIn('id="daily-loss-setting"', html)

            headers = {
                "Content-Type": "application/json",
                "Origin": f"http://{host}:{port}",
                "X-Dashboard-Token": token,
            }
            connection.request(
                "POST",
                "/api/auto-pilot-settings",
                body=json.dumps(
                    {"auto_risk_percent": 0.5, "daily_loss_limit_percent": 2.0}
                ),
                headers=headers,
            )
            response = connection.getresponse()
            self.assertEqual(response.status, 200)
            response.read()
            self.assertEqual(state["auto_risk_percent"], 0.5)
            self.assertEqual(state["daily_loss_limit_percent"], 2.0)

            connection.request(
                "POST",
                "/api/auto-pilot-settings",
                body=json.dumps(
                    {"auto_risk_percent": 10.01, "daily_loss_limit_percent": 2.0}
                ),
                headers=headers,
            )
            response = connection.getresponse()
            self.assertEqual(response.status, 400)
            response.read()
            self.assertEqual(state["auto_risk_percent"], 0.5)

            with (
                patch.object(
                    monitor,
                    "account_snapshot",
                    return_value={
                        "connected": True,
                        "trade_allowed": True,
                        "trade_mode": "DEMO",
                        "positions": [],
                        "pending_orders": 0,
                        "login": "123",
                        "server": "Demo-Server",
                    },
                ),
                patch.object(
                    monitor,
                    "daily_risk_snapshot",
                    return_value={"loss_percent": 0.0, "date_utc": "2025-01-02"},
                ),
                patch.object(monitor.mt5, "orders_get", return_value=()),
            ):
                connection.request(
                    "POST",
                    "/api/auto-pilot",
                    body=json.dumps({"enabled": True, "confirm": "wrong"}),
                    headers=headers,
                )
                response = connection.getresponse()
                self.assertEqual(response.status, 400)
                response.read()
                self.assertFalse(state["auto_pilot_enabled"])

                connection.request(
                    "POST",
                    "/api/auto-pilot",
                    body=json.dumps(
                        {"enabled": True, "confirm": "AKTIFKAN AUTO PILOT"}
                    ),
                    headers=headers,
                )
                response = connection.getresponse()
                self.assertEqual(response.status, 200)
                self.assertTrue(json.loads(response.read())["ok"])
                self.assertTrue(state["auto_pilot_enabled"])

                connection.request(
                    "POST",
                    "/api/auto-pilot-settings",
                    body=json.dumps(
                        {"auto_risk_percent": 1.0, "daily_loss_limit_percent": 3.0}
                    ),
                    headers=headers,
                )
                response = connection.getresponse()
                self.assertEqual(response.status, 409)
                response.read()
                self.assertEqual(state["auto_risk_percent"], 0.5)

            connection.request(
                "POST",
                "/api/chart-settings",
                body=json.dumps(
                    {"timeframe": "M5", "higher_timeframe": "H1"}
                ),
                headers=headers,
            )
            response = connection.getresponse()
            self.assertEqual(response.status, 409)
            response.read()

            connection.request(
                "POST",
                "/api/auto-pilot",
                body=json.dumps({"enabled": False}),
                headers=headers,
            )
            response = connection.getresponse()
            self.assertEqual(response.status, 200)
            self.assertFalse(state["auto_pilot_enabled"])

            connection.request(
                "POST",
                "/api/auto-pilot-settings",
                body=json.dumps(
                    {"auto_risk_percent": 10.0, "daily_loss_limit_percent": 10.0}
                ),
                headers=headers,
            )
            response = connection.getresponse()
            self.assertEqual(response.status, 200)
            response.read()
            self.assertEqual(state["auto_risk_percent"], 10.0)
            self.assertEqual(state["daily_loss_limit_percent"], 10.0)
            connection.close()
        finally:
            server.shutdown()
            server.server_close()

    def test_account_snapshot_exposes_financial_summary_without_order_data(self) -> None:
        account = SimpleNamespace(
            login=123456,
            server="Demo-Server",
            currency="USD",
            trade_mode=monitor.mt5.ACCOUNT_TRADE_MODE_DEMO,
            leverage=100,
            balance=10000.0,
            equity=10100.0,
            profit=100.0,
            margin=500.0,
            margin_free=9600.0,
            margin_level=2020.0,
            trade_allowed=True,
        )
        terminal = SimpleNamespace(connected=True, trade_allowed=True)
        with (
            patch.object(monitor.mt5, "account_info", return_value=account),
            patch.object(monitor.mt5, "terminal_info", return_value=terminal),
            patch.object(monitor.mt5, "positions_get", return_value=()),
            patch.object(monitor.mt5, "orders_get", return_value=()),
        ):
            result = account_snapshot()

        self.assertTrue(result["connected"])
        self.assertEqual(result["trade_mode"], "DEMO")
        self.assertEqual(result["balance"], 10000.0)
        self.assertEqual(result["pending_orders"], 0)
        self.assertEqual(result["positions"], [])

    def test_local_dashboard_serves_page_and_json_status(self) -> None:
        server, state, lock = create_dashboard_server(0)
        state["status"] = "NO TRADE"
        state["symbol"] = "TEST"
        with lock:
            state["setup"] = {"score": 70}
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            host, port = server.server_address
            connection = http.client.HTTPConnection(host, port, timeout=3)
            connection.request("GET", "/")
            page = connection.getresponse()
            self.assertEqual(page.status, 200)
            html = page.read().decode("utf-8")
            self.assertIn("ATLAS", html)
            self.assertIn("Analisis Mandiri", html)
            self.assertIn("Jurnal & hasil sinyal", html)
            self.assertIn("Backtest historis", html)
            self.assertIn("Open order manual · di luar aturan sinyal", html)
            self.assertIn("BUY sinyal", html)
            self.assertIn("SELL sinyal", html)
            self.assertIn('value="3000"', html)
            self.assertIn('id="strategy-mode"', html)
            self.assertIn('id="autopilot-toggle"', html)
            self.assertIn("Belum ada trade yang memenuhi setup", html)
            self.assertNotIn("__DASHBOARD_TOKEN__", html)
            token = re.search(r'const DASHBOARD_TOKEN = "([^"]+)"', html).group(1)

            connection.request("GET", "/api/status")
            response = connection.getresponse()
            payload = json.loads(response.read())
            self.assertEqual(response.status, 200)
            self.assertEqual(payload["status"], "NO TRADE")
            self.assertEqual(payload["symbol"], "TEST")
            self.assertEqual(payload["setup"]["score"], 70)
            self.assertEqual(payload["journal"]["total_signals"], 0)
            self.assertFalse(payload["actions_enabled"])
            connection.close()

            connection = http.client.HTTPConnection(host, port, timeout=3)
            connection.request("GET", "/analyst")
            analyst_page = connection.getresponse()
            analyst_html = analyst_page.read().decode("utf-8")
            self.assertEqual(analyst_page.status, 200)
            self.assertIn("Kalender ekonomi", analyst_html)
            self.assertIn("Insight makro", analyst_html)
            self.assertNotIn("pipeline-step", analyst_html)
            self.assertNotIn("AI belum aktif", analyst_html)
            self.assertIn("Sinyal teknikal Atlas · bukan AI", analyst_html)
            self.assertLess(
                analyst_html.index("Tahap 1 · pengumpulan data makro"),
                analyst_html.index("Terminal realtime"),
            )
            connection.close()

            with patch.object(
                monitor,
                "fetch_economic_calendar",
                return_value=[
                    {
                        "title": "CPI",
                        "country": "USD",
                        "date": "2026-10-22T12:00:00+00:00",
                        "impact": "High",
                        "actual": "",
                        "forecast": "2.0%",
                        "previous": "2.1%",
                    }
                ],
            ) as fetch_calendar:
                connection = http.client.HTTPConnection(host, port, timeout=3)
                connection.request("GET", "/api/macro-calendar")
                macro_response = connection.getresponse()
                macro_payload = json.loads(macro_response.read())
                self.assertEqual(macro_response.status, 200)
                self.assertEqual(macro_payload["events"][0]["title"], "CPI")
                connection.request("GET", "/api/macro-calendar")
                cached_response = connection.getresponse()
                cached_response.read()
                self.assertEqual(cached_response.status, 200)
                fetch_calendar.assert_called_once()
                connection.close()

            macro_data = {
                "source": "FRED",
                "source_url": "https://fred.stlouisfed.org/",
                "updated_at": "2026-10-22T12:00:00+00:00",
                "indicators": [{"id": "DGS10", "value": 4.15}],
                "errors": [],
            }
            with patch.object(
                monitor,
                "fetch_macro_indicators",
                return_value=macro_data,
            ) as fetch_macro_data:
                connection = http.client.HTTPConnection(host, port, timeout=3)
                connection.request("GET", "/api/macro-data")
                macro_response = connection.getresponse()
                macro_payload = json.loads(macro_response.read())
                self.assertEqual(macro_response.status, 200)
                self.assertEqual(
                    macro_payload["indicators"][0]["id"],
                    "DGS10",
                )
                connection.request("GET", "/api/macro-data")
                cached_response = connection.getresponse()
                cached_response.read()
                self.assertEqual(cached_response.status, 200)
                fetch_macro_data.assert_called_once()
                connection.close()

            connection = http.client.HTTPConnection(host, port, timeout=3)
            connection.request(
                "POST",
                "/api/chart-settings",
                body=json.dumps(
                    {"timeframe": "M15", "higher_timeframe": "H4"}
                ),
                headers={
                    "Content-Type": "application/json",
                    "Origin": f"http://{host}:{port}",
                    "X-Dashboard-Token": token,
                },
            )
            response = connection.getresponse()
            self.assertEqual(response.status, 200)
            self.assertEqual(state["requested_timeframe"], "M15")
            self.assertEqual(state["requested_higher_timeframe"], "H4")
            connection.close()

            connection = http.client.HTTPConnection(host, port, timeout=3)
            connection.request(
                "POST",
                "/api/strategy-mode",
                body=json.dumps({"mode": "scalping"}),
                headers={
                    "Content-Type": "application/json",
                    "Origin": f"http://{host}:{port}",
                    "X-Dashboard-Token": token,
                },
            )
            response = connection.getresponse()
            self.assertEqual(response.status, 200)
            self.assertEqual(state["requested_strategy_mode"], "scalping")
            connection.close()

            connection = http.client.HTTPConnection(host, port, timeout=3)
            connection.request(
                "POST",
                "/api/strategy-mode",
                body=json.dumps({"mode": "invalid"}),
                headers={
                    "Content-Type": "application/json",
                    "Origin": f"http://{host}:{port}",
                    "X-Dashboard-Token": token,
                },
            )
            response = connection.getresponse()
            self.assertEqual(response.status, 400)
            connection.close()

            connection = http.client.HTTPConnection(host, port, timeout=3)
            connection.request(
                "POST",
                "/api/backtest",
                body=json.dumps(
                    {
                        "bars": 500,
                        "commission_points": 1.5,
                        "slippage_points": 0.4,
                    }
                ),
                headers={
                    "Content-Type": "application/json",
                    "Origin": f"http://{host}:{port}",
                    "X-Dashboard-Token": token,
                },
            )
            response = connection.getresponse()
            self.assertEqual(response.status, 202)
            self.assertEqual(
                state["backtest_request"],
                {
                    "bars": 500,
                    "commission_points": 1.5,
                    "slippage_points": 0.4,
                    "strategy_mode": "scalping",
                },
            )
            self.assertEqual(state["backtest"]["status"], "queued")
            connection.close()

            connection = http.client.HTTPConnection(host, port, timeout=3)
            connection.request(
                "POST",
                "/api/strategy-mode",
                body=json.dumps({"mode": "trend"}),
                headers={
                    "Content-Type": "application/json",
                    "Origin": f"http://{host}:{port}",
                    "X-Dashboard-Token": token,
                },
            )
            response = connection.getresponse()
            self.assertEqual(response.status, 409)
            self.assertEqual(state["requested_strategy_mode"], "scalping")
            connection.close()

            connection = http.client.HTTPConnection(host, port, timeout=3)
            connection.request(
                "POST",
                "/api/backtest",
                body=json.dumps({"bars": 299}),
                headers={
                    "Content-Type": "application/json",
                    "Origin": f"http://{host}:{port}",
                    "X-Dashboard-Token": token,
                },
            )
            response = connection.getresponse()
            self.assertEqual(response.status, 400)
            connection.close()

            connection = http.client.HTTPConnection(host, port, timeout=3)
            connection.request(
                "POST",
                "/api/backtest",
                body=json.dumps(
                    {"bars": 500, "commission_points": -1, "slippage_points": 0}
                ),
                headers={
                    "Content-Type": "application/json",
                    "Origin": f"http://{host}:{port}",
                    "X-Dashboard-Token": token,
                },
            )
            response = connection.getresponse()
            self.assertEqual(response.status, 400)
            connection.close()

            connection = http.client.HTTPConnection(host, port, timeout=3)
            connection.request(
                "POST",
                "/api/chart-settings",
                body=json.dumps(
                    {"timeframe": "H1", "higher_timeframe": "M15"}
                ),
                headers={
                    "Content-Type": "application/json",
                    "Origin": f"http://{host}:{port}",
                    "X-Dashboard-Token": token,
                },
            )
            response = connection.getresponse()
            self.assertEqual(response.status, 400)
            connection.close()

            connection = http.client.HTTPConnection(host, port, timeout=3)
            connection.request(
                "POST",
                "/api/order",
                body=json.dumps({"confirm": "KIRIM", "volume": 0.01}),
                headers={
                    "Content-Type": "application/json",
                    "Origin": f"http://{host}:{port}",
                },
            )
            response = connection.getresponse()
            payload = json.loads(response.read())
            self.assertEqual(response.status, 403)
            self.assertFalse(payload["ok"])
            connection.close()

            connection = http.client.HTTPConnection(host, port, timeout=3)
            connection.request(
                "POST",
                "/api/order",
                body=json.dumps({"confirm": "KIRIM", "volume": 0.01}),
                headers={
                    "Content-Type": "application/json",
                    "Origin": f"http://{host}:{port}",
                    "X-Dashboard-Token": token,
                },
            )
            response = connection.getresponse()
            payload = json.loads(response.read())
            self.assertEqual(response.status, 403)
            self.assertIn("dinonaktifkan", payload["message"])
            connection.close()
        finally:
            server.shutdown()
            server.server_close()

    def test_manual_order_endpoint_accepts_explicit_direction_without_signal(self) -> None:
        server, state, lock = create_dashboard_server(0)
        with lock:
            state["actions_enabled"] = True
            state["symbol"] = "TEST"
            state["status"] = "NO TRADE"
            state["setup"] = None
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            host, port = server.server_address
            connection = http.client.HTTPConnection(host, port, timeout=3)
            connection.request("GET", "/")
            page = connection.getresponse()
            token = re.search(
                r'const DASHBOARD_TOKEN = "([^"]+)"',
                page.read().decode("utf-8"),
            ).group(1)
            headers = {
                "Content-Type": "application/json",
                "Origin": f"http://{host}:{port}",
                "X-Dashboard-Token": token,
            }
            body = {
                "direction": "BUY",
                "volume": 0.1,
                "stop": 99.0,
                "target": 102.0,
                "confirm": "KIRIM MANUAL BUY",
            }
            result = SimpleNamespace(
                retcode=monitor.mt5.TRADE_RETCODE_DONE,
                order=123,
                deal=456,
                comment="done",
            )
            with (
                patch.object(monitor, "get_spread_points", return_value=1),
                patch.object(
                    monitor,
                    "prepare_manual_order",
                    return_value=({"action": "deal"}, "risk ok", 0.2),
                ) as prepare,
                patch.object(monitor.mt5, "order_send", return_value=result) as send,
            ):
                connection.request(
                    "POST",
                    "/api/manual-order",
                    body=json.dumps(body),
                    headers=headers,
                )
                response = connection.getresponse()
                payload = json.loads(response.read())
                self.assertEqual(response.status, 200)
                self.assertIn("Order manual BUY diterima", payload["message"])
                self.assertEqual(state["status"], "NO TRADE")
                self.assertIn("Order manual BUY diterima", state["last_action"])
                prepare.assert_called_once_with(
                    "BUY", "TEST", 0.1, 99.0, 102.0, Config(), 20
                )
                send.assert_called_once_with({"action": "deal"})

                with lock:
                    state["auto_pilot_enabled"] = True
                connection.request(
                    "POST",
                    "/api/manual-order",
                    body=json.dumps(body),
                    headers=headers,
                )
                response = connection.getresponse()
                payload = json.loads(response.read())
                self.assertEqual(response.status, 409)
                self.assertIn("Matikan Auto Pilot", payload["message"])
                send.assert_called_once()
            connection.close()
        finally:
            server.shutdown()
            server.server_close()

    def test_gemini_macro_analysis_is_manual_and_key_is_private(self) -> None:
        with (
            patch.object(
                monitor,
                "load_gemini_api_key",
                return_value="secret-gemini-key",
            ),
            patch.object(
                monitor,
                "load_gemini_model",
                return_value="gemini-3.5-flash-lite",
            ),
        ):
            server, state, lock = create_dashboard_server(0)
        state["symbol"] = "GBPUSD.m"
        state["timeframe"] = "M5"
        state["higher_timeframe"] = "M15"
        state["strategy_mode"] = "scalping"
        state["status"] = "NO TRADE"
        state["market"] = {"bid": 1.25, "ask": 1.2502, "spread_points": 2}
        state["setup"] = {"score": 68, "rsi": 53.0}
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            host, port = server.server_address
            connection = http.client.HTTPConnection(host, port, timeout=3)
            connection.request("GET", "/analyst")
            page = connection.getresponse()
            analyst_html = page.read().decode("utf-8")
            token = re.search(
                r'const DASHBOARD_TOKEN = "([^"]+)"', analyst_html
            ).group(1)
            self.assertEqual(page.status, 200)
            self.assertNotIn("__DASHBOARD_TOKEN__", analyst_html)
            headers = {
                "Content-Type": "application/json",
                "Origin": f"http://{host}:{port}",
                "X-Dashboard-Token": token,
            }

            self.assertTrue(state["macro_ai_configured"])

            connection.request("GET", "/api/status")
            status_response = connection.getresponse()
            status_json = status_response.read().decode("utf-8")
            self.assertNotIn("secret-gemini-key", status_json)

            events = [
                {
                    "title": "UK CPI",
                    "country": "GBP",
                    "date": "2026-10-22T12:00:00+00:00",
                    "impact": "High",
                    "actual": "2.2%",
                    "forecast": "2.3%",
                    "previous": "2.4%",
                },
                {
                    "title": "US CPI",
                    "country": "USD",
                    "date": "2026-10-22T13:00:00+00:00",
                    "impact": "High",
                    "actual": "",
                    "forecast": "2.0%",
                    "previous": "2.1%",
                },
                {
                    "title": "Euro CPI",
                    "country": "EUR",
                    "date": "2026-10-22T14:00:00+00:00",
                    "impact": "High",
                    "actual": "",
                    "forecast": "2.0%",
                    "previous": "2.1%",
                },
            ]
            with patch.object(
                monitor, "fetch_economic_calendar", return_value=events
            ), patch.object(
                monitor,
                "fetch_macro_indicators",
                return_value={
                    "source": "FRED",
                    "indicators": [{"id": "DGS10", "value": 4.15}],
                    "errors": [],
                },
            ), patch.object(
                monitor,
                "analyze_macro_with_gemini",
                return_value="Bias GBP netral; tunggu konfirmasi.",
            ) as analyze:
                connection.request(
                    "POST", "/api/macro-analysis", body="{}", headers=headers
                )
                analysis_response = connection.getresponse()
                analysis_payload = json.loads(analysis_response.read())
            self.assertEqual(analysis_response.status, 200)
            self.assertEqual(analysis_payload["events_analyzed"], 2)
            self.assertEqual(
                [event["country"] for event in analyze.call_args.args[2]],
                ["GBP", "USD"],
            )
            self.assertEqual(
                analyze.call_args.args[0],
                "secret-gemini-key",
            )
            self.assertEqual(analyze.call_args.args[3], "gemini-3.5-flash-lite")
            self.assertEqual(
                analyze.call_args.args[4]["indicators"][0]["id"],
                "DGS10",
            )
            self.assertEqual(state["macro_ai_model"], "gemini-3.5-flash-lite")
            self.assertIn("Bias GBP netral", analysis_payload["analysis"])
            self.assertEqual(analysis_payload["indicators_analyzed"], 1)
            connection.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)

    def test_pivot_detection_requires_a_local_extreme(self) -> None:
        highs = np.array([1.0, 2.0, 5.0, 3.0, 2.0])
        lows = np.array([5.0, 4.0, 1.0, 3.0, 4.0])

        self.assertTrue(is_pivot_high(highs, 2, 2))
        self.assertTrue(is_pivot_low(lows, 2, 2))
        self.assertFalse(is_pivot_high(highs, 0, 2))
        self.assertFalse(is_pivot_low(lows, 4, 2))

    def test_score_uses_documented_confluence_weights(self) -> None:
        self.assertEqual(calculate_score(True, True, True, False, True), 85)
        self.assertEqual(calculate_score(False, False, False, False, False), 0)

    def test_manual_volume_must_match_broker_limits_and_step(self) -> None:
        symbol_info = SimpleNamespace(
            volume_min=0.01,
            volume_max=10.0,
            volume_step=0.01,
        )

        self.assertTrue(is_valid_volume(0.05, symbol_info))
        self.assertFalse(is_valid_volume(0.015, symbol_info))
        self.assertFalse(is_valid_volume(10.01, symbol_info))

    def test_indicator_calculation_produces_expected_columns(self) -> None:
        config = Config(
            fast_ema_period=3,
            slow_ema_period=5,
            rsi_period=3,
            atr_period=3,
            adx_period=3,
            bands_period=3,
        )
        close = np.linspace(100.0, 110.0, 40)
        rates = pd.DataFrame(
            {
                "open": close - 0.1,
                "high": close + 0.5,
                "low": close - 0.5,
                "close": close,
                "tick_volume": np.full(40, 100, dtype=np.int64),
            }
        )

        result = calculate_indicators(rates, config)

        for column in (
            "ema_fast",
            "ema_slow",
            "rsi",
            "atr",
            "adx",
            "bands_middle",
            "bands_upper",
            "bands_lower",
            "macd",
            "macd_signal",
            "stochastic_k",
            "obv",
        ):
            self.assertIn(column, result.columns)
        self.assertTrue(np.isfinite(result["ema_slow"].iloc[-1]))
        self.assertTrue(np.isfinite(result["macd_signal"].iloc[-1]))
        self.assertGreater(result["bands_upper"].iloc[-1], result["bands_lower"].iloc[-1])

    def test_dashboard_history_includes_the_forming_live_candle(self) -> None:
        config = Config(
            fast_ema_period=3,
            slow_ema_period=5,
            rsi_period=3,
            atr_period=3,
            adx_period=3,
            bands_period=3,
        )
        close = np.linspace(100.0, 110.0, 40)
        rates = pd.DataFrame(
            {
                "time": pd.date_range("2025-01-01", periods=40, freq="min", tz="UTC"),
                "open": close - 0.1,
                "high": close + 0.5,
                "low": close - 0.5,
                "close": close,
                "tick_volume": np.full(40, 100, dtype=np.int64),
            }
        )

        history = build_dashboard_history(rates, config, limit=10)

        self.assertEqual(len(history), 10)
        self.assertEqual(history[-1]["close"], float(close[-1]))
        self.assertEqual(history[-1]["time"], rates.iloc[-1]["time"].isoformat())
        self.assertEqual(history[-1]["tick_volume"], 100.0)

    def test_signal_journal_records_once_and_tracks_closed_bar_outcomes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            journal_path = Path(temp_dir) / "signals.sqlite3"
            initialize_signal_journal(journal_path)
            signal_time = pd.Timestamp("2025-01-01T00:00:00Z")
            setup = monitor.Setup(
                bar_time=signal_time,
                status="BUY",
                trend="BULLISH MTF",
                structure="BOS bullish",
                score=85,
                buy_score=85,
                sell_score=10,
                rsi=55.0,
                adx=25.0,
                band_width_percent=1.0,
                relative_volume=1.5,
                atr=1.0,
                spread_points=2.0,
                macd=0.2,
                macd_signal=0.1,
                stochastic_k=60.0,
                components={"Trend MTF": True},
                entry=100.0,
                stop=98.0,
                target1=102.0,
                target2=104.0,
            )

            self.assertTrue(record_signal(journal_path, "TEST", "M1", setup, 0.01))
            self.assertFalse(record_signal(journal_path, "TEST", "M1", setup, 0.01))
            self.assertFalse(
                record_signal(
                    journal_path,
                    "TEST",
                    "M1",
                    replace(setup, status="NO TRADE"),
                    0.01,
                )
            )

            rates = pd.DataFrame(
                {
                    "time": pd.date_range(
                        signal_time, periods=7, freq="min", tz="UTC"
                    ),
                    "open": [100, 100, 101, 99, 103, 101, 102],
                    "high": [100, 102, 102, 104, 104, 103, 103],
                    "low": [100, 99, 98, 97, 100, 99, 101],
                    "close": [100, 101, 99, 103, 101, 102, 102],
                }
            )
            self.assertEqual(
                update_signal_outcomes(journal_path, "TEST", "M1", rates),
                3,
            )
            snapshot = signal_journal_snapshot(journal_path, "TEST", "M1")

            self.assertEqual(snapshot["total_signals"], 1)
            self.assertEqual([item["samples"] for item in snapshot["summary"]], [1, 1, 1])
            self.assertEqual(snapshot["summary"][0]["average_net_points"], 98.0)
            self.assertAlmostEqual(snapshot["summary"][0]["average_net_r"], 0.49)
            self.assertEqual(
                snapshot["recent"][0]["outcomes"]["3"]["net_points"], 298.0
            )
            self.assertAlmostEqual(
                snapshot["recent"][0]["outcomes"]["3"]["net_r"], 1.49
            )
            self.assertAlmostEqual(
                snapshot["recent"][0]["outcomes"]["3"]["favorable_r"], 2.0
            )
            self.assertAlmostEqual(
                snapshot["recent"][0]["outcomes"]["3"]["adverse_r"], -1.5
            )
            self.assertEqual(
                snapshot["recent"][0]["outcomes"]["5"]["net_points"], 198.0
            )
            self.assertEqual(
                update_signal_outcomes(journal_path, "TEST", "M1", rates),
                0,
            )

    def test_signal_journal_migrates_existing_schema_without_dropping_rows(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            journal_path = Path(temp_dir) / "legacy.sqlite3"
            with monitor.closing(monitor.sqlite3.connect(journal_path)) as connection, connection:
                connection.executescript(
                    """
                    CREATE TABLE signals (
                        id INTEGER PRIMARY KEY,
                        symbol TEXT NOT NULL,
                        timeframe TEXT NOT NULL,
                        bar_time TEXT NOT NULL,
                        direction TEXT NOT NULL,
                        entry_price REAL NOT NULL,
                        point_size REAL NOT NULL,
                        score INTEGER NOT NULL,
                        trend TEXT NOT NULL,
                        structure TEXT NOT NULL,
                        spread_points REAL NOT NULL,
                        components_json TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        UNIQUE (symbol, timeframe, bar_time)
                    );
                    CREATE TABLE signal_outcomes (
                        signal_id INTEGER NOT NULL,
                        horizon_bars INTEGER NOT NULL,
                        close_price REAL NOT NULL,
                        net_points REAL NOT NULL,
                        favorable_points REAL NOT NULL,
                        adverse_points REAL NOT NULL,
                        completed_at TEXT NOT NULL,
                        PRIMARY KEY (signal_id, horizon_bars)
                    );
                    INSERT INTO signals VALUES (
                        1, 'TEST', 'M1', '2025-01-01T00:00:00+00:00',
                        'BUY', 100, 0.01, 80, 'BULLISH', 'BOS',
                        2, '{}', '2025-01-01T00:00:00+00:00'
                    );
                    INSERT INTO signal_outcomes VALUES (
                        1, 1, 101, 98, 200, -100, '2025-01-01T00:01:00+00:00'
                    );
                    """
                )

            initialize_signal_journal(journal_path)
            snapshot = signal_journal_snapshot(journal_path, "TEST", "M1")

            self.assertEqual(snapshot["total_signals"], 1)
            self.assertEqual(snapshot["recent"][0]["outcomes"]["1"]["net_points"], 98)
            self.assertIsNone(snapshot["recent"][0]["outcomes"]["1"]["net_r"])
            self.assertEqual(snapshot["recent"][0]["risk_points"], 0)

    def test_historical_backtest_uses_next_open_and_does_not_pass_future_ohlc_to_setup(self) -> None:
        config = Config(
            fast_ema_period=3,
            slow_ema_period=5,
            structure_lookback=5,
            swing_strength=1,
            volume_period=2,
        )
        close = 100.0 + np.arange(24, dtype=float) * 0.05
        rates_close = np.concatenate((close, [5000.0]))
        rates = pd.DataFrame(
            {
                "time": pd.date_range(
                    "2025-01-01T00:00:00Z", periods=len(rates_close), freq="min"
                ),
                "open": rates_close,
                "high": rates_close + 0.1,
                "low": rates_close - 0.1,
                "close": rates_close,
                "tick_volume": np.full(len(rates_close), 100),
                "spread": np.full(len(rates_close), 2),
            }
        )
        higher_rates = rates.iloc[: config.slow_ema_period + 2].copy()
        analyzed: list[pd.DataFrame] = []

        def fake_analysis(
            chart_rates: pd.DataFrame,
            higher: pd.DataFrame,
            spread_points: float,
            selected_config: Config,
        ) -> monitor.Setup:
            analyzed.append(chart_rates.copy())
            signal_bar = chart_rates.iloc[-2]
            entry = float(signal_bar["close"])
            return monitor.Setup(
                bar_time=signal_bar["time"],
                status="BUY",
                trend="BULLISH MTF",
                structure="BOS bullish",
                score=80,
                buy_score=80,
                sell_score=0,
                rsi=55,
                adx=25,
                band_width_percent=1,
                relative_volume=1.5,
                atr=0.1,
                spread_points=spread_points,
                macd=0.2,
                macd_signal=0.1,
                stochastic_k=60,
                components={},
                entry=entry,
                stop=entry - 0.2,
                target1=entry + 0.2,
                target2=entry + 0.4,
            )

        with patch.object(monitor, "analyze_latest", side_effect=fake_analysis):
            result = run_historical_backtest(rates, higher_rates, 0.01, 1, config)
            costs_result = run_historical_backtest(
                rates,
                higher_rates,
                0.01,
                1,
                config,
                commission_points=1,
                slippage_points=0.5,
            )

        self.assertEqual(result["signals_tested"], {"in_sample": 6, "out_of_sample": 3})
        self.assertEqual(result["signals_detected"], {"in_sample": 7, "out_of_sample": 3})
        self.assertEqual(result["bars"], 24)
        self.assertEqual(result["summary"]["in_sample"][0]["samples"], 6)
        self.assertAlmostEqual(result["summary"]["in_sample"][0]["average_net_points"], -2.0)
        self.assertAlmostEqual(
            result["summary"]["out_of_sample"][0]["expectancy_r"], -2 / 27
        )
        self.assertFalse(
            result["summary"]["out_of_sample"][0]["profit_factor_unbounded"]
        )
        self.assertEqual(result["summary"]["out_of_sample"][0]["profit_factor"], 0)
        self.assertEqual(result["costs"]["commission_points_round_turn"], 0)
        self.assertAlmostEqual(
            costs_result["summary"]["out_of_sample"][0]["average_net_points"], -4.0
        )
        self.assertEqual(
            costs_result["costs"]["commission_points_round_turn"], 1
        )
        self.assertEqual(costs_result["costs"]["slippage_points_per_side"], 0.5)
        self.assertEqual(
            result["assumptions"]["higher_timeframe"],
            "Hanya candle konfirmasi yang sudah terkonfirmasi pada waktu sinyal.",
        )
        self.assertGreater(len(analyzed), 0)
        for analysis_rates in analyzed:
            signal_bar = analysis_rates.iloc[-2]
            forming_bar = analysis_rates.iloc[-1]
            self.assertEqual(forming_bar["time"], signal_bar["time"] + pd.Timedelta(minutes=1))
            for field in ("open", "high", "low", "close", "tick_volume", "spread"):
                self.assertEqual(forming_bar[field], signal_bar[field])

    def test_backtest_exit_models_sl_tp_ambiguity_gaps_and_execution_costs(self) -> None:
        both_touched = pd.DataFrame(
            [{"open": 100.0, "high": 102.0, "low": 98.0, "close": 101.0, "spread": 0.0}]
        )
        ambiguous = monitor.simulate_backtest_exit(
            both_touched, "BUY", 100.0, 99.0, 101.0, 1.0, 0.0, 0.0
        )
        self.assertEqual(ambiguous["exit_reason"], "ambiguous_sl")
        self.assertTrue(ambiguous["ambiguous_stop_target"])
        self.assertEqual(ambiguous["net_points"], -1)

        target_bar = pd.DataFrame(
            [{"open": 100.0, "high": 101.5, "low": 99.5, "close": 101.0, "spread": 0.0}]
        )
        target_exit = monitor.simulate_backtest_exit(
            target_bar, "BUY", 100.0, 99.0, 101.0, 1.0, 0.0, 0.0
        )
        self.assertEqual(target_exit["exit_reason"], "tp")
        self.assertEqual(target_exit["net_points"], 1)

        gap_bar = pd.DataFrame(
            [{"open": 97.0, "high": 98.0, "low": 96.0, "close": 97.5, "spread": 0.0}]
        )
        gap_exit = monitor.simulate_backtest_exit(
            gap_bar, "BUY", 100.0, 99.0, 101.0, 1.0, 0.0, 0.0
        )
        self.assertEqual(gap_exit["exit_reason"], "sl")
        self.assertEqual(gap_exit["net_points"], -3)

        time_bar = pd.DataFrame(
            [{"open": 100.0, "high": 102.0, "low": 99.5, "close": 101.5, "spread": 0.1}]
        )
        time_exit = monitor.simulate_backtest_exit(
            time_bar, "BUY", 100.0, 90.0, 110.0, 1.0, 0.2, 0.1
        )
        self.assertEqual(time_exit["exit_reason"], "time")
        self.assertAlmostEqual(time_exit["net_points"], 1.2)

        short_spread_bar = pd.DataFrame(
            [{"open": 100.0, "high": 100.8, "low": 99.5, "close": 100.0, "spread": 0.3}]
        )
        short_exit = monitor.simulate_backtest_exit(
            short_spread_bar, "SELL", 100.0, 101.0, 99.0, 1.0, 0.0, 0.0
        )
        self.assertEqual(short_exit["exit_reason"], "sl")
        self.assertEqual(short_exit["net_points"], -1.0)

    def test_structure_uses_only_confirmed_pivots_before_signal(self) -> None:
        config = Config(swing_strength=1, structure_lookback=10)
        data = pd.DataFrame(
            {
                "high": [2, 5, 3, 6, 4, 7, 5, 8, 6, 9, 7],
                "low": [1, 3, 2, 4, 3, 5, 4, 6, 5, 7, 6],
                "close": [1.5, 4, 2.5, 5, 3.5, 6, 4.5, 7, 5.5, 8, 7],
            }
        )

        result = evaluate_structure(data, 10, config)

        self.assertTrue(result[0])
        self.assertFalse(result[1])
        self.assertFalse(result[2])
        self.assertFalse(result[3])

    def test_latest_analysis_uses_closed_chart_and_higher_timeframe_bars(self) -> None:
        count = 600
        chart_close = 100.0 + np.arange(count) * 0.02 + np.sin(np.arange(count) / 5) * 0.5
        chart_rates = pd.DataFrame(
            {
                "time": pd.date_range("2025-01-01", periods=count, freq="15min", tz="UTC"),
                "open": chart_close - 0.05,
                "high": chart_close + 0.3,
                "low": chart_close - 0.3,
                "close": chart_close,
                "tick_volume": np.full(count, 100, dtype=np.int64),
            }
        )
        higher_count = 500
        higher_close = (
            100.0
            + np.arange(higher_count) * 0.3
            + np.sin(np.arange(higher_count) / 6) * 2
        )
        higher_rates = pd.DataFrame(
            {
                "time": pd.date_range(
                    "2024-11-25", periods=higher_count, freq="4h", tz="UTC"
                ),
                "open": higher_close - 0.1,
                "high": higher_close + 1.0,
                "low": higher_close - 1.0,
                "close": higher_close,
                "tick_volume": np.full(higher_count, 500, dtype=np.int64),
            }
        )

        setup = analyze_latest(chart_rates, higher_rates, 12.0, Config())

        self.assertEqual(setup.bar_time, chart_rates.iloc[-2]["time"])
        self.assertIn(
            setup.status,
            (
                "BUY",
                "SELL",
                "WATCH BUY",
                "WATCH SELL",
                "NO TRADE - regime",
                "NO TRADE - sesi",
                "NO TRADE - syarat belum lengkap",
                "NO TRADE - spread",
            ),
        )
        self.assertTrue(np.isfinite(setup.atr))
        self.assertIsInstance(json.loads(json.dumps(setup.components)), dict)

    def test_higher_timeframe_confirmation_ignores_unclosed_and_future_bars(self) -> None:
        config = Config(fast_ema_period=3, slow_ema_period=5)
        close = 100.0 + np.arange(30, dtype=float)
        rates = pd.DataFrame(
            {
                "time": pd.date_range(
                    "2025-01-01T00:00:00Z", periods=len(close), freq="4h"
                ),
                "open": close - 0.1,
                "high": close + 0.2,
                "low": close - 0.2,
                "close": close,
                "tick_volume": np.full(len(close), 100),
            }
        )
        signal_time = rates.iloc[-5]["time"] + pd.Timedelta(hours=1)
        baseline = monitor.get_higher_timeframe_trend(
            signal_time, calculate_indicators(rates, config)
        )
        future_changed = rates.copy()
        future_changed.loc[len(rates) - 5 :, ["open", "high", "low", "close"]] = (
            10000.0
        )
        modified = monitor.get_higher_timeframe_trend(
            signal_time, calculate_indicators(future_changed, config)
        )

        self.assertEqual(baseline, (True, False))
        self.assertEqual(modified, baseline)


if __name__ == "__main__":
    unittest.main()
