"""
AlphaMind AI — End-to-End Pipeline Integration & Logic Verification Test Suite
Verifies the complete flow across Data Ingestion, Valuation, AI Schemas,
State Machine Decision Synthesizer, Dynamic Stop-Loss, and Backtest Metrics.
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

from alphamind.ingestion.finmind_collector import FinMindCollector
from alphamind.ingestion.macro_collector import GlobalMacroCollector
from alphamind.engine.macro_engine import GlobalMacroEngine, MacroRegion
from alphamind.engine.sector_flow_engine import SectorMoneyFlowEngine, TickData
from alphamind.engine.risk_engine import DailyBar, DynamicStopLossEngine
from alphamind.engine.supply_chain_engine import SupplyChainEdge, SupplyChainLagEngine
from alphamind.engine.valuation_engine import FinancialStatementData, ValuationEngine
from alphamind.engine.decision_synthesizer import DecisionSynthesizer, TradingAction
from alphamind.engine.backtest_engine import BacktestEngine
from alphamind.engine.overfitting_guard import OverfittingGuard
from alphamind.ai.structured_extractor import StructuredExtractor
from alphamind.ai.devils_advocate import DevilsAdvocateAgent
from alphamind.ai.neutral_synthesizer import NeutralAIAgent


def test_end_to_end_pipeline():
    print("\n=== STEP 1: 總經資料採集與跨市場風控評估 ===")
    rates_fx, expectations, dxy = GlobalMacroCollector.get_latest_snapshot(dxy_override=104.2, jpy_shock_pct=-0.5)
    macro_engine = GlobalMacroEngine()
    macro_result = macro_engine.evaluate(rates_fx, expectations, dxy)

    assert macro_result.dxy_index == 104.2
    assert 0.2 <= macro_result.macro_regime_multiplier <= 1.2
    print(f"總經部位乘數: {macro_result.macro_regime_multiplier}, 警示清單: {macro_result.key_warnings}")

    print("\n=== STEP 2: 基本面財報體質與河流圖估值 ===")
    val_engine = ValuationEngine()
    sample_stmt = FinancialStatementData(
        net_income=350_000_000_000.0,
        operating_cash_flow=420_000_000_000.0, # 營業現金流大於淨利
        total_assets_current=2_500_000_000_000.0,
        total_assets_prior=2_200_000_000_000.0,
        long_term_debt_current=300_000_000_000.0,
        long_term_debt_prior=320_000_000_000.0, # 長債下降
        current_assets_current=900_000_000_000.0,
        current_liabilities_current=450_000_000_000.0,
        current_assets_prior=800_000_000_000.0,
        current_liabilities_prior=450_000_000_000.0,
        shares_outstanding_current=25_930_000_000,
        shares_outstanding_prior=25_930_000_000,
        gross_margin_current=54.5,
        gross_margin_prior=53.0, # 毛利改善
        asset_turnover_current=0.55,
        asset_turnover_prior=0.52,
        ebit=400_000_000_000.0,
        total_liabilities=800_000_000_000.0,
        retained_earnings=1_200_000_000_000.0,
        sales=1_400_000_000_000.0,
        market_cap=26_000_000_000_000.0,
    )

    valuation = val_engine.evaluate(
        symbol="2330.TW",
        current_price=1050.0,
        statement=sample_stmt,
        historical_pes=[15.0, 18.0, 22.0, 26.0, 30.0],
        historical_pbs=[3.5, 4.5, 5.5, 6.5, 7.5],
        eps=45.0,
        bps=210.0,
        fcf=380_000_000_000.0,
    )

    assert valuation.piotroski_f_score >= 7, f"Expected F-Score >= 7, got {valuation.piotroski_f_score}"
    assert valuation.altman_z_score > 3.0, f"Expected safe Altman Z, got {valuation.altman_z_score}"
    assert valuation.is_f_score_healthy is True
    print(f"Piotroski F-Score: {valuation.piotroski_f_score}/9, Altman Z: {valuation.altman_z_score}, DCF共識: {valuation.dcf_intrinsic_value_consensus}")

    print("\n=== STEP 3: AI 結構化特徵抽取與魔鬼代言人逆向審查 ===")
    sc_res = StructuredExtractor.parse_mock_supply_chain_text("年報文字", reporting_company="台積電")
    assert len(sc_res.edges) > 0
    assert sc_res.edges[0].supplier_symbol == "3131.TW"

    news_res = StructuredExtractor.parse_mock_news_text("台積電擴產 CoWoS 先進封裝大增", "內容...")
    assert news_res.sentiment_score > 0.5
    assert news_res.event_category == "CAPEX_EXPANSION"

    red_team = DevilsAdvocateAgent.audit_bull_thesis(
        symbol="2330.TW",
        name="台積電",
        bull_thesis="先進製程獨家壟斷且 AI 晶片需求爆發",
        pe_ratio=23.3,
        margin_debt_high=False,
        receivables_stretched=False,
    )
    assert len(red_team.three_fatal_bear_reasons) == 3
    print(f"魔鬼代言人評級: {red_team.red_team_verdict}, 致命理由1: {red_team.three_fatal_bear_reasons[0]}")

    print("\n=== STEP 4: 階層式決策狀態機 (Decision Synthesizer) 邏輯驗證 ===")
    synthesizer = DecisionSynthesizer(base_position_size_pct=15.0)

    # 模擬 40 天 K 線以計算風控停損
    risk_engine = DynamicStopLossEngine(atr_period=14, chandelier_period=22)
    sample_bars = [
        DailyBar(
            date=f"2026-10-{i+1:02d}",
            open=1000.0 + i * 2,
            high=1015.0 + i * 2,
            low=995.0 + i * 2,
            close=1010.0 + i * 2,
            volume=20_000_000,
            institutional_net_buy=3000,
        )
        for i in range(25)
    ]
    risk_evals = risk_engine.evaluate_series(sample_bars)
    latest_risk = risk_evals[-1]

    # 情境 A: 四維共振健全標的 -> 輸出 BUY / STRONG_BUY
    decision_healthy = synthesizer.synthesize(
        symbol="2330.TW",
        current_price=1050.0,
        macro_analysis=macro_result,
        valuation=valuation,
        risk_eval=latest_risk,
        is_inst_net_buying_5d=True,
        is_margin_overheated=False,
    )
    assert decision_healthy.action in [TradingAction.STRONG_BUY, TradingAction.BUY]
    assert decision_healthy.passed_health_gate is True
    assert decision_healthy.recommended_position_pct > 0.0
    print(f"情境 A 決策: {decision_healthy.action}, 建議建倉部位: {decision_healthy.recommended_position_pct}%, 停損價: {decision_healthy.stop_loss_price}")

    # 情境 B: 基本面地雷股 (F-Score 3分, 破產警戒) -> 強制拒絕做多 PROHIBIT_LONG
    bad_stmt = FinancialStatementData(
        net_income=-50_000_000.0, # 虧損
        operating_cash_flow=-80_000_000.0,
        total_assets_current=500_000_000.0,
        total_assets_prior=550_000_000.0,
        long_term_debt_current=300_000_000.0,
        long_term_debt_prior=200_000_000.0, # 負債大增
        current_assets_current=100_000_000.0,
        current_liabilities_current=200_000_000.0,
        current_assets_prior=120_000_000.0,
        current_liabilities_prior=150_000_000.0,
        shares_outstanding_current=100_000_000,
        shares_outstanding_prior=80_000_000, # 增資印股票
        gross_margin_current=10.0,
        gross_margin_prior=15.0, # 毛利崩跌
        asset_turnover_current=0.3,
        asset_turnover_prior=0.4,
        ebit=-30_000_000.0,
        total_liabilities=400_000_000.0,
        retained_earnings=-100_000_000.0,
        sales=150_000_000.0,
        market_cap=200_000_000.0,
    )
    bad_valuation = val_engine.evaluate("TRASH.TW", 20.0, bad_stmt, [10.0], [1.0], -0.5, 5.0, -80_000_000.0)
    decision_trash = synthesizer.synthesize("TRASH.TW", 20.0, macro_result, bad_valuation, latest_risk)
    assert decision_trash.action == TradingAction.PROHIBIT_LONG
    assert decision_trash.passed_health_gate is False
    assert decision_trash.recommended_position_pct == 0.0
    print(f"情境 B 決策: {decision_trash.action}, 拒絕理由: {decision_trash.rejection_reason}")

    # 情境 C: 觸及停損線出場 -> 輸出 STOP_LOSS
    stop_risk = latest_risk
    stop_risk.is_exit_signal_triggered = True
    stop_risk.exit_reason = "CHANDELIER_VOLATILITY_STOP_BREACH"
    decision_stop = synthesizer.synthesize("2330.TW", 950.0, macro_result, valuation, stop_risk)
    assert decision_stop.action == TradingAction.STOP_LOSS
    assert decision_stop.is_stop_loss_triggered is True
    assert decision_stop.recommended_position_pct == 0.0
    print(f"情境 C 決策: {decision_stop.action}, 理由: {decision_stop.rejection_reason}")

    print("\n=== STEP 5: 策略回測引擎指標運算 ===")
    backtester = BacktestEngine(initial_capital=10_000_000.0)
    # 產生 100 日回測行情
    backtest_data = []
    px = 100.0
    for i in range(100):
        px = px * (1.0 + (0.008 if i < 70 else -0.015))
        sig = 1 if i < 70 else 0
        backtest_data.append({
            "date": f"2026-01-{(i%28)+1:02d}",
            "close": px,
            "high": px * 1.02,
            "low": px * 0.98,
            "signal": sig,
            "stop_loss": px * 0.93,
        })
    bt_summary = backtester.run_backtest("動能突破+移動停損", pd.DataFrame(backtest_data), "TEST_STOCK")
    assert bt_summary.final_equity > 0
    assert bt_summary.total_trades > 0
    assert bt_summary.max_drawdown_pct >= 0.0
    print(f"回測摘要: 總報酬={bt_summary.total_return_pct}%, 最大回撤={bt_summary.max_drawdown_pct}%, 勝率={bt_summary.win_rate_pct}%, 交易筆數={bt_summary.total_trades}")

    print("\n=== STEP 6: 過擬合防禦與 Point-in-Time 審查 ===")
    # 測試 1: 檢驗財報發布日時間戳洩漏 (Lookahead Leakage)
    test_evaluations = [
        {"decision_date": "2026-06-01", "report_year": 2026, "report_quarter": 1}, # 合法 (Q1在5/15已公告)
        {"decision_date": "2026-04-10", "report_year": 2026, "report_quarter": 1}, # 違法 (4/10尚未公告Q1)
    ]
    audit_rep = OverfittingGuard.audit_point_in_time_integrity(test_evaluations)
    assert audit_rep.lookahead_violations_count == 1
    assert audit_rep.is_point_in_time_clean is False
    print(f"先見偏差稽核成功抓出違規: {audit_rep.violations[0]}")

    # 測試 2: 計算 Deflated Sharpe Ratio (DSR)
    np.random.seed(42)
    fake_daily_returns = list(np.random.normal(0.001, 0.015, 252)) # 年化 Sharpe ~ 1.05
    dsr_rep = OverfittingGuard.calculate_deflated_sharpe_ratio(fake_daily_returns, number_of_trials=100)
    assert dsr_rep.observed_sharpe > 0
    print(f"Deflated Sharpe: 觀測 Sharpe={dsr_rep.observed_sharpe}, DSR機率={dsr_rep.deflated_sharpe_ratio}, 100組試驗下顯著={dsr_rep.is_statistically_significant}")

    # 測試 3: 參數高原穩定度測試 (Parameter Plateau Test)
    def dummy_backtest(param_val: float) -> float:
        # 模擬高原形態：基準 2.5，鄰近區間平穩微幅變化
        return 1.8 - abs(param_val - 2.5) * 0.15

    plateau_rep = OverfittingGuard.test_parameter_plateau(2.5, dummy_backtest)
    assert plateau_rep.is_parameter_plateau_robust is True
    print(f"參數高原穩定性檢測通過: 衰退比={plateau_rep.degradation_ratio} >= 0.70")

    print("\n=== STEP 7: 停利停損雙軌劃分（現價預測 vs 持倉均價策略）===")
    # A. 現價進場預測
    unalloc_rec = risk_engine.predict_unallocated_targets_and_stops(
        symbol="2330.TW",
        current_price=1050.0,
        atr_14=20.0,
        conservative_target=1120.0,
        consensus_target=1200.0,
        optimistic_target=1350.0,
        support_level=1020.0,
    )
    assert unalloc_rec.initial_stop_loss_price < 1050.0
    assert unalloc_rec.risk_reward_ratio >= 2.0
    assert unalloc_rec.is_favorable_entry is True
    print(f"現價預測: 現價={unalloc_rec.current_market_price}, 建議買進區間=[{unalloc_rec.suggested_entry_zone_low}, {unalloc_rec.suggested_entry_zone_high}], 初始停損={unalloc_rec.initial_stop_loss_price}, 風險報酬比={unalloc_rec.risk_reward_ratio}")

    # B. 持倉均價策略推薦 (獲利達標 +18%，已超過保本門檻 +8%)
    alloc_rec = risk_engine.evaluate_allocated_position_strategy(
        symbol="2330.TW",
        avg_cost_price=900.0,     # 購入均價 900
        current_price=1065.0,     # 現價 1065 (+18.3%)
        highest_price_since_entry=1080.0,
        atr_14=20.0,
        holding_days=18,
    )
    assert alloc_rec.unrealized_pnl_pct > 15.0
    assert alloc_rec.break_even_protection_active is True
    assert alloc_rec.break_even_stop_price == 909.0 # 成本 * 1.01 保本
    assert alloc_rec.action_recommendation == "TAKE_PROFIT_TIER_1" # 達到 +15% 減碼 1/3
    print(f"持倉策略: 成本均價={alloc_rec.avg_cost_price}, 現價={alloc_rec.current_market_price}, 未實現損益={alloc_rec.unrealized_pnl_pct}%, 保本線={alloc_rec.break_even_stop_price}, 有效停損={alloc_rec.effective_trailing_stop_price}, 推薦動作={alloc_rec.action_recommendation}")

    print("\n=== STEP 8: AI 首席投資長 (CIO) 中性全域綜合裁決 ===")
    sample_edge = SupplyChainEdge(
        leader_symbol="NVDA",
        supplier_symbol="2330.TW",
        relationship_type="SUPPLIES_TO",
        revenue_share=0.15,
        confidence=0.98,
        is_sole_supplier=True,
        substitutability_score=0.95,
    )
    ai_report = NeutralAIAgent.synthesize_judgment(
        symbol="2330.TW",
        name="台積電",
        macro=macro_result,
        valuation=valuation,
        decision=decision_healthy,
        unallocated=unalloc_rec,
        allocated=alloc_rec,
        red_team=red_team,
        news=news_res,
        supply_edge=sample_edge,
    )

    assert ai_report.overall_market_bias in ["STRONG_BULLISH", "LEAN_BULLISH", "NEUTRAL"]
    assert len(ai_report.bull_catalysts) >= 2
    assert len(ai_report.bear_risks) >= 2 # 確保空方風險完整揭露，絕無單向偏坦
    assert ai_report.confidence_score >= 70.0
    print(f"AI 中性研判結論: 多空傾向={ai_report.overall_market_bias}, 置信度={ai_report.confidence_score}%")
    print(f"做多催化劑數量: {len(ai_report.bull_catalysts)}, 揭露空方風險數量: {len(ai_report.bear_risks)}")
    print(f"中性裁決內文:\n{ai_report.neutral_synthesis_judgment}")
    print(f"現價進場指引:\n{ai_report.unallocated_action_plan}")
    print(f"持倉均價指引:\n{ai_report.allocated_position_plan}")

    print("\n>>> 全管線端到端驗證全部通過，無邏輯矛盾與型別錯誤！<<<")




if __name__ == "__main__":
    test_end_to_end_pipeline()
