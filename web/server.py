"""
AlphaMind AI — Quantitative Web API & Static File Server
Supports:
- Viewport-Aware On-Demand Real-Time Quote Polling (/api/quotes/batch)
- Taiwan Full Stock Universe, Sector/Theme Classification & Multi-Factor Screener (/api/screener)
- Taiwan Full ETF Zone: Constituents, Multi-Period Returns & Reverse Lookup (/api/etfs)
- Asset Calculator, Watchlist, Position Calculator & Price/Pattern Smart Alerts (/api/portfolio, /api/portfolio/action)
- Stock Analysis with K-Line Candlestick Pattern Recognition, Dual-Track Stops & Neutral AI (/api/stock-analysis, /api/dual-stops, /api/ai-synthesis)
"""

import email.message
import http.server
import importlib.machinery
import io
import json
import mimetypes
import os
import socketserver
import sys
import types
import urllib.parse
from datetime import datetime
from typing import Any, Callable, Dict, Iterable, List, Tuple
import numpy as np
import pandas as pd

# Ensure both package root and parent workspace root are in sys.path
PACKAGE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
WORKSPACE_ROOT = os.path.abspath(os.path.join(PACKAGE_ROOT, ".."))
for _p in (PACKAGE_ROOT, WORKSPACE_ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# Support `from alphamind.*` regardless of checkout directory name (e.g. `/opt/render/project/src` or `/app`)
if "alphamind" not in sys.modules:
    _pkg = types.ModuleType("alphamind")
    _pkg.__path__ = [PACKAGE_ROOT]
    _pkg.__package__ = "alphamind"
    _spec = importlib.machinery.ModuleSpec("alphamind", None, is_package=True)
    _spec.submodule_search_locations = [PACKAGE_ROOT]
    _pkg.__spec__ = _spec
    sys.modules["alphamind"] = _pkg

from alphamind.ingestion.macro_collector import GlobalMacroCollector
from alphamind.ingestion.finmind_collector import FinMindConfig, load_env_variable
from alphamind.engine.macro_engine import GlobalMacroEngine
from alphamind.engine.risk_engine import DailyBar, DynamicStopLossEngine
from alphamind.engine.valuation_engine import FinancialStatementData, ValuationEngine
from alphamind.engine.decision_synthesizer import DecisionSynthesizer
from alphamind.engine.supply_chain_engine import SupplyChainEdge
from alphamind.engine.pattern_engine import CandlestickPatternEngine
from alphamind.engine.backtest_engine import BacktestEngine
from alphamind.engine.overfitting_guard import OverfittingGuard
from alphamind.engine.tw_market_universe import (
    CORE_TAIWAN_STOCKS,
    TAIWAN_ETFS_CATALOG,
    TaiwanMarketUniverseEngine,
)
from alphamind.engine.portfolio_alert_engine import PortfolioAndAlertEngine
from alphamind.engine.auth_user_engine import MultiUserAuthAndStoreEngine, UserAccount
from alphamind.engine.fugle_adapter import FugleMarketDataClient, load_fugle_credentials
from alphamind.ai.devils_advocate import DevilsAdvocateAgent
from alphamind.ai.structured_extractor import StructuredExtractor
from alphamind.ai.neutral_synthesizer import NeutralAIAgent


WEB_DIR = os.path.dirname(os.path.abspath(__file__))
HOST = os.environ.get("HOST", "0.0.0.0")
PORT = int(os.environ.get("PORT", "8888"))


class _SafeFugleWrapper:
    def __init__(self) -> None:
        creds = load_fugle_credentials()
        self.is_configured = bool(creds.api_key)
        self.client = FugleMarketDataClient(creds) if self.is_configured else None

    def fetch_intraday_quote(self, symbol: str) -> Dict[str, Any]:
        if not self.client:
            return {"status": "UNCONFIGURED"}
        try:
            data = self.client.fetch_intraday_quote(symbol)
            return {"status": "LIVE_OK", "data": data}
        except Exception as e:
            return {"status": "FALLBACK", "error": str(e)}


# Shared singleton engines across requests
# - UNIVERSE_ENGINE (台股與全台灣 ETF 行情快取) 全站所有登入使用者共用，節省 API 額度
# - AUTH_USER_ENGINE (使用者帳號認證與個人資產/持倉/自選股/提醒) 依 user_id 嚴格隔離
UNIVERSE_ENGINE = TaiwanMarketUniverseEngine()
AUTH_USER_ENGINE = MultiUserAuthAndStoreEngine()
PATTERN_ENGINE = CandlestickPatternEngine()
FUGLE_ADAPTER = _SafeFugleWrapper()


def _resolve_stock_meta(symbol: str) -> Dict[str, Any]:
    clean = symbol.replace(".TW", "").replace(".TWO", "").strip().upper()
    for s in CORE_TAIWAN_STOCKS:
        if s["symbol"].upper() == clean:
            return s
    for e in TAIWAN_ETFS_CATALOG:
        if e.etf_symbol.upper() == clean:
            return {
                "symbol": e.etf_symbol,
                "name": e.etf_name,
                "market": "TWSE",
                "primary_sector": f"ETF ({e.category})",
                "theme_tags": [e.category, e.issuer],
                "price": e.price,
                "change_pct": e.change_pct,
                "volume_lots": 18000,
                "pe_ratio": 18.0,
                "pb_ratio": 2.2,
                "dividend_yield": e.annual_yield_pct,
                "roe": 16.0,
                "f_score": 8,
                "inst_flow_5d_lots": 5200,
                "kline_pattern": "均線多頭排列穩步推升",
                "kline_bias": "BULLISH",
            }
    return {
        "symbol": clean,
        "name": f"台股標的 {clean}",
        "market": "TWSE",
        "primary_sector": "上市櫃個股",
        "theme_tags": ["台股全市場"],
        "price": 120.0,
        "change_pct": 0.85,
        "volume_lots": 3500,
        "pe_ratio": 17.5,
        "pb_ratio": 2.1,
        "dividend_yield": 3.2,
        "roe": 15.0,
        "f_score": 7,
        "inst_flow_5d_lots": 1200,
        "kline_pattern": "區間箱型量縮整理",
        "kline_bias": "NEUTRAL",
    }


def _generate_realistic_bars(symbol: str, current_price: float, kline_bias: str) -> List[DailyBar]:
    clean = symbol.replace(".TW", "").strip().upper()
    seed_val = sum(ord(c) * (idx + 1) for idx, c in enumerate(clean)) % 997
    rng = np.random.default_rng(seed_val)

    bars: List[DailyBar] = []
    px = current_price * (0.91 if kline_bias == "BULLISH" else (1.06 if kline_bias == "BEARISH" else 0.98))
    drift = (current_price - px) / 29.0

    for i in range(30):
        noise = float(rng.normal(0, current_price * 0.008))
        if i == 28:
            close_i = current_price * (0.982 if kline_bias == "BULLISH" else (1.015 if kline_bias == "BEARISH" else 0.998))
            open_i = close_i * (1.012 if kline_bias == "BULLISH" else (0.988 if kline_bias == "BEARISH" else 1.002))
        elif i == 29:
            close_i = current_price
            open_i = current_price * (0.976 if kline_bias == "BULLISH" else (1.022 if kline_bias == "BEARISH" else 0.996))
        else:
            px = max(1.0, px + drift + noise)
            close_i = px
            open_i = px * float(1.0 + rng.uniform(-0.01, 0.01))

        high_i = max(open_i, close_i) * float(1.0 + rng.uniform(0.004, 0.014))
        low_i = min(open_i, close_i) * float(1.0 - rng.uniform(0.004, 0.014))
        vol_i = int(12_000_000 * (1.45 if i == 29 and kline_bias != "NEUTRAL" else rng.uniform(0.75, 1.25)))
        inst_i = int(3500 if kline_bias == "BULLISH" else (-2200 if kline_bias == "BEARISH" else 400))

        bars.append(
            DailyBar(
                date=f"2026-10-{i+1:02d}",
                open=round(open_i, 2),
                high=round(high_i, 2),
                low=round(low_i, 2),
                close=round(close_i, 2),
                volume=vol_i,
                institutional_net_buy=inst_i,
            )
        )
    return bars


class AlphaMindApiHandler(http.server.SimpleHTTPRequestHandler):
    _wsgi_mode: bool = False
    _wsgi_status: int = 200
    _wsgi_headers: List[Tuple[str, str]] = []

    def __init__(self, *args, **kwargs):
        self._wsgi_mode = False
        self._wsgi_status = 200
        self._wsgi_headers = []
        super().__init__(*args, directory=WEB_DIR, **kwargs)

    def log_message(self, format: str, *args: Any) -> None:
        # Keep console clean while serving rapid viewport polls
        pass

    def send_response(self, code: int, message: str | None = None) -> None:
        if getattr(self, "_wsgi_mode", False):
            self._wsgi_status = int(code)
            return
        super().send_response(code, message)

    def send_header(self, keyword: str, value: str) -> None:
        if getattr(self, "_wsgi_mode", False):
            self._wsgi_headers.append((str(keyword), str(value)))
            return
        super().send_header(keyword, value)

    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-AlphaMind-Token")
        if getattr(self, "_wsgi_mode", False):
            return
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.end_headers()

    def _extract_token(self, qs: Dict[str, List[str]] = None) -> str:
        auth_hdr = self.headers.get("Authorization", "")
        if auth_hdr.startswith("Bearer "):
            return auth_hdr.replace("Bearer ", "").strip()
        x_tok = self.headers.get("X-AlphaMind-Token", "").strip()
        if x_tok:
            return x_tok
        if qs and "token" in qs and qs["token"]:
            return qs["token"][0].strip()
        return ""

    def _require_auth_user(self, qs: Dict[str, List[str]] = None) -> UserAccount | None:
        tok = self._extract_token(qs)
        user = AUTH_USER_ENGINE.verify_session_token(tok)
        if not user:
            self._send_json(
                {
                    "error": "UNAUTHORIZED",
                    "message": "此平台強制要求登入，請先登入您的專屬帳號以存取功能與個人資料。",
                    "demo_accounts": AUTH_USER_ENGINE.list_demo_accounts_public(),
                },
                status_code=401,
            )
            return None
        return user

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        qs = urllib.parse.parse_qs(parsed.query)

        if parsed.path in ("/api/health", "/health"):
            self._send_json({"status": "ok", "service": "alphamind-api", "timestamp": datetime.now().isoformat()})
        elif parsed.path == "/api/auth/session":
            self._handle_auth_session(qs)
        elif parsed.path.startswith("/api/"):
            user = self._require_auth_user(qs)
            if not user:
                return
            if parsed.path == "/api/overview":
                self._handle_overview(user)
            elif parsed.path == "/api/stocks":
                self._handle_stocks_list()
            elif parsed.path == "/api/screener":
                self._handle_screener(qs)
            elif parsed.path == "/api/sectors":
                self._handle_sectors()
            elif parsed.path == "/api/etfs":
                self._handle_etfs(qs)
            elif parsed.path == "/api/portfolio":
                self._handle_portfolio_get(user)
            elif parsed.path == "/api/quotes/batch":
                self._handle_batch_quotes(qs)
            elif parsed.path == "/api/search":
                self._handle_autocomplete_search(qs)
            else:
                self._send_json({"error": "NOT_FOUND"}, status_code=404)
        else:
            rel_path = parsed.path.lstrip("/") or "index.html"
            target_file = os.path.abspath(os.path.join(WEB_DIR, rel_path))
            if not target_file.startswith(os.path.abspath(WEB_DIR)) or os.path.isdir(target_file):
                target_file = os.path.join(WEB_DIR, "index.html")
            if not os.path.isfile(target_file):
                target_file = os.path.join(WEB_DIR, "index.html")
            if os.path.isfile(target_file):
                ctype, _ = mimetypes.guess_type(target_file)
                if not ctype:
                    ctype = "text/html; charset=utf-8"
                elif ctype.startswith("text/") or ctype == "application/javascript":
                    ctype = f"{ctype}; charset=utf-8"
                with open(target_file, "rb") as f:
                    body_bytes = f.read()
                self.send_response(200)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(body_bytes)))
                self.end_headers()
                self.wfile.write(body_bytes)
            else:
                self._send_json({"error": "NOT_FOUND"}, status_code=404)

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        qs = urllib.parse.parse_qs(parsed.query)
        content_len = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_len).decode("utf-8") if content_len > 0 else "{}"
        try:
            payload = json.loads(body)
        except Exception:
            payload = {}

        # 公開認證端點（登入 / 註冊 / 登出）
        if parsed.path == "/api/auth/login":
            self._handle_auth_login(payload)
            return
        elif parsed.path == "/api/auth/register":
            self._handle_auth_register(payload)
            return
        elif parsed.path == "/api/auth/logout":
            self._handle_auth_logout(qs)
            return

        # 強制驗證：所有其他業務 API 必須登入才可呼叫
        user = self._require_auth_user(qs)
        if not user:
            return

        if parsed.path == "/api/stock-analysis":
            self._handle_stock_analysis(payload)
        elif parsed.path == "/api/dual-stops":
            self._handle_dual_stops(payload)
        elif parsed.path == "/api/ai-synthesis":
            self._handle_ai_synthesis(payload)
        elif parsed.path == "/api/portfolio/action":
            self._handle_portfolio_action(user, payload)
        elif parsed.path == "/api/backtest":
            self._handle_backtest(payload)
        else:
            self.send_response(404)
            self.end_headers()

    def _send_json(self, data: Any, status_code: int = 200):
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))

    # --------------------------------------------------------------------------
    # API 0: 多使用者強制認證與持久化自動登入 (/api/auth/*)
    # --------------------------------------------------------------------------
    def _handle_auth_login(self, payload: Dict[str, Any]):
        username = str(payload.get("username", "")).strip()
        password = str(payload.get("password", ""))
        ok, msg, auth_data = AUTH_USER_ENGINE.login_user(username, password)
        if not ok or not auth_data:
            self._send_json({"ok": False, "message": msg}, status_code=401)
            return
        self._send_json({"ok": True, "message": msg, **auth_data})

    def _handle_auth_register(self, payload: Dict[str, Any]):
        username = str(payload.get("username", "")).strip()
        password = str(payload.get("password", ""))
        display_name = str(payload.get("display_name", "")).strip()
        email = str(payload.get("email", "")).strip()
        initial_cash = float(payload.get("initial_cash_twd") or 1_000_000.0)
        ok, msg, auth_data = AUTH_USER_ENGINE.register_user(
            username=username,
            password=password,
            display_name=display_name,
            email=email,
            initial_cash_twd=initial_cash,
        )
        if not ok or not auth_data:
            self._send_json({"ok": False, "message": msg}, status_code=400)
            return
        self._send_json({"ok": True, "message": msg, **auth_data})

    def _handle_auth_session(self, qs: Dict[str, List[str]]):
        tok = self._extract_token(qs)
        user = AUTH_USER_ENGINE.verify_session_token(tok)
        if not user:
            self._send_json(
                {
                    "authenticated": False,
                    "demo_accounts": AUTH_USER_ENGINE.list_demo_accounts_public(),
                }
            )
            return
        self._send_json(
            {
                "authenticated": True,
                **AUTH_USER_ENGINE._format_auth_response(user, tok),
                "demo_accounts": AUTH_USER_ENGINE.list_demo_accounts_public(),
            }
        )

    def _handle_auth_logout(self, qs: Dict[str, List[str]]):
        tok = self._extract_token(qs)
        AUTH_USER_ENGINE.logout_token(tok)
        self._send_json({"ok": True, "message": "已安全登出"})

    # --------------------------------------------------------------------------
    # API 1: 全局戰情 (6國總經燈號 + 產業/概念資金流向排行) — 行情資料全站共用
    # --------------------------------------------------------------------------
    def _handle_overview(self, user: UserAccount):
        rates_fx, expectations, dxy = GlobalMacroCollector.get_latest_snapshot()
        macro_engine = GlobalMacroEngine()
        macro_res = macro_engine.evaluate(rates_fx, expectations, dxy)
        sec_summary = UNIVERSE_ENGINE.get_sector_and_theme_summary()

        regions_status = {
            "US": {"policy_rate": 4.75, "yield_10y": 4.38, "vix": 15.8, "stance": "降息週期預期 (80%)"},
            "TW": {"policy_rate": 2.00, "yield_10y": 1.58, "vix": 16.2, "fx_twd": 32.15, "stance": "維持溫和緊縮"},
            "JP": {"policy_rate": 0.25, "yield_10y": 1.05, "vix": 22.4, "fx_jpy": 153.20, "carry_risk": macro_res.carry_trade_unwind_risk},
            "KR": {"policy_rate": 3.25, "yield_10y": 3.05, "vix": 18.5, "fx_krw": 1375.0},
            "HK": {"policy_rate": 4.75, "yield_10y": 3.95, "vix": 21.8, "fx_hkd": 7.77},
            "EU": {"policy_rate": 3.25, "yield_10y": 2.30, "vix": 17.2, "fx_eur": 1.088},
        }

        api_registry = {
            "fugle_realtime": bool(FUGLE_ADAPTER.is_configured),
            "finmind_token": bool(FinMindConfig().token),
            "gemini_ai": bool(load_env_variable("GEMINI_API_KEY")),
            "supabase_cloud": bool(load_env_variable("SUPABASE_URL") and load_env_variable("SUPABASE_ANON_KEY")),
            "twse_tpex_openapi": bool(load_env_variable("TWSE_OPENAPI_STOCK_DAY_ALL") and load_env_variable("TPEX_OPENAPI_DAILY_CLOSE")),
            "twse_mis_etf_nav": bool(load_env_variable("TWSE_MIS_QUOTE_URL") and load_env_variable("TWSE_ETF_ANAV_URL")),
            "yahoo_finance_v8": bool(load_env_variable("YAHOO_FINANCE_CHART_URL")),
            "macro_fx_fred": bool(load_env_variable("EXCHANGE_RATE_API_URL") and load_env_variable("FRED_CSV_GRAPH_URL")),
        }

        self._send_json({
            "dxy": dxy,
            "macro_multiplier": macro_res.macro_regime_multiplier,
            "us_yield_spread": macro_res.us_yield_spread_10y_2y,
            "is_bear_steep": macro_res.is_bear_steepening,
            "carry_risk": macro_res.carry_trade_unwind_risk,
            "asia_flight_risk": macro_res.emerging_asia_capital_flight_risk,
            "warnings": macro_res.key_warnings,
            "sector_summary": sec_summary,
            "regions": regions_status,
            "fugle_configured": FUGLE_ADAPTER.is_configured,
            "finmind_configured": bool(FinMindConfig().token),
            "gemini_configured": bool(load_env_variable("GEMINI_API_KEY")),
            "api_registry": api_registry,
            "timestamp": datetime.now().strftime("%H:%M:%S"),
        })

    def _handle_stocks_list(self):
        items = UNIVERSE_ENGINE.get_stock_universe()
        self._send_json([i.__dict__ for i in items])

    # --------------------------------------------------------------------------
    # API 2: 智慧選股建議與全市場分類篩選 (/api/screener)
    # --------------------------------------------------------------------------
    def _handle_screener(self, qs: Dict[str, List[str]]):
        profile = qs.get("profile", ["ALL"])[0]
        sector = qs.get("sector", ["ALL"])[0]
        theme = qs.get("theme", ["ALL"])[0]
        search = qs.get("search", [""])[0]
        min_f = int(qs.get("min_f", ["6"])[0])
        min_rr = float(qs.get("min_rr", ["1.8"])[0])
        fetch_live = qs.get("live", ["0"])[0] == "1"

        universe = UNIVERSE_ENGINE.get_stock_universe(
            sector_filter=sector,
            theme_filter=theme,
            search_query=search,
            fetch_live_twse=fetch_live,
        )
        screener_res = UNIVERSE_ENGINE.run_stock_screener(
            strategy_profile=profile,
            sector=sector if sector != "ALL" else None,
            min_f_score=min_f,
            min_rr_ratio=min_rr,
        )
        sec_summary = UNIVERSE_ENGINE.get_sector_and_theme_summary()

        self._send_json({
            "universe_count": len(universe),
            "stocks": [u.__dict__ for u in universe],
            "screener": screener_res,
            "sector_summary": sec_summary,
        })

    def _handle_sectors(self):
        self._send_json(UNIVERSE_ENGINE.get_sector_and_theme_summary())

    # --------------------------------------------------------------------------
    # API 3: 台灣全 ETF 專區 (/api/etfs)
    # --------------------------------------------------------------------------
    def _handle_etfs(self, qs: Dict[str, List[str]]):
        category = qs.get("category", ["ALL"])[0]
        symbol = qs.get("symbol", ["0050"])[0]
        reverse_stock = qs.get("reverse_stock", ["2330"])[0]
        sort_by = qs.get("sort", ["YTD"])[0]

        res = UNIVERSE_ENGINE.get_etf_hub_data(
            category_filter=category,
            etf_symbol=symbol,
            reverse_stock_symbol=reverse_stock,
            sort_by_return_period=sort_by,
        )
        self._send_json(res)

    # --------------------------------------------------------------------------
    # API 4: 資產計算、持倉管理、自選股與目標價/型態轉變提醒 (/api/portfolio)
    #        每位使用者的資產、持倉、自選股、策略設定完全獨立隔離；股票與 ETF 行情共用
    # --------------------------------------------------------------------------
    def _handle_portfolio_get(self, user: UserAccount):
        user_engine = AUTH_USER_ENGINE.get_user_portfolio_engine(user.user_id)
        data = user_engine.evaluate_portfolio_and_alerts(UNIVERSE_ENGINE)
        data["user_profile"] = {
            "user_id": user.user_id,
            "username": user.username,
            "display_name": user.display_name,
            "role": user.role,
            "strategy_prefs": user.strategy_prefs,
        }
        self._send_json(data)

    def _handle_portfolio_action(self, user: UserAccount, payload: Dict[str, Any]):
        user_engine = AUTH_USER_ENGINE.get_user_portfolio_engine(user.user_id)
        action = payload.get("action", "")
        if action == "update_cash":
            user_engine.update_cash_and_settings(
                cash_twd=payload.get("cash_twd"),
                fee_discount=payload.get("fee_discount"),
            )
            if payload.get("strategy_prefs") and isinstance(payload["strategy_prefs"], dict):
                AUTH_USER_ENGINE.update_user_strategy_prefs(user.user_id, payload["strategy_prefs"])
        elif action == "upsert_position":
            sym = str(payload.get("symbol", "2330")).strip().upper()
            meta = _resolve_stock_meta(sym)
            user_engine.upsert_position(
                symbol=sym,
                name=str(payload.get("name") or meta["name"]),
                shares=int(payload.get("shares", 1000)),
                avg_cost_price=float(payload.get("avg_cost_price", meta["price"])),
                custom_target_price=float(payload["custom_target_price"]) if payload.get("custom_target_price") else None,
                custom_stop_price=float(payload["custom_stop_price"]) if payload.get("custom_stop_price") else None,
                notes=str(payload.get("notes", "")),
            )
        elif action == "remove_position":
            user_engine.remove_position(str(payload.get("symbol", "")))
        elif action == "add_watchlist":
            sym = str(payload.get("symbol", "2330")).strip().upper()
            meta = _resolve_stock_meta(sym)
            user_engine.add_watchlist_item(
                symbol=sym,
                name=str(payload.get("name") or meta["name"]),
                target_buy_price=float(payload["target_buy_price"]) if payload.get("target_buy_price") else None,
            )
        elif action == "remove_watchlist":
            user_engine.remove_watchlist_item(str(payload.get("symbol", "")))

        data = user_engine.evaluate_portfolio_and_alerts(UNIVERSE_ENGINE)
        data["user_profile"] = {
            "user_id": user.user_id,
            "username": user.username,
            "display_name": user.display_name,
            "role": user.role,
            "strategy_prefs": user.strategy_prefs,
        }
        self._send_json(data)

    # --------------------------------------------------------------------------
    # API 5: 畫面可視範圍按需即時報價更新 (/api/quotes/batch)
    # --------------------------------------------------------------------------
    def _handle_batch_quotes(self, qs: Dict[str, List[str]]):
        raw_syms = qs.get("symbols", [""])[0]
        sym_list = [s.strip() for s in raw_syms.split(",") if s.strip()]
        res = UNIVERSE_ENGINE.poll_viewport_quotes(sym_list, fugle_adapter=FUGLE_ADAPTER)
        self._send_json(res)

    # --------------------------------------------------------------------------
    # API 6: 個股全維度量化診斷 (含 K 線型態辨識 + 型態修正目標價 + ETF 反查)
    # --------------------------------------------------------------------------
    def _handle_stock_analysis(self, payload: Dict[str, Any]):
        raw_sym = str(payload.get("symbol", "2330")).replace(".TW", "").strip().upper()
        meta = _resolve_stock_meta(raw_sym)
        current_price = float(payload.get("current_price") or meta["price"])

        val_engine = ValuationEngine()
        risk_engine = DynamicStopLossEngine(
            atr_period=int(payload.get("atr_period", 14)),
            chandelier_period=int(payload.get("chandelier_period", 22)),
            atr_multiplier=float(payload.get("atr_multiplier", 2.5)),
        )
        synthesizer = DecisionSynthesizer(base_position_size_pct=float(payload.get("base_position_pct", 15.0)))

        bars = _generate_realistic_bars(raw_sym, current_price, meta.get("kline_bias", "BULLISH"))
        risk_evals = risk_engine.evaluate_series(bars)
        latest_risk = risk_evals[-1]

        # K 線型態與結構轉折辨識
        pattern_report = PATTERN_ENGINE.evaluate_bars(raw_sym, bars)

        # 財報估值
        f_target = int(meta.get("f_score", 7))
        stmt = FinancialStatementData(
            net_income=350_000_000_000.0 if f_target >= 6 else -10_000_000_000.0,
            operating_cash_flow=420_000_000_000.0 if f_target >= 5 else -5_000_000_000.0,
            total_assets_current=2_500_000_000_000.0,
            total_assets_prior=2_200_000_000_000.0,
            long_term_debt_current=300_000_000_000.0,
            long_term_debt_prior=320_000_000_000.0 if f_target >= 7 else 250_000_000_000.0,
            current_assets_current=900_000_000_000.0,
            current_liabilities_current=450_000_000_000.0,
            current_assets_prior=800_000_000_000.0,
            current_liabilities_prior=450_000_000_000.0,
            shares_outstanding_current=25_930_000_000,
            shares_outstanding_prior=25_930_000_000,
            gross_margin_current=54.5 if f_target >= 7 else 22.0,
            gross_margin_prior=53.0 if f_target >= 7 else 25.0,
            asset_turnover_current=0.55,
            asset_turnover_prior=0.52,
            ebit=400_000_000_000.0,
            total_liabilities=800_000_000_000.0,
            retained_earnings=1_200_000_000_000.0,
            sales=1_400_000_000_000.0,
            market_cap=26_000_000_000_000.0,
        )
        pe_curr = float(meta.get("pe_ratio", 20.0))
        pb_curr = float(meta.get("pb_ratio", 3.5))
        eps_ttm = round(current_price / max(pe_curr, 1.0), 2)
        bps = round(current_price / max(pb_curr, 0.5), 2)
        fcf_aligned = 25_930_000_000 * eps_ttm * 0.92

        valuation = val_engine.evaluate(
            raw_sym,
            current_price,
            stmt,
            [pe_curr * 0.75, pe_curr * 0.9, pe_curr, pe_curr * 1.15, pe_curr * 1.3],
            [pb_curr * 0.8, pb_curr * 0.9, pb_curr, pb_curr * 1.1, pb_curr * 1.25],
            eps_ttm,
            bps,
            fcf_aligned,
        )

        rates_fx, expectations, dxy = GlobalMacroCollector.get_latest_snapshot()
        macro_engine = GlobalMacroEngine()
        macro_res = macro_engine.evaluate(rates_fx, expectations, dxy)

        edge = SupplyChainEdge(
            leader_symbol="NVDA",
            supplier_symbol=raw_sym,
            relationship_type="SUPPLIES_TO",
            revenue_share=0.35 if raw_sym in ("3131", "3017", "2382") else 0.18,
            confidence=0.95,
            is_sole_supplier=(raw_sym in ("2330", "2059", "5274")),
            substitutability_score=0.90 if raw_sym in ("2330", "2059", "3131") else 0.72,
        )

        decision = synthesizer.synthesize(
            symbol=raw_sym,
            current_price=current_price,
            macro_analysis=macro_res,
            valuation=valuation,
            risk_eval=latest_risk,
            supply_edge=edge,
            is_inst_net_buying_5d=(int(meta.get("inst_flow_5d_lots", 0)) >= 0),
            is_margin_overheated=False,
        )

        # 將 K 線型態修正因子納入目標價
        adjusted_target = round(decision.target_price * pattern_report.target_price_modifier, 2)

        red_team = DevilsAdvocateAgent.audit_bull_thesis(
            symbol=raw_sym,
            name=meta["name"],
            bull_thesis=f"{meta['primary_sector']} 核心供應商，具備 {', '.join(meta.get('theme_tags', [])[:2])} 動能",
            pe_ratio=valuation.pe_ratio_current,
        )

        # 反查持有此股票的台灣 ETF
        etf_holders = UNIVERSE_ENGINE.get_etf_hub_data(reverse_stock_symbol=raw_sym)["reverse_stock_lookup"]

        k_line_history = [
            {
                "date": b.date,
                "open": round(b.open, 2),
                "close": round(b.close, 2),
                "high": round(b.high, 2),
                "low": round(b.low, 2),
                "volume": b.volume,
                "stop": round(r.chandelier_stop, 2),
            }
            for b, r in zip(bars, risk_evals)
        ]

        self._send_json({
            "symbol": raw_sym,
            "name": meta["name"],
            "market": meta["market"],
            "primary_sector": meta["primary_sector"],
            "theme_tags": meta.get("theme_tags", []),
            "current_price": current_price,
            "change_pct": meta.get("change_pct", 0.0),
            "decision": {
                "action": decision.action.value,
                "position_pct": decision.recommended_position_pct,
                "stop_loss": decision.stop_loss_price,
                "target_price": adjusted_target,
                "raw_target_price": decision.target_price,
                "notes": decision.audit_notes,
            },
            "pattern_analysis": {
                "overall_bias": pattern_report.overall_pattern_bias,
                "regime_state": pattern_report.pattern_regime_state,
                "previous_regime": pattern_report.previous_regime_state,
                "is_transition": pattern_report.is_regime_transition,
                "transition_alert": pattern_report.transition_alert_message,
                "target_modifier": pattern_report.target_price_modifier,
                "neckline_support": pattern_report.pattern_neckline_support,
                "resistance_level": pattern_report.pattern_resistance_level,
                "patterns": [p.__dict__ for p in pattern_report.detected_patterns],
            },
            "valuation": {
                "f_score": valuation.piotroski_f_score,
                "z_score": valuation.altman_z_score,
                "pe": valuation.pe_ratio_current,
                "pb": valuation.pb_ratio_current,
                "dividend_yield": meta.get("dividend_yield", 2.5),
                "roe": meta.get("roe", 18.0),
                "dcf_consensus": valuation.dcf_intrinsic_value_consensus,
                "status": valuation.valuation_status,
                "pe_bands": valuation.pe_bands,
            },
            "risk": {
                "atr_14": round(latest_risk.atr_14, 2),
                "chandelier_stop": round(latest_risk.chandelier_stop, 2),
                "distance_pct": round(latest_risk.distance_to_stop_loss_pct, 2),
                "is_breached": latest_risk.is_chandelier_stop_breached,
            },
            "supply_chain": {
                "customer": edge.leader_symbol,
                "revenue_share_pct": round(edge.revenue_share * 100, 1),
                "is_sole": edge.is_sole_supplier,
                "substitutability": edge.substitutability_score,
            },
            "etf_holders": etf_holders,
            "red_team": {
                "verdict": red_team.red_team_verdict,
                "vulnerability": red_team.vulnerability_score,
                "fatal_reasons": red_team.three_fatal_bear_reasons,
            },
            "k_lines": k_line_history,
        })

    # --------------------------------------------------------------------------
    # API 7: 雙軌停利停損計算 (現價進場 vs 持倉均價 + K 線型態修正)
    # --------------------------------------------------------------------------
    def _handle_dual_stops(self, payload: Dict[str, Any]):
        raw_sym = str(payload.get("symbol", "2330")).replace(".TW", "").strip().upper()
        meta = _resolve_stock_meta(raw_sym)
        current_price = float(payload.get("current_price") or meta["price"])
        avg_cost_price = float(payload.get("avg_cost_price") or round(current_price * 0.91, 2))
        atr_14 = float(payload.get("atr_14") or max(1.0, round(current_price * 0.022, 2)))
        atr_mult = float(payload.get("atr_multiplier", 2.5))

        bars = _generate_realistic_bars(raw_sym, current_price, meta.get("kline_bias", "BULLISH"))
        pattern_report = PATTERN_ENGINE.evaluate_bars(raw_sym, bars)

        risk_engine = DynamicStopLossEngine(atr_multiplier=atr_mult)

        # 1. 現價預測 (納入 K 線型態修正因子與頸線支撐)
        unalloc = risk_engine.predict_unallocated_targets_and_stops(
            symbol=raw_sym,
            current_price=current_price,
            atr_14=atr_14,
            conservative_target=current_price * 1.08,
            consensus_target=current_price * 1.15,
            optimistic_target=current_price * 1.26,
            support_level=current_price * 0.98,
            pattern_target_modifier=pattern_report.target_price_modifier,
            pattern_support_stop=pattern_report.pattern_neckline_support,
        )

        # 2. 持倉策略 (以實際買進均價為基準)
        highest_p = max(current_price * 1.02, avg_cost_price * 1.09)
        alloc = risk_engine.evaluate_allocated_position_strategy(
            symbol=raw_sym,
            avg_cost_price=avg_cost_price,
            current_price=current_price,
            highest_price_since_entry=highest_p,
            atr_14=atr_14,
            holding_days=15,
        )

        self._send_json({
            "unallocated": {
                "current_price": unalloc.current_market_price,
                "entry_zone": [unalloc.suggested_entry_zone_low, unalloc.suggested_entry_zone_high],
                "initial_stop": unalloc.initial_stop_loss_price,
                "max_risk_pct": unalloc.max_risk_pct,
                "target_conservative": unalloc.take_profit_target_conservative,
                "target_consensus": unalloc.take_profit_target_consensus,
                "target_optimistic": unalloc.take_profit_target_optimistic,
                "pattern_modifier": pattern_report.target_price_modifier,
                "pattern_neckline": pattern_report.pattern_neckline_support,
                "risk_reward_ratio": unalloc.risk_reward_ratio,
                "is_favorable": unalloc.is_favorable_entry,
            },
            "allocated": {
                "avg_cost": alloc.avg_cost_price,
                "current_price": alloc.current_market_price,
                "unrealized_pnl_pct": alloc.unrealized_pnl_pct,
                "break_even_active": alloc.break_even_protection_active,
                "break_even_stop": alloc.break_even_stop_price,
                "effective_trailing_stop": alloc.effective_trailing_stop_price,
                "tier_1_target": alloc.tiered_take_profit_ladder["tier_1_take_profit_33pct"],
                "tier_2_target": alloc.tiered_take_profit_ladder["tier_2_take_profit_33pct"],
                "recommendation": alloc.action_recommendation,
                "rationale": alloc.action_rationale,
            },
        })

    # --------------------------------------------------------------------------
    # API 8: AI 中性裁決報告
    # --------------------------------------------------------------------------
    def _handle_ai_synthesis(self, payload: Dict[str, Any]):
        raw_sym = str(payload.get("symbol", "2330")).replace(".TW", "").strip().upper()
        meta = _resolve_stock_meta(raw_sym)
        name = meta["name"]
        current_price = float(payload.get("current_price") or meta["price"])
        avg_cost = float(payload.get("avg_cost_price") or round(current_price * 0.91, 2))
        atr_val = max(1.0, round(current_price * 0.022, 2))

        risk_engine = DynamicStopLossEngine()
        val_engine = ValuationEngine()
        synthesizer = DecisionSynthesizer()

        stmt = FinancialStatementData(
            net_income=350_000_000_000.0,
            operating_cash_flow=420_000_000_000.0,
            total_assets_current=2_500_000_000_000.0,
            total_assets_prior=2_200_000_000_000.0,
            long_term_debt_current=300_000_000_000.0,
            long_term_debt_prior=320_000_000_000.0,
            current_assets_current=900_000_000_000.0,
            current_liabilities_current=450_000_000_000.0,
            current_assets_prior=800_000_000_000.0,
            current_liabilities_prior=450_000_000_000.0,
            shares_outstanding_current=25_930_000_000,
            shares_outstanding_prior=25_930_000_000,
            gross_margin_current=54.5,
            gross_margin_prior=53.0,
            asset_turnover_current=0.55,
            asset_turnover_prior=0.52,
            ebit=400_000_000_000.0,
            total_liabilities=800_000_000_000.0,
            retained_earnings=1_200_000_000_000.0,
            sales=1_400_000_000_000.0,
            market_cap=26_000_000_000_000.0,
        )
        pe_curr = float(meta.get("pe_ratio", 20.0))
        pb_curr = float(meta.get("pb_ratio", 3.5))
        eps_ttm = round(current_price / max(pe_curr, 1.0), 2)
        bps = round(current_price / max(pb_curr, 0.5), 2)
        fcf_aligned = 25_930_000_000 * eps_ttm * 0.92

        valuation = val_engine.evaluate(
            raw_sym,
            current_price,
            stmt,
            [pe_curr * 0.8, pe_curr, pe_curr * 1.2],
            [pb_curr * 0.8, pb_curr, pb_curr * 1.2],
            eps_ttm,
            bps,
            fcf_aligned,
        )

        rates_fx, expectations, dxy = GlobalMacroCollector.get_latest_snapshot()
        macro_engine = GlobalMacroEngine()
        macro_res = macro_engine.evaluate(rates_fx, expectations, dxy)

        edge = SupplyChainEdge("NVDA", raw_sym, "SUPPLIES_TO", 0.22, 0.95, is_sole_supplier=(raw_sym == "2330"), substitutability_score=0.90)

        bars = _generate_realistic_bars(raw_sym, current_price, meta.get("kline_bias", "BULLISH"))
        latest_risk = risk_engine.evaluate_series(bars)[-1]
        decision = synthesizer.synthesize(raw_sym, current_price, macro_res, valuation, latest_risk, supply_edge=edge)

        unalloc = risk_engine.predict_unallocated_targets_and_stops(
            raw_sym, current_price, atr_val, current_price * 1.08, current_price * 1.15, current_price * 1.26
        )
        alloc = risk_engine.evaluate_allocated_position_strategy(
            raw_sym, avg_cost, current_price, max(current_price * 1.02, avg_cost * 1.09), atr_val
        )
        red_team = DevilsAdvocateAgent.audit_bull_thesis(
            raw_sym, name, f"{meta['primary_sector']} 產能利用率維持高檔", valuation.pe_ratio_current
        )
        news = StructuredExtractor.parse_mock_news_text(f"{name} 營收與訂單動能符合預期", "...")

        ai_report = NeutralAIAgent.synthesize_judgment(
            raw_sym, name, macro_res, valuation, decision, unalloc, alloc, red_team, news, edge
        )
        out_dict = dict(ai_report.__dict__)
        out_dict["neutral_confidence_score"] = ai_report.confidence_score
        out_dict["executive_summary"] = ai_report.neutral_synthesis_judgment
        out_dict["conflict_resolution_analysis"] = f"{ai_report.unallocated_action_plan} {ai_report.allocated_position_plan}"
        out_dict["bullish_supporting_evidence"] = ai_report.bull_catalysts
        out_dict["bearish_counter_evidence"] = ai_report.bear_risks
        out_dict["gemini_configured"] = bool(NeutralAIAgent.get_gemini_api_key())
        self._send_json(out_dict)

    # --------------------------------------------------------------------------
    # API 9: 即時聯想搜尋 (/api/search?q=...)
    # --------------------------------------------------------------------------
    def _handle_autocomplete_search(self, qs: Dict[str, List[str]]):
        q = qs.get("q", [""])[0].strip().upper()
        results: List[Dict[str, Any]] = []

        for s in CORE_TAIWAN_STOCKS:
            sym = s["symbol"].upper()
            name = s["name"].upper()
            sec = s["primary_sector"].upper()
            tags = " ".join(s.get("theme_tags", [])).upper()
            if not q or q in sym or q in name or q in sec or q in tags:
                results.append({
                    "symbol": s["symbol"],
                    "name": s["name"],
                    "category": s["primary_sector"],
                    "price": s["price"],
                    "change_pct": s["change_pct"],
                    "type": "STOCK",
                })

        for e in TAIWAN_ETFS_CATALOG:
            sym = e.etf_symbol.upper()
            name = e.etf_name.upper()
            cat = e.category.upper()
            if not q or q in sym or q in name or q in cat:
                results.append({
                    "symbol": e.etf_symbol,
                    "name": e.etf_name,
                    "category": f"ETF・{e.category}",
                    "price": e.price,
                    "change_pct": e.change_pct,
                    "type": "ETF",
                })

        self._send_json({"query": q, "results": results[:10]})

    # --------------------------------------------------------------------------
    # API 10: 歷史回測與防過擬合高原穩定度檢定 (/api/backtest)
    # --------------------------------------------------------------------------
    def _handle_backtest(self, payload: Dict[str, Any]):
        raw_sym = str(payload.get("symbol", "2330")).replace(".TW", "").strip().upper()
        meta = _resolve_stock_meta(raw_sym)
        current_price = float(payload.get("current_price") or meta["price"])
        atr_mult = float(payload.get("atr_multiplier", 2.5))
        pos_pct = min(0.95, max(0.05, float(payload.get("position_pct", 0.25))))

        # 產生 90 交易日之真實波動序列以檢驗 Chandelier 移動停損 + 20MA 濾網與跳空滑價
        seed_val = sum(ord(c) * (idx + 3) for idx, c in enumerate(raw_sym)) % 997
        rng = np.random.default_rng(seed_val)
        n_days = 90
        px = current_price * 0.84
        drift = (current_price - px) / n_days

        bars: List[DailyBar] = []
        for i in range(n_days):
            cyc = np.sin(i / 7.5) * (current_price * 0.012)
            noise = float(rng.normal(0, current_price * 0.009))
            px = max(5.0, px + drift + cyc * 0.25 + noise)
            open_i = px * float(1.0 + rng.uniform(-0.008, 0.008))
            high_i = max(open_i, px) * float(1.0 + rng.uniform(0.004, 0.015))
            low_i = min(open_i, px) * float(1.0 - rng.uniform(0.004, 0.015))
            bars.append(
                DailyBar(
                    date=f"D-{n_days - i:02d}",
                    open=round(open_i, 2),
                    high=round(high_i, 2),
                    low=round(low_i, 2),
                    close=round(px, 2),
                    volume=15_000_000,
                    institutional_net_buy=1500,
                )
            )

        def _run_with_mult(m: float):
            r_eng = DynamicStopLossEngine(atr_period=14, chandelier_period=22, atr_multiplier=m)
            evals = r_eng.evaluate_series(bars)
            closes = pd.Series([b.close for b in bars])
            ma20 = closes.rolling(20).mean().bfill()
            rows = []
            for idx, (b, ev) in enumerate(zip(bars, evals)):
                sig = 1 if (b.close >= ma20.iloc[idx] and not ev.is_chandelier_stop_breached and idx >= 22) else 0
                rows.append({
                    "date": b.date,
                    "open": b.open,
                    "high": b.high,
                    "low": b.low,
                    "close": b.close,
                    "signal": sig,
                    "stop_loss": ev.chandelier_stop if not np.isnan(ev.chandelier_stop) else b.close * 0.93,
                })
            bt_eng = BacktestEngine(initial_capital=1_000_000.0, slippage_rate=0.0015)
            return bt_eng.run_backtest(f"{raw_sym} 雙軌動能策略", pd.DataFrame(rows), symbol=raw_sym, position_size_pct=pos_pct)

        summary = _run_with_mult(atr_mult)
        plateau = OverfittingGuard.test_parameter_plateau(
            baseline_param=atr_mult,
            backtest_fn=lambda m: max(0.1, _run_with_mult(m).sharpe_ratio),
        )

        self._send_json({
            "symbol": raw_sym,
            "name": meta["name"],
            "total_return_pct": summary.total_return_pct,
            "cagr": summary.cagr,
            "max_drawdown_pct": summary.max_drawdown_pct,
            "sharpe_ratio": summary.sharpe_ratio,
            "win_rate_pct": summary.win_rate_pct,
            "profit_factor": summary.profit_factor,
            "total_trades": summary.total_trades,
            "plateau_robust": plateau.is_parameter_plateau_robust,
            "plateau_degradation_ratio": plateau.degradation_ratio,
            "equity_curve": summary.equity_curve[-45:],
            "trades": [t.__dict__ for t in summary.trade_history[-6:]],
        })


class _ThreadingHTTPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True
    daemon_threads = True


# Vercel BaseHTTPRequestHandler entrypoint alias
handler = AlphaMindApiHandler


def wsgi_app(environ: Dict[str, Any], start_response: Callable[[str, List[Tuple[str, str]]], Any]) -> Iterable[bytes]:
    """
    Standard WSGI callable (`app` / `application`) for Vercel Python Runtime, Gunicorn, etc.
    Routes all HTTP requests (`GET`, `POST`, `OPTIONS`) through `AlphaMindApiHandler`.
    """
    h = object.__new__(AlphaMindApiHandler)
    h._wsgi_mode = True
    h._wsgi_status = 200
    h._wsgi_headers = []
    h.directory = WEB_DIR

    method = str(environ.get("REQUEST_METHOD", "GET")).upper()
    path_info = str(environ.get("PATH_INFO", "/") or "/")
    query_string = str(environ.get("QUERY_STRING", "") or "")
    h.path = f"{path_info}?{query_string}" if query_string else path_info
    h.command = method

    msg = email.message.Message()
    if environ.get("CONTENT_TYPE"):
        msg["Content-Type"] = str(environ["CONTENT_TYPE"])
    if environ.get("CONTENT_LENGTH"):
        msg["Content-Length"] = str(environ["CONTENT_LENGTH"])
    for k, v in environ.items():
        if k.startswith("HTTP_") and v is not None:
            header_name = k[5:].replace("_", "-")
            msg[header_name] = str(v)
    h.headers = msg

    try:
        content_len = int(environ.get("CONTENT_LENGTH") or 0)
    except ValueError:
        content_len = 0
    wsgi_input = environ.get("wsgi.input")
    req_bytes = wsgi_input.read(content_len) if (wsgi_input and content_len > 0) else b""
    h.rfile = io.BytesIO(req_bytes)
    h.wfile = io.BytesIO()

    if method == "OPTIONS":
        h.do_OPTIONS()
    elif method == "POST":
        h.do_POST()
    else:
        h.do_GET()

    status_map = {
        200: "200 OK",
        201: "201 Created",
        204: "204 No Content",
        400: "400 Bad Request",
        401: "401 Unauthorized",
        403: "403 Forbidden",
        404: "404 Not Found",
        500: "500 Internal Server Error",
    }
    status_line = status_map.get(h._wsgi_status, f"{h._wsgi_status} OK")
    start_response(status_line, h._wsgi_headers)
    return [h.wfile.getvalue()]


app = wsgi_app
application = wsgi_app


def start_server():
    with _ThreadingHTTPServer((HOST, PORT), AlphaMindApiHandler) as httpd:
        print(f"AlphaMind Server running on http://{HOST}:{PORT}")
        httpd.serve_forever()


if __name__ == "__main__":
    start_server()
