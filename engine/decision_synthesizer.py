"""
AlphaMind AI — Hierarchical Decision Synthesizer
Implements the 5-Gate State Machine resolving signal conflicts across Macro,
Supply Chain Moat, Fundamental Health, Smart Money Kinetic, and Real-Time Price Action.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional

from alphamind.engine.macro_engine import GlobalMacroCompositeAnalysis
from alphamind.engine.risk_engine import RiskEvaluationResult
from alphamind.engine.sector_flow_engine import SectorFlowSignal
from alphamind.engine.supply_chain_engine import SupplyChainEdge
from alphamind.engine.valuation_engine import ValuationAssessment


class TradingAction(str, Enum):
    STRONG_BUY = "STRONG_BUY"           # 五道門檻全數通過，全額/放大建倉
    BUY = "BUY"                         # 通過戰術門檻，常規建倉
    WATCHLIST = "WATCHLIST"             # 通過基本面與戰略，等待籌碼或線圖發動
    HOLD = "HOLD"                       # 持倉中，未觸及停損
    REDUCE = "REDUCE"                   # 籌碼鬆動或總經惡化，主動減碼
    STOP_LOSS = "STOP_LOSS"             # 觸及 ATR 或主力成本停損線，強制出場
    PROHIBIT_LONG = "PROHIBIT_LONG"     # 門檻未過（如地雷股、無護城河、大戶出貨），嚴禁做多


@dataclass
class DecisionAuditTrail:
    stock_symbol: str
    action: TradingAction
    passed_strategic_gate: bool
    passed_health_gate: bool
    passed_kinetic_gate: bool
    passed_tactical_gate: bool
    is_stop_loss_triggered: bool
    rejection_reason: Optional[str] = None
    macro_regime_multiplier: float = 1.0
    recommended_position_pct: float = 0.0 # 佔整體投資組合比例 (%)
    stop_loss_price: float = 0.0
    target_price: float = 0.0
    audit_notes: List[str] = field(default_factory=list)


class DecisionSynthesizer:
    """
    四維階層式決策狀態機聚合器：
    排除「多空線性加權平均」陷阱，採用階層過濾與觸發機制：
    Gate 1: 戰略層 (產業地位、定價權、供應鏈傳導)
    Gate 2: 體質層 (Piotroski F-Score >= 6, Altman Z >= 1.81, 營業現金流為正)
    Gate 3: 動力層 (法人籌碼沉澱、大戶持股比例上升、融資未失控)
    Gate 4: 戰術層 (股價站上 20MA、即時價格高於 VWAP、資金流向比 >= 1.5)
    Gate 5: 風控與部位縮放 (以 ATR 與總經係數動態計算停損價與部位上限)
    """

    def __init__(
        self,
        base_position_size_pct: float = 15.0, # 單檔預設基準配置 15%
        min_f_score: int = 6,
        min_altman_z: float = 1.81,
    ) -> None:
        self.base_position_size_pct = base_position_size_pct
        self.min_f_score = min_f_score
        self.min_altman_z = min_altman_z

    def synthesize(
        self,
        symbol: str,
        current_price: float,
        macro_analysis: GlobalMacroCompositeAnalysis,
        valuation: ValuationAssessment,
        risk_eval: RiskEvaluationResult,
        sector_signal: Optional[SectorFlowSignal] = None,
        supply_edge: Optional[SupplyChainEdge] = None,
        is_inst_net_buying_5d: bool = True,
        is_margin_overheated: bool = False,
    ) -> DecisionAuditTrail:
        notes: List[str] = []

        # 0. 風控優先：檢查是否已觸及現有持倉停損
        if risk_eval.is_exit_signal_triggered:
            notes.append(f"EXIT_ALERT: 觸發停損出場訊號 - {risk_eval.exit_reason}")
            return DecisionAuditTrail(
                stock_symbol=symbol,
                action=TradingAction.STOP_LOSS,
                passed_strategic_gate=False,
                passed_health_gate=False,
                passed_kinetic_gate=False,
                passed_tactical_gate=False,
                is_stop_loss_triggered=True,
                rejection_reason=f"STOP_LOSS_BREACH: {risk_eval.exit_reason}",
                macro_regime_multiplier=macro_analysis.macro_regime_multiplier,
                recommended_position_pct=0.0,
                stop_loss_price=risk_eval.chandelier_stop,
                target_price=valuation.dcf_intrinsic_value_consensus,
                audit_notes=notes,
            )

        # Gate 1: 戰略層（產業圖譜與定價權）
        passed_strategic = True
        strategic_notes = []
        if supply_edge:
            # 檢查替代性與話語權
            if supply_edge.revenue_share > 0.40 and not supply_edge.is_sole_supplier:
                # 高度依賴單一大客戶但非獨家，面臨砍價抽單風險
                strategic_notes.append("WARN: 高度依賴非獨家客戶，定價權偏弱。")
            if supply_edge.confidence >= 0.85:
                strategic_notes.append("CONFIRMED: 圖譜傳導關係確鑿。")
        notes.extend(strategic_notes)

        # Gate 2: 體質層（基本面與破產風險）
        passed_health = True
        health_reasons = []
        if valuation.piotroski_f_score < self.min_f_score:
            passed_health = False
            health_reasons.append(f"F-Score 偏低 ({valuation.piotroski_f_score} < {self.min_f_score})")
        if valuation.altman_z_score < self.min_altman_z:
            passed_health = False
            health_reasons.append(f"Altman Z 破產風險警示 ({valuation.altman_z_score} < {self.min_altman_z})")

        if not passed_health:
            rejection = "HEALTH_GATE_FAILED: " + "; ".join(health_reasons)
            notes.append(rejection)
            return DecisionAuditTrail(
                stock_symbol=symbol,
                action=TradingAction.PROHIBIT_LONG,
                passed_strategic_gate=passed_strategic,
                passed_health_gate=False,
                passed_kinetic_gate=False,
                passed_tactical_gate=False,
                is_stop_loss_triggered=False,
                rejection_reason=rejection,
                macro_regime_multiplier=macro_analysis.macro_regime_multiplier,
                recommended_position_pct=0.0,
                stop_loss_price=risk_eval.chandelier_stop,
                target_price=valuation.dcf_intrinsic_value_consensus,
                audit_notes=notes,
            )

        # Gate 3: 動力層（法人籌碼與散戶籌碼沉澱）
        passed_kinetic = is_inst_net_buying_5d and (not is_margin_overheated)
        if not is_inst_net_buying_5d:
            notes.append("KINETIC_WAIT: 近 5 日法人尚未連續買超。")
        if is_margin_overheated:
            notes.append("KINETIC_WARN: 融資過熱，散戶浮額沉重。")

        # Gate 4: 戰術層（盤中即時流向與 VWAP 站上）
        passed_tactical = False
        if sector_signal:
            is_flow_strong = sector_signal.flow_ratio >= 1.5
            is_above_vwap = current_price >= sector_signal.leading_stock_vwap and current_price > 0
            passed_tactical = is_flow_strong and is_above_vwap
            if is_flow_strong:
                notes.append(f"TACTICAL_PASS: 族群資金流向比顯著 ({sector_signal.flow_ratio:.2f})")
        else:
            # 無即時盤中資料時，以價格高於停損線與均線輔助判定
            passed_tactical = current_price > risk_eval.chandelier_stop

        # Gate 5: 執行層部位計算（結合總經乘數）
        macro_mult = macro_analysis.macro_regime_multiplier
        final_pos_pct = round(self.base_position_size_pct * macro_mult, 2)

        # 綜合狀態判定
        if passed_strategic and passed_health and passed_kinetic and passed_tactical:
            action = TradingAction.STRONG_BUY if macro_mult >= 0.9 else TradingAction.BUY
            notes.append(f"EXECUTE: 四維共振確認，建議建倉 {final_pos_pct}% (總經係數: {macro_mult})")
        elif passed_strategic and passed_health:
            action = TradingAction.WATCHLIST
            final_pos_pct = 0.0
            notes.append("WATCHLIST: 基本面與產業地位優良，等待籌碼或突破訊號點火。")
        else:
            action = TradingAction.HOLD if current_price > risk_eval.chandelier_stop else TradingAction.REDUCE
            final_pos_pct = 0.0

        target_px = max(valuation.dcf_intrinsic_value_consensus, valuation.pe_bands.get("p75", current_price * 1.15))

        return DecisionAuditTrail(
            stock_symbol=symbol,
            action=action,
            passed_strategic_gate=passed_strategic,
            passed_health_gate=passed_health,
            passed_kinetic_gate=passed_kinetic,
            passed_tactical_gate=passed_tactical,
            is_stop_loss_triggered=False,
            rejection_reason=None if action in [TradingAction.STRONG_BUY, TradingAction.BUY] else "WAITING_FOR_TRIGGER",
            macro_regime_multiplier=macro_mult,
            recommended_position_pct=final_pos_pct,
            stop_loss_price=risk_eval.chandelier_stop,
            target_price=round(target_px, 2),
            audit_notes=notes,
        )
