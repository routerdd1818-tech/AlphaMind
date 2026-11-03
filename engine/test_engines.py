"""
Unit Tests and Verification Suite for AlphaMind AI Core Engines.
"""

import os
import sys
from datetime import datetime, timedelta
import numpy as np
import pandas as pd
import pytest

# Ensure project root is in sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from alphamind.engine.sector_flow_engine import SectorMoneyFlowEngine, TickData
from alphamind.engine.risk_engine import DailyBar, DynamicStopLossEngine
from alphamind.engine.supply_chain_engine import SupplyChainEdge, SupplyChainLagEngine
from alphamind.engine.macro_engine import (
    GlobalMacroEngine,
    MacroRegion,
    MonetaryPolicyStance,
    RateHikeExpectation,
    RegionalRatesAndFX,
)


def test_sector_money_flow_engine():
    total_market_cap = 60_000_000_000_000.0  # 60 兆 TWD
    engine = SectorMoneyFlowEngine(
        total_market_cap=total_market_cap,
        large_order_threshold=5_000_000.0,
        flow_ratio_threshold=1.5,
    )

    cowos_market_cap = 1_200_000_000_000.0  # 1.2 兆 TWD (佔大盤 2%)
    engine.register_sector(
        sector_id="CoWoS",
        name="CoWoS 先進封裝",
        market_cap=cowos_market_cap,
        symbols=["2330.TW", "3131.TW", "3583.TW"],
    )

    base_time = datetime(2026, 11, 2, 9, 0, 0)

    # 模擬 9:00 全市場與 CoWoS 平緩交易
    engine.process_tick(
        TickData(
            symbol="2317.TW",
            price=200.0,
            volume=50_000,
            turnover=10_000_000.0,
            bid_ask_flag=1,
            timestamp=base_time,
        )
    )
    engine.process_tick(
        TickData(
            symbol="2330.TW",
            price=1050.0,
            volume=10_000,
            turnover=10_500_000.0,
            bid_ask_flag=1,
            timestamp=base_time,
        )
    )

    # 模擬 9:06 (6分鐘後) 資金大量湧入 CoWoS (弘塑 3131 連續大單外盤敲進)
    t1 = base_time + timedelta(minutes=6)
    signals = []
    for i in range(5):
        sig = engine.process_tick(
            TickData(
                symbol="3131.TW",
                price=1850.0 + i * 10,
                volume=10_000,
                turnover=18_500_000.0,  # 單筆 1850 萬 (大單)
                bid_ask_flag=1,         # 外盤
                timestamp=t1 + timedelta(seconds=i * 2),
                is_large_order=True,
            )
        )
        signals.extend(sig)

    assert len(signals) > 0
    latest_sig = signals[-1]
    assert latest_sig.sector_id == "CoWoS"
    assert latest_sig.flow_ratio > 0.0
    assert latest_sig.turnover > 0.0
    print(f"Sector Flow Test Passed: CoWoS Flow Ratio={latest_sig.flow_ratio:.2f}, Breakout={latest_sig.is_flow_inflow_breakout}")


def test_dynamic_stop_loss_engine():
    engine = DynamicStopLossEngine(
        atr_period=14,
        chandelier_period=22,
        atr_multiplier=2.5,
        institutional_window=20,
    )

    np.random.seed(42)
    base_price = 500.0
    bars = []

    # 產生 40 天上升趨勢日 K
    for i in range(40):
        high = base_price + 8.0 + np.random.uniform(0, 5)
        low = base_price - 5.0 - np.random.uniform(0, 3)
        close = base_price + 3.0 + np.random.uniform(-2, 4)
        open_px = base_price
        inst_buy = 2000 if i % 2 == 0 else -500
        bars.append(
            DailyBar(
                date=f"2026-09-{i+1:02d}" if i < 30 else f"2026-10-{i-29:02d}",
                open=open_px,
                high=high,
                low=low,
                close=close,
                volume=10_000_000,
                institutional_net_buy=inst_buy,
                vwap=(high + low + close) / 3.0,
            )
        )
        base_price += 4.0  # 持續上漲

    # 第 41 天重挫長黑跌破停損線
    bars.append(
        DailyBar(
            date="2026-10-12",
            open=base_price - 10,
            high=base_price - 5,
            low=base_price - 80,
            close=base_price - 75,  # 急跌
            volume=25_000_000,      # 放量
            institutional_net_buy=-8000,
            vwap=base_price - 60,
        )
    )

    results = engine.evaluate_series(bars)
    assert len(results) == len(bars)

    last_res = results[-1]
    assert last_res.atr_14 > 0
    assert last_res.chandelier_stop > 0
    assert last_res.is_exit_signal_triggered is True
    print(f"Stop Loss Test Passed: Last Close={last_res.close_price:.1f}, Chandelier Stop={last_res.chandelier_stop:.1f}, Exit Triggered={last_res.is_exit_signal_triggered}")


def test_supply_chain_lag_engine():
    engine = SupplyChainLagEngine(
        leader_return_threshold=0.10,
        supplier_return_ceiling=0.02,
        min_correlation=0.70,
        correlation_window=60,
    )

    edge = SupplyChainEdge(
        leader_symbol="NVDA",
        supplier_symbol="3131.TW",
        relationship_type="SUPPLIES_TO",
        revenue_share=0.35,
        confidence=0.92,
    )

    # 模擬 60 日高度正相關歷史序列
    np.random.seed(101)
    leader_prices = [100.0]
    supplier_prices = [1000.0]

    for _ in range(55):
        shock = np.random.normal(0.002, 0.015)
        leader_prices.append(leader_prices[-1] * (1.0 + shock))
        supplier_prices.append(supplier_prices[-1] * (1.0 + shock * 0.95 + np.random.normal(0, 0.003)))

    # 最後 5 天：Leader 急拉 +15%，Supplier 滯漲 +1%
    for _ in range(5):
        leader_prices.append(leader_prices[-1] * 1.028)    # 累計約 +15%
        supplier_prices.append(supplier_prices[-1] * 1.002) # 累計約 +1%

    leader_s = pd.Series(leader_prices)
    supplier_s = pd.Series(supplier_prices)

    signal = engine.scan_opportunities(edge, leader_s, supplier_s, "2026-11-02")
    assert signal is not None
    assert signal.is_lagging_signal is True
    assert signal.historical_correlation_60d >= 0.70
    assert signal.leader_5d_return_pct >= 10.0
    assert signal.supplier_5d_return_pct <= 2.0
    assert signal.catch_up_target_price > signal.current_supplier_price
    print(f"Supply Chain Lag Test Passed: Leader 5d Ret={signal.leader_5d_return_pct}%, Supplier 5d Ret={signal.supplier_5d_return_pct}%, Catch-Up Target={signal.catch_up_target_price}")


def test_global_macro_engine():
    engine = GlobalMacroEngine()

    rates_fx = {
        MacroRegion.US: RegionalRatesAndFX(
            region=MacroRegion.US,
            central_bank_policy_rate=5.00,
            yield_2y=4.20,
            yield_10y=4.45,
            fx_rate=1.0,
            fx_change_pct_1d=0.2,
            volatility_index=17.5,
            term_structure_ratio=0.95,
        ),
        MacroRegion.TW: RegionalRatesAndFX(
            region=MacroRegion.TW,
            central_bank_policy_rate=2.00,
            yield_2y=1.35,
            yield_10y=1.65,
            fx_rate=32.25,
            fx_change_pct_1d=0.45,  # 台幣單日貶值 0.45%
            volatility_index=16.8,
            term_structure_ratio=0.98,
        ),
        MacroRegion.JP: RegionalRatesAndFX(
            region=MacroRegion.JP,
            central_bank_policy_rate=0.25,
            yield_2y=0.45,
            yield_10y=1.02,
            fx_rate=152.80,
            fx_change_pct_1d=-1.50, # 日圓大升值 1.5% (套利平倉)
            volatility_index=24.5,
            term_structure_ratio=1.10,
        ),
        MacroRegion.KR: RegionalRatesAndFX(
            region=MacroRegion.KR,
            central_bank_policy_rate=3.25,
            yield_2y=2.95,
            yield_10y=3.10,
            fx_rate=1380.0,
            fx_change_pct_1d=0.60,  # 韓元貶值
            volatility_index=19.2,
            term_structure_ratio=1.02,
        ),
        MacroRegion.HK: RegionalRatesAndFX(
            region=MacroRegion.HK,
            central_bank_policy_rate=5.00,
            yield_2y=3.85,
            yield_10y=4.05,
            fx_rate=7.77,
            fx_change_pct_1d=0.01,
            volatility_index=23.0,
            term_structure_ratio=1.04,
        ),
        MacroRegion.EU: RegionalRatesAndFX(
            region=MacroRegion.EU,
            central_bank_policy_rate=3.25,
            yield_2y=2.15,
            yield_10y=2.35,
            fx_rate=1.085,
            fx_change_pct_1d=-0.15,
            volatility_index=18.0,
            term_structure_ratio=0.97,
        ),
    }

    rate_expectations = {
        MacroRegion.US: RateHikeExpectation(
            region=MacroRegion.US,
            next_meeting_date="2026-12-16",
            prob_cut=0.75,
            prob_hold=0.25,
            prob_hike=0.0,
            implied_terminal_rate=3.75,
        ),
        MacroRegion.EU: RateHikeExpectation(
            region=MacroRegion.EU,
            next_meeting_date="2026-12-12",
            prob_cut=0.85,
            prob_hold=0.15,
            prob_hike=0.0,
            implied_terminal_rate=2.75,
        ),
        MacroRegion.JP: RateHikeExpectation(
            region=MacroRegion.JP,
            next_meeting_date="2026-12-19",
            prob_cut=0.0,
            prob_hold=0.40,
            prob_hike=0.60, # 日本有升息預期
            implied_terminal_rate=0.75,
        ),
    }

    analysis = engine.evaluate(
        rates_fx=rates_fx,
        rate_expectations=rate_expectations,
        dxy_index=105.2, # 強勢美元
    )

    assert analysis.us_yield_spread_10y_2y > 0.0
    assert analysis.is_bear_steepening is True
    assert analysis.carry_trade_unwind_risk > 50.0  # 日圓大升帶動平倉警示
    assert analysis.emerging_asia_capital_flight_risk > 50.0
    assert analysis.macro_regime_multiplier < 1.0   # 風控降部位
    assert len(analysis.key_warnings) > 0
    print(f"Global Macro Test Passed: DXY={analysis.dxy_index}, Carry Risk={analysis.carry_trade_unwind_risk}, Asia Flight Risk={analysis.emerging_asia_capital_flight_risk}, Regime Mult={analysis.macro_regime_multiplier}")
    print(f"Key Warnings: {analysis.key_warnings}")


if __name__ == "__main__":
    test_sector_money_flow_engine()
    test_dynamic_stop_loss_engine()
    test_supply_chain_lag_engine()
    test_global_macro_engine()
    print("All engine prototype tests executed successfully!")

