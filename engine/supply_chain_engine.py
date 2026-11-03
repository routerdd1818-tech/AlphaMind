"""
AlphaMind AI — Supply Chain Lagging & Transmission Engine
Identifies arbitrage opportunities where upstream/downstream leaders surged but direct suppliers lagged.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional
import numpy as np
import pandas as pd


@dataclass(frozen=True)
class SupplyChainEdge:
    leader_symbol: str
    supplier_symbol: str
    relationship_type: str       # 'SUPPLIES_TO', 'BUYS_FROM'
    revenue_share: float         # 供應商營收佔比 (0.0 ~ 1.0)
    confidence: float            # 知識圖譜可信度
    is_sole_supplier: bool = False
    substitutability_score: float = 0.5 # 0.0 極易替代 ~ 1.0 無法替代


@dataclass
class LaggingOpportunitySignal:
    date: str
    leader_symbol: str
    supplier_symbol: str
    leader_5d_return_pct: float
    supplier_5d_return_pct: float
    return_spread_pct: float
    historical_correlation_60d: float
    revenue_share: float
    catch_up_target_price: float
    current_supplier_price: float
    is_lagging_signal: bool
    signal_strength: float       # 綜合評分 0.0 ~ 100.0


class SupplyChainLagEngine:
    """
    供應鏈落後補漲引擎：
    1. 檢測上/下游龍頭近 5 日漲幅與直屬供應商之報酬脫鉤（Spread）。
    2. 驗證近 60 日歷史股價相關係數 > 0.70。
    3. 結合圖譜營收依賴度（revenue_share）推算補漲潛力目標與信號強度。
    """

    def __init__(
        self,
        leader_return_threshold: float = 0.10,    # 龍頭 5 日漲幅 >= 10%
        supplier_return_ceiling: float = 0.02,    # 供應商 5 日漲幅 <= 2%
        min_correlation: float = 0.70,            # 歷史相關性門檻
        correlation_window: int = 60,
    ) -> None:
        self.leader_return_threshold = leader_return_threshold
        self.supplier_return_ceiling = supplier_return_ceiling
        self.min_correlation = min_correlation
        self.correlation_window = correlation_window

    def scan_opportunities(
        self,
        edge: SupplyChainEdge,
        leader_closes: pd.Series,
        supplier_closes: pd.Series,
        date_str: str,
    ) -> Optional[LaggingOpportunitySignal]:
        if len(leader_closes) < self.correlation_window or len(supplier_closes) < self.correlation_window:
            return None

        # 1. 計算近 5 日報酬率
        leader_5d_ret = float((leader_closes.iloc[-1] / leader_closes.iloc[-6]) - 1.0)
        supplier_5d_ret = float((supplier_closes.iloc[-1] / supplier_closes.iloc[-6]) - 1.0)
        spread = leader_5d_ret - supplier_5d_ret

        # 2. 計算過去 60 日對數報酬率相關係數
        leader_log_ret = np.log(leader_closes.iloc[-self.correlation_window:] / leader_closes.iloc[-self.correlation_window:].shift(1)).dropna()
        supplier_log_ret = np.log(supplier_closes.iloc[-self.correlation_window:] / supplier_closes.iloc[-self.correlation_window:].shift(1)).dropna()

        corr = float(leader_log_ret.corr(supplier_log_ret))
        if np.isnan(corr):
            corr = 0.0

        # 3. 條件判定
        is_triggered = bool(
            leader_5d_ret >= self.leader_return_threshold
            and supplier_5d_ret <= self.supplier_return_ceiling
            and corr >= self.min_correlation
        )

        cur_supplier_px = float(supplier_closes.iloc[-1])

        # 4. 推算理論補漲目標價 (以相關性與營收權重折現)
        # 預期補漲幅度 = 價差 * 相關係數 * (0.5 + 0.5 * 營收佔比)
        expected_catchup_ret = spread * max(0.0, corr) * (0.5 + 0.5 * edge.revenue_share)
        catch_up_target = cur_supplier_px * (1.0 + max(0.0, expected_catchup_ret))

        # 5. 計算訊號強度得分 (0 ~ 100)
        # 因子包括：價差大小 (40%)、歷史相關係數 (30%)、營收權重與置信度 (30%)
        spread_score = min(100.0, (spread / 0.15) * 100.0) * 0.40
        corr_score = max(0.0, min(100.0, (corr / 1.0) * 100.0)) * 0.30
        weight_score = (edge.revenue_share * edge.confidence * 100.0) * 0.30
        composite_score = float(round(spread_score + corr_score + weight_score, 2)) if is_triggered else 0.0

        return LaggingOpportunitySignal(
            date=date_str,
            leader_symbol=edge.leader_symbol,
            supplier_symbol=edge.supplier_symbol,
            leader_5d_return_pct=round(leader_5d_ret * 100.0, 2),
            supplier_5d_return_pct=round(supplier_5d_ret * 100.0, 2),
            return_spread_pct=round(spread * 100.0, 2),
            historical_correlation_60d=round(corr, 3),
            revenue_share=round(edge.revenue_share, 3),
            catch_up_target_price=round(catch_up_target, 2),
            current_supplier_price=round(cur_supplier_px, 2),
            is_lagging_signal=is_triggered,
            signal_strength=composite_score,
        )
