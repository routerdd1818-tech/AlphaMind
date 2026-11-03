"""
AlphaMind AI — Quantitative Web API & Static File Server
Supports:
- Viewport-Aware On-Demand Real-Time Quote Polling (/api/quotes/batch)
- Taiwan Full Stock Universe, Sector/Theme Classification & Multi-Factor Screener (/api/screener)
- Taiwan Full ETF Zone: Constituents, Multi-Period Returns & Reverse Lookup (/api/etfs)
- Asset Calculator, Watchlist, Position Calculator & Price/Pattern Smart Alerts (/api/portfolio, /api/portfolio/action)
- Stock Analysis with K-Line Candlestick Pattern Recognition, Dual-Track Stops & Neutral AI (/api/stock-analysis, /api/dual-stops, /api/ai-synthesis)
"""

import http.server
import json
import os
import socketserver
import sys
import urllib.parse
from datetime import datetime
from typing import Any, Dict, List
import numpy as np

# Ensure workspace root is in sys.path
WORKSPACE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if WORKSPACE_ROOT not in sys.path:
    sys.path.insert(0, WORKSPACE_ROOT)

from alphamind.ingestion.macro_collector import GlobalMacroCollector
from alphamind.engine.macro_engine import GlobalMacroEngine
from alphamind.engine.risk_engine import DailyBar, DynamicStopLossEngine
from alphamind.engine.valuation_engine import FinancialStatementData, ValuationEngine
from alphamind.engine.decision_synthesizer import DecisionSynthesizer
from alphamind.engine.supply_chain_engine import SupplyChainEdge
from alphamind.engine.pattern_engine import CandlestickPatternEngine
from alphamind.engine.tw_market_universe import (
    CORE_TAIWAN_STOCKS,
    TAIWAN_ETFS_CATALOG,
    TaiwanMarketUniverseEngine,
)
from alphamind.engine.portfolio_alert_engine import PortfolioAndAlertEngine
from alphamind.engine.fugle_adapter import FugleMarketDataClient, load_fugle_credentials
from alphamind.ai.devils_advocate import DevilsAdvocateAgent
from alphamind.ai.structured_extractor import StructuredExtractor
from alphamind.ai.neutral_synthesizer import NeutralAIAgent


WEB_DIR = os.path.dirname(os.path.abspath(__file__))
PORT = 8888


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
UNIVERSE_ENGINE = TaiwanMarketUniverseEngine()
PORTFOLIO_ENGINE = PortfolioAndAlertEngine()
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
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=WEB_DIR, **kwargs)

    def log_message(self, format: str, *args: Any) -> None:
        # Keep console clean while serving rapid viewport polls
        pass

    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        qs = urllib.parse.parse_qs(parsed.query)

        if parsed.path == "/api/overview":
            self._handle_overview()
        elif parsed.path == "/api/stocks":
            self._handle_stocks_list()
        elif parsed.path == "/api/screener":
            self._handle_screener(qs)
        elif parsed.path == "/api/sectors":
            self._handle_sectors()
        elif parsed.path == "/api/etfs":
            self._handle_etfs(qs)
        elif parsed.path == "/api/portfolio":
            self._handle_portfolio_get()
        elif parsed.path == "/api/quotes/batch":
            self._handle_batch_quotes(qs)
        else:
            super().do_GET()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        content_len = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_len).decode("utf-8") if content_len > 0 else "{}"
        try:
            payload = json.loads(body)
        except Exception:
            payload = {}

        if parsed.path == "/api/stock-analysis":
            self._handle_stock_analysis(payload)
        elif parsed.path == "/api/dual-stops":
            self._handle_dual_stops(payload)
        elif parsed.path == "/api/ai-synthesis":
            self._handle_ai_synthesis(payload)
        elif parsed.path == "/api/portfolio/action":
            self._handle_portfolio_action(payload)
        else:
            self.send_response(404)
            self.end_headers()

    def _send_json(self, data: Any):
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))

    # --------------------------------------------------------------------------
    # API 1: 全局戰情 (6國總經燈號 + 產業/概念資金流向排行)
    # --------------------------------------------------------------------------
    def _handle_overview(self):
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
    # --------------------------------------------------------------------------
    def _handle_portfolio_get(self):
        self._send_json(PORTFOLIO_ENGINE.evaluate_portfolio_and_alerts(UNIVERSE_ENGINE))

    def _handle_portfolio_action(self, payload: Dict[str, Any]):
        action = payload.get("action", "")
        if action == "update_cash":
            PORTFOLIO_ENGINE.update_cash_and_settings(
                cash_twd=payload.get("cash_twd"),
                fee_discount=payload.get("fee_discount"),
            )
        elif action == "upsert_position":
            sym = str(payload.get("symbol", "2330")).strip().upper()
            meta = _resolve_stock_meta(sym)
            PORTFOLIO_ENGINE.upsert_position(
                symbol=sym,
                name=str(payload.get("name") or meta["name"]),
                shares=int(payload.get("shares", 1000)),
                avg_cost_price=float(payload.get("avg_cost_price", meta["price"])),
                custom_target_price=float(payload["custom_target_price"]) if payload.get("custom_target_price") else None,
                custom_stop_price=float(payload["custom_stop_price"]) if payload.get("custom_stop_price") else None,
                notes=str(payload.get("notes", "")),
            )
        elif action == "remove_position":
            PORTFOLIO_ENGINE.remove_position(str(payload.get("symbol", "")))
        elif action == "add_watchlist":
            sym = str(payload.get("symbol", "2330")).strip().upper()
            meta = _resolve_stock_meta(sym)
            PORTFOLIO_ENGINE.add_watchlist_item(
                symbol=sym,
                name=str(payload.get("name") or meta["name"]),
                target_buy_price=float(payload["target_buy_price"]) if payload.get("target_buy_price") else None,
            )
        elif action == "remove_watchlist":
            PORTFOLIO_ENGINE.remove_watchlist_item(str(payload.get("symbol", "")))

        self._send_json(PORTFOLIO_ENGINE.evaluate_portfolio_and_alerts(UNIVERSE_ENGINE))

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
        self._send_json(ai_report.__dict__)


def start_server():
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("", PORT), AlphaMindApiHandler) as httpd:
        print(f"AlphaMind Server running on http://localhost:{PORT}")
        httpd.serve_forever()


if __name__ == "__main__":
    start_server()
