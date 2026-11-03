"""
AlphaMind AI — Fundamental Health & Valuation River Engine
Calculates Piotroski F-Score, Altman Z-Score, PE/PB River Bands, and DCF consensus target prices.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
import numpy as np
import pandas as pd


@dataclass
class FinancialStatementData:
    net_income: float
    operating_cash_flow: float
    total_assets_current: float
    total_assets_prior: float
    long_term_debt_current: float
    long_term_debt_prior: float
    current_assets_current: float
    current_liabilities_current: float
    current_assets_prior: float
    current_liabilities_prior: float
    shares_outstanding_current: int
    shares_outstanding_prior: int
    gross_margin_current: float
    gross_margin_prior: float
    asset_turnover_current: float
    asset_turnover_prior: float
    ebit: float
    total_liabilities: float
    retained_earnings: float
    sales: float
    market_cap: float


@dataclass
class ValuationAssessment:
    stock_symbol: str
    current_price: float
    piotroski_f_score: int                 # 0 ~ 9
    is_f_score_healthy: bool               # >= 6 為財務健康
    altman_z_score: float                  # < 1.81 危險, 1.81~2.99 灰色, > 2.99 安全
    is_bankruptcy_risk_low: bool
    pe_ratio_current: float
    pe_bands: Dict[str, float]             # 'p10', 'p25', 'p50', 'p75', 'p90'
    pb_ratio_current: float
    pb_bands: Dict[str, float]
    dcf_intrinsic_value_conservative: float
    dcf_intrinsic_value_consensus: float
    dcf_intrinsic_value_optimistic: float
    valuation_status: str                  # 'UNDERVALUED', 'FAIR', 'OVERVALUED'


class ValuationEngine:
    """基本面評分與多模型估值引擎"""

    @staticmethod
    def calculate_piotroski_f_score(data: FinancialStatementData) -> int:
        score = 0
        # 1. 獲利能力 (Profitability)
        roa_current = data.net_income / max(data.total_assets_prior, 1.0)
        if data.net_income > 0:
            score += 1
        if data.operating_cash_flow > 0:
            score += 1
        if roa_current > 0:
            score += 1
        # 營業現金流 > 淨利 (盈餘品質高)
        if data.operating_cash_flow > data.net_income:
            score += 1

        # 2. 槓桿、流動性與融資 (Leverage & Liquidity)
        if data.long_term_debt_current <= data.long_term_debt_prior:
            score += 1
        cr_current = data.current_assets_current / max(data.current_liabilities_current, 1.0)
        cr_prior = data.current_assets_prior / max(data.current_liabilities_prior, 1.0)
        if cr_current > cr_prior:
            score += 1
        # 沒有增資稀釋普通股
        if data.shares_outstanding_current <= data.shares_outstanding_prior:
            score += 1

        # 3. 營運效率 (Operating Efficiency)
        if data.gross_margin_current > data.gross_margin_prior:
            score += 1
        if data.asset_turnover_current > data.asset_turnover_prior:
            score += 1

        return score

    @staticmethod
    def calculate_altman_z_score(data: FinancialStatementData) -> float:
        """Altman Z-Score 製造業通用公式"""
        working_capital = data.current_assets_current - data.current_liabilities_current
        x1 = working_capital / max(data.total_assets_current, 1.0)
        x2 = data.retained_earnings / max(data.total_assets_current, 1.0)
        x3 = data.ebit / max(data.total_assets_current, 1.0)
        x4 = data.market_cap / max(data.total_liabilities, 1.0)
        x5 = data.sales / max(data.total_assets_current, 1.0)
        z = 1.2 * x1 + 1.4 * x2 + 3.3 * x3 + 0.6 * x4 + 0.999 * x5
        return float(round(z, 3))

    @staticmethod
    def calculate_river_bands(
        historical_multiples: List[float],
        current_metric_value: float,
    ) -> Dict[str, float]:
        """計算河流圖百分位數價位帶"""
        clean_multiples = [m for m in historical_multiples if m > 0]
        if not clean_multiples:
            clean_multiples = [12.0, 15.0, 18.0, 22.0, 28.0]

        percentiles = [10, 25, 50, 75, 90]
        values = np.percentile(clean_multiples, percentiles)
        return {
            f"p{p}": round(float(v * current_metric_value), 2)
            for p, v in zip(percentiles, values)
        }

    @staticmethod
    def calculate_dcf(
        free_cash_flow: float,
        shares_outstanding: int,
        wacc: float = 0.085,
        terminal_growth: float = 0.025,
        forecast_growth_rates: Optional[Tuple[float, float, float]] = None,
    ) -> Tuple[float, float, float]:
        """推導保守/共識/樂觀 DCF 內在價值"""
        # (保守成長率, 共識成長率, 樂觀成長率)
        rates = forecast_growth_rates or (0.08, 0.15, 0.22)
        intrinsic_values = []

        for g in rates:
            pv_fcf = 0.0
            cur_fcf = max(free_cash_flow, 1.0)
            for t in range(1, 6):
                cur_fcf *= (1.0 + g)
                pv_fcf += cur_fcf / ((1.0 + wacc) ** t)
            # 終值 Terminal Value
            terminal_val = (cur_fcf * (1.0 + terminal_growth)) / max(0.01, wacc - terminal_growth)
            pv_tv = terminal_val / ((1.0 + wacc) ** 5)
            enterprise_value = pv_fcf + pv_tv
            per_share_value = enterprise_value / max(shares_outstanding, 1)
            intrinsic_values.append(round(float(per_share_value), 2))

        return intrinsic_values[0], intrinsic_values[1], intrinsic_values[2]

    def evaluate(
        self,
        symbol: str,
        current_price: float,
        statement: FinancialStatementData,
        historical_pes: List[float],
        historical_pbs: List[float],
        eps: float,
        bps: float,
        fcf: float,
    ) -> ValuationAssessment:
        f_score = self.calculate_piotroski_f_score(statement)
        z_score = self.calculate_altman_z_score(statement)
        pe_bands = self.calculate_river_bands(historical_pes, max(eps, 0.1))
        pb_bands = self.calculate_river_bands(historical_pbs, max(bps, 1.0))
        dcf_cons, dcf_mid, dcf_opt = self.calculate_dcf(fcf, statement.shares_outstanding_current)

        cur_pe = current_price / max(eps, 0.001)
        cur_pb = current_price / max(bps, 0.001)

        val_status = "FAIR"
        if current_price < pe_bands.get("p25", 0.0) and current_price < dcf_mid:
            val_status = "UNDERVALUED"
        elif current_price > pe_bands.get("p75", 999999.0):
            val_status = "OVERVALUED"

        return ValuationAssessment(
            stock_symbol=symbol,
            current_price=current_price,
            piotroski_f_score=f_score,
            is_f_score_healthy=(f_score >= 6),
            altman_z_score=z_score,
            is_bankruptcy_risk_low=(z_score >= 1.81),
            pe_ratio_current=round(cur_pe, 2),
            pe_bands=pe_bands,
            pb_ratio_current=round(cur_pb, 2),
            pb_bands=pb_bands,
            dcf_intrinsic_value_conservative=dcf_cons,
            dcf_intrinsic_value_consensus=dcf_mid,
            dcf_intrinsic_value_optimistic=dcf_opt,
            valuation_status=val_status,
        )
