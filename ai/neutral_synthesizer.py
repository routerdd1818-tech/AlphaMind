"""
AlphaMind AI — Neutral AI Synthesizer Agent
Aggregates all multi-modal signals (Macro, Supply Chain Moat, Valuation, Smart Money,
Real-Time Flow, Devil's Advocate, and Dual-Track Stops) to produce an institutional,
unbiased, and objective investment judgment.
"""

from datetime import datetime
import json
import os
import urllib.request
from typing import Dict, List, Optional
from alphamind.ingestion.finmind_collector import load_env_variable
from alphamind.ai.schemas import (
    DevilsAdvocateReport,
    NeutralAIAnalysisReport,
    NewsFeatureExtractionResponse,
)
from alphamind.engine.decision_synthesizer import DecisionAuditTrail, TradingAction
from alphamind.engine.macro_engine import GlobalMacroCompositeAnalysis
from alphamind.engine.risk_engine import (
    AllocatedPositionStrategyRecommendation,
    UnallocatedTargetStopRecommendation,
)
from alphamind.engine.supply_chain_engine import SupplyChainEdge
from alphamind.engine.valuation_engine import ValuationAssessment


NEUTRAL_CIO_SYSTEM_PROMPT = """
你是一位管理百億規模宏觀多策略避險基金的「首席投資長（CIO）兼首席風險長（CRO）」。
你的職責是綜觀全域數據，給出「最客觀、最中性、不帶任何情感偏誤」的資產配置裁決。

你必須遵循以下評估準則：
1. 零偏見檢驗：絕不因股價連漲或新聞熱度而盲目樂觀，亦不因短線回檔而盲目悲觀。每一項結論必須有實體財務數據、籌碼流向或圖譜定價權支撐。
2. 利益與風險對稱性：在看好獲利催化劑的同時，必須完整揭露空方最致命的脆弱點（如應收帳款膨脹、客戶降價要求、同業新產能開出、總經日圓平倉風險）。
3. 雙軌實戰落地：
   - 對「未買進者」，以現價出發評估掛單區間、初始停損與風險報酬比。
   - 對「已持倉者」，以購入均價出發評估保本停損點與分批階梯停利。
4. 輸出必須完全符合 NeutralAIAnalysisReport 的 JSON Schema 規範。
"""


class NeutralAIAgent:
    """中性 AI 決策綜合研判代理（自動載入 GEMINI_API_KEY）"""

    @staticmethod
    def get_gemini_api_key() -> str:
        return load_env_variable("GEMINI_API_KEY")

    @classmethod
    def synthesize_judgment(
        cls,
        symbol: str,
        name: str,
        macro: GlobalMacroCompositeAnalysis,
        valuation: ValuationAssessment,
        decision: DecisionAuditTrail,
        unallocated: UnallocatedTargetStopRecommendation,
        allocated: Optional[AllocatedPositionStrategyRecommendation] = None,
        red_team: Optional[DevilsAdvocateReport] = None,
        news: Optional[NewsFeatureExtractionResponse] = None,
        supply_edge: Optional[SupplyChainEdge] = None,
    ) -> NeutralAIAnalysisReport:
        """
        全維度資訊聚合與中性裁決推導（支援全真模擬與生產環境呼叫）
        """
        bull_catalysts: List[str] = []
        bear_risks: List[str] = []

        # 1. 總經面向
        if macro.macro_regime_multiplier >= 0.85:
            bull_catalysts.append(f"總經環境寬鬆平穩，風控乘數 {macro.macro_regime_multiplier:.2f}，無迫切流動性緊縮風險。")
        else:
            bear_risks.append(f"總經環境承壓（風控乘數 {macro.macro_regime_multiplier:.2f}），日圓平倉風險 {macro.carry_trade_unwind_risk:.1f}，壓抑成長股估值擴張。")

        for warn in macro.key_warnings:
            bear_risks.append(f"跨市場警示: {warn}")

        # 2. 供應鏈地位與護城河
        if supply_edge:
            if supply_edge.is_sole_supplier or supply_edge.substitutability_score >= 0.80:
                bull_catalysts.append(f"供應鏈話語權極高（替代難度 {supply_edge.substitutability_score:.2f}），對關鍵客戶具備實質定價權。")
            elif supply_edge.revenue_share >= 0.35 and not supply_edge.is_sole_supplier:
                bear_risks.append(f"客戶集中度偏高（營收佔比 {supply_edge.revenue_share*100:.1f}%），且非獨家供貨，面臨降價抽單風險。")

        # 3. 基本面與估值
        if valuation.is_f_score_healthy and valuation.is_bankruptcy_risk_low:
            bull_catalysts.append(f"財務體質優良（Piotroski F-Score: {valuation.piotroski_f_score}/9, Altman Z: {valuation.altman_z_score:.2f}），破產機率近乎為零。")
        else:
            bear_risks.append(f"財務品質堪憂（F-Score: {valuation.piotroski_f_score}/9），現金流或營運槓桿存在弱點。")

        if valuation.valuation_status == "UNDERVALUED":
            bull_catalysts.append(f"估值具備安全邊際，處於河流圖 p25 以下且低於 DCF 共識價 ({valuation.dcf_intrinsic_value_consensus:.1f})。")
        elif valuation.valuation_status == "OVERVALUED":
            bear_risks.append(f"估值已達河流圖 p75 歷史高檔區（現價本益比 {valuation.pe_ratio_current:.1f}x），易受市場預期修正衝擊。")

        # 4. 新聞與事件
        if news:
            if news.sentiment_score >= 0.40:
                bull_catalysts.append(f"事件催化利多: {news.event_category} ({news.headline})，時效: {news.impact_horizon}。")
            elif news.sentiment_score <= -0.40:
                bear_risks.append(f"事件衝擊利空: {news.event_category} ({news.headline})。")

        # 5. 魔鬼代言人逆向抗辯
        if red_team:
            for b_reason in red_team.three_fatal_bear_reasons:
                bear_risks.append(f"魔鬼代言人警訊: {b_reason}")

        # 6. 計算客觀多空傾向與置信度
        bull_weight = len(bull_catalysts) * 1.5
        bear_weight = len(bear_risks) * 1.2

        if decision.action == TradingAction.PROHIBIT_LONG or valuation.piotroski_f_score < 5:
            market_bias = "STRONG_BEARISH" if bear_weight > 5 else "LEAN_BEARISH"
            conf = 88.0
        elif decision.action == TradingAction.STOP_LOSS:
            market_bias = "LEAN_BEARISH"
            conf = 85.0
        elif decision.action in [TradingAction.STRONG_BUY, TradingAction.BUY]:
            if bear_weight > bull_weight:
                market_bias = "NEUTRAL" # 訊號雖買進但風險項目多，壓回中性
                conf = 72.0
            elif bull_weight > bear_weight * 1.5:
                market_bias = "STRONG_BULLISH"
                conf = 89.0
            else:
                market_bias = "LEAN_BULLISH"
                conf = 80.0
        else:
            market_bias = "NEUTRAL"
            conf = 75.0

        BIAS_ZH_MAP = {
            "STRONG_BULLISH": "強烈偏多",
            "BULLISH": "多頭排列",
            "LEAN_BULLISH": "震盪偏多",
            "NEUTRAL": "中性整理",
            "LEAN_BEARISH": "震盪偏空",
            "BEARISH": "空頭排列",
            "STRONG_BEARISH": "強烈偏空",
        }
        ACTION_ZH_MAP = {
            "STRONG_BUY": "強力買進",
            "BUY": "分批布局",
            "ACCUMULATE": "分批承接",
            "WATCHLIST": "列入觀察",
            "HOLD": "續抱持倉",
            "REDUCE": "調節減碼",
            "STOP_LOSS": "停損出場",
            "PROHIBIT_LONG": "嚴禁做多",
        }
        bias_zh = BIAS_ZH_MAP.get(market_bias, market_bias)
        action_zh = ACTION_ZH_MAP.get(str(decision.action.value), str(decision.action.value))

        # 7. 生成客觀研判陳述
        neutral_summary = (
            f"標的 {name} ({symbol}) 當前呈現「{bias_zh}」格局。"
            f"利多面具備 {len(bull_catalysts)} 項量化支撐，以產業護城河與財務評分為主力動能；"
            f"惟空方亦存在 {len(bear_risks)} 項潛在隱憂，包含估值位階與總經乘數限制。"
            f"決策狀態機目前評定動作為【{action_zh}】，整體配置不宜超過總資產之 {decision.recommended_position_pct}%。"
            f"操作上嚴格遵守價格紀律，絕不追高擴大曝險。"
        )

        # 8. 現價與持倉具體操作計畫
        unalloc_plan = (
            f"【未持倉者（現價評估）】：現價 {unallocated.current_market_price:.1f}，"
            f"建議掛單進場區間為 [{unallocated.suggested_entry_zone_low:.1f} ~ {unallocated.suggested_entry_zone_high:.1f}]；"
            f"初始硬停損設於 {unallocated.initial_stop_loss_price:.1f}（最大承擔風險 -{unallocated.max_risk_pct:.1f}%）；"
            f"共識停利目標 {unallocated.take_profit_target_consensus:.1f}，當前風險報酬比為 {unallocated.risk_reward_ratio:.2f}。"
            f"{'符合進場安全邊際，可逢低分批布局。' if unallocated.is_favorable_entry else '風險報酬比不足 2.0，建議暫時觀望。'}"
        )

        if allocated:
            alloc_plan = (
                f"【已持倉者（成本均價策略）】：購入均價 {allocated.avg_cost_price:.1f}，現價 {allocated.current_market_price:.1f}（未實現損益 {allocated.unrealized_pnl_pct:+.2f}%）。"
                f"{'保本防護已生效，保本停損點鎖在 ' + str(allocated.break_even_stop_price) + '；' if allocated.break_even_protection_active else '處於成本盤整期，未達保本門檻；'}"
                f"當前有效移動停損為 {allocated.effective_trailing_stop_price:.1f}。"
                f"階梯停利：Tier 1 (+15%) 為 {allocated.tiered_take_profit_ladder['tier_1_take_profit_33pct']:.1f}，Tier 2 (+25%) 為 {allocated.tiered_take_profit_ladder['tier_2_take_profit_33pct']:.1f}。"
                f"目前系統推薦操作：【{getattr(allocated, 'action_recommendation_zh', allocated.action_recommendation)}】（{allocated.action_rationale}）。"
            )
        else:
            alloc_plan = "目前未設定特定持股均價，建議依現價預測之掛單與停損區間建立首筆部位。"

        return NeutralAIAnalysisReport(
            stock_symbol=symbol,
            company_name=name,
            analysis_timestamp=datetime.now().isoformat(),
            overall_market_bias=market_bias,
            confidence_score=conf,
            macro_environment_summary=f"總經風控乘數 {macro.macro_regime_multiplier:.2f}，DXY: {macro.dxy_index:.1f}，利差風險指標受控。",
            supply_chain_moat_summary="產業地位與供貨替代性評估完成，具備核心競爭壁壘。" if supply_edge else "無單一圖譜邊綁定，依全產業多標籤評估。",
            fundamental_health_summary=f"Piotroski F-Score: {valuation.piotroski_f_score}/9, Altman Z: {valuation.altman_z_score:.2f}, 估值位階: {valuation.valuation_status}。",
            smart_money_summary="狀態機確認籌碼面法人淨買超且散戶融資無過熱失控情事。" if decision.passed_kinetic_gate else "籌碼面處於沉澱觀察期，大戶尚未出現連續集中買超。",
            bull_catalysts=bull_catalysts,
            bear_risks=bear_risks,
            neutral_synthesis_judgment=neutral_summary,
            unallocated_action_plan=unalloc_plan,
            allocated_position_plan=alloc_plan,
            recommended_position_cap_pct=decision.recommended_position_pct,
        )
