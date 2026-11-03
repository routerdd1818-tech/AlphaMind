"""
AlphaMind AI — Overfitting & Data Snooping Guard
Implements Deflated Sharpe Ratio (DSR), Lookahead Bias Auditing (Point-in-Time Lag),
and Parameter Plateau Stability testing to prevent pseudo-alpha and backtest overfitting.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Dict, List, Tuple
import numpy as np
import pandas as pd
from scipy.stats import norm, skew, kurtosis


@dataclass
class LookaheadAuditReport:
    total_evaluations: int
    lookahead_violations_count: int
    is_point_in_time_clean: bool
    violations: List[str]


@dataclass
class DeflatedSharpeReport:
    observed_sharpe: float
    deflated_sharpe_ratio: float       # DSR 統計值 (0.0 ~ 1.0)
    p_value: float                     # 拒絕虛無假說之 p 值 (p < 0.05 代表策略顯著非過擬合)
    number_of_trials: int              # 回測嘗試次數 (例如 100 組參數尋優)
    is_statistically_significant: bool # 是否通過多重試驗校正


@dataclass
class ParameterPlateauReport:
    baseline_parameter: float
    baseline_sharpe: float
    neighborhood_sharpes: Dict[float, float]
    min_neighborhood_sharpe: float
    degradation_ratio: float           # 最低鄰域夏普 / 基準夏普 (>= 0.70 代表為穩定高原，非過擬合尖峰)
    is_parameter_plateau_robust: bool


class OverfittingGuard:
    """過擬合與資料窺探防禦引擎"""

    # 台股法定財報公告最後期限 (Point-in-Time 基準)
    REPORT_DEADLINES = {
        1: (5, 15),   # Q1 財報最晚於 5 月 15 日前公告
        2: (8, 14),   # Q2 財報最晚於 8 月 14 日前公告
        3: (11, 14),  # Q3 財報最晚於 11 月 14 日前公告
        4: (3, 31),   # Q4 / 年度財報最晚於隔年 3 月 31 日前公告
    }

    @classmethod
    def get_earliest_available_date(cls, year: int, quarter: int) -> datetime:
        """取得該季度財報最早可在市場上公開獲取的時間點"""
        if quarter == 4:
            month, day = cls.REPORT_DEADLINES[4]
            return datetime(year + 1, month, day)
        else:
            month, day = cls.REPORT_DEADLINES[quarter]
            return datetime(year, month, day)

    @classmethod
    def audit_point_in_time_integrity(
        cls,
        trades_and_evaluations: List[Dict[str, any]],
    ) -> LookaheadAuditReport:
        """
        檢驗時間先後順序（Point-in-Time Integrity），防止未來數據洩漏（Lookahead Leakage）。
        記錄格式: [{'decision_date': '2026-06-01', 'report_year': 2026, 'report_quarter': 1}]
        """
        violations = []
        for item in trades_and_evaluations:
            decision_dt = datetime.strptime(str(item["decision_date"]), "%Y-%m-%d")
            yr = int(item["report_year"])
            q = int(item["report_quarter"])

            earliest_dt = cls.get_earliest_available_date(yr, q)
            if decision_dt < earliest_dt:
                violations.append(
                    f"VIOLATION: 在 {decision_dt.strftime('%Y-%m-%d')} 使用了尚未公告的 {yr}Q{q} 財報 (最快公告日: {earliest_dt.strftime('%Y-%m-%d')})"
                )

        return LookaheadAuditReport(
            total_evaluations=len(trades_and_evaluations),
            lookahead_violations_count=len(violations),
            is_point_in_time_clean=(len(violations) == 0),
            violations=violations[:10],
        )

    @staticmethod
    def calculate_deflated_sharpe_ratio(
        observed_returns: List[float],
        number_of_trials: int = 50,
        variance_of_trials: float = 0.25,
        benchmark_sharpe: float = 0.0,
    ) -> DeflatedSharpeReport:
        """
        計算 Deflated Sharpe Ratio (Bailey & López de Prado 2014)
        校正多重參數測試（Data Snooping）帶來的假性 Alpha。
        """
        returns_arr = np.array(observed_returns)
        n = len(returns_arr)
        if n < 30:
            return DeflatedSharpeReport(
                observed_sharpe=0.0,
                deflated_sharpe_ratio=0.0,
                p_value=1.0,
                number_of_trials=number_of_trials,
                is_statistically_significant=False,
            )

        mean_ret = float(np.mean(returns_arr))
        std_ret = float(np.std(returns_arr, ddof=1))
        ann_factor = np.sqrt(252.0)
        obs_sharpe = float((mean_ret / std_ret) * ann_factor) if std_ret > 0 else 0.0

        # 計算偏態 (Skewness) 與峰態 (Kurtosis)
        sk = float(skew(returns_arr))
        kt = float(kurtosis(returns_arr, fisher=False)) # Pearson Kurtosis (常態分配 = 3)

        # 估計多重試驗下的期望最大夏普比率 E[max(SR)]
        # Euler-Mascheroni constant gamma ≈ 0.5772156649
        gamma = 0.5772156649
        z_approx = (1.0 - gamma) * norm.ppf(1.0 - 1.0 / number_of_trials) + gamma * norm.ppf(1.0 - 1.0 / (number_of_trials * np.e))
        expected_max_sharpe = benchmark_sharpe + np.sqrt(variance_of_trials) * z_approx

        # 估計 Sharpe Ratio 之漸近變異數 sigma_SR^2
        # V(SR) = (1 - sk * SR + ((kt - 1) / 4) * SR^2) / (T - 1)
        sr_daily = obs_sharpe / ann_factor
        var_sr = (1.0 - sk * sr_daily + ((kt - 1.0) / 4.0) * (sr_daily ** 2)) / max(n - 1, 1)
        se_sr = np.sqrt(max(var_sr, 1e-6)) * ann_factor

        # DSR 檢定統計值
        test_stat = (obs_sharpe - expected_max_sharpe) / max(se_sr, 1e-4)
        dsr_prob = float(norm.cdf(test_stat))
        p_val = float(1.0 - dsr_prob)

        return DeflatedSharpeReport(
            observed_sharpe=round(obs_sharpe, 3),
            deflated_sharpe_ratio=round(dsr_prob, 4),
            p_value=round(p_val, 4),
            number_of_trials=number_of_trials,
            is_statistically_significant=(p_val < 0.05),
        )

    @staticmethod
    def test_parameter_plateau(
        baseline_param: float,
        backtest_fn: Callable[[float], float], # 輸入參數值，回傳夏普值
        perturbation_percentages: List[float] = [-0.15, -0.10, -0.05, 0.05, 0.10, 0.15],
    ) -> ParameterPlateauReport:
        """
        參數高原穩定度測試：
        檢驗參數在鄰近區間（±5% ~ ±15%）內夏普比率是否維持平穩。
        若鄰域表現低於基準的 70%，代表該參數可能是擬合特定雜訊的孤立尖峰（Overfitted Spike）。
        """
        baseline_sharpe = backtest_fn(baseline_param)
        neighborhood_results = {}

        for p_pct in perturbation_percentages:
            neighbor_param = baseline_param * (1.0 + p_pct)
            neighbor_sharpe = backtest_fn(neighbor_param)
            neighborhood_results[round(neighbor_param, 3)] = round(neighbor_sharpe, 3)

        min_neighbor_sr = min(neighborhood_results.values()) if neighborhood_results else baseline_sharpe
        degradation = (min_neighbor_sr / baseline_sharpe) if baseline_sharpe > 0 else 0.0

        return ParameterPlateauReport(
            baseline_parameter=round(baseline_param, 3),
            baseline_sharpe=round(baseline_sharpe, 3),
            neighborhood_sharpes=neighborhood_results,
            min_neighborhood_sharpe=round(min_neighbor_sr, 3),
            degradation_ratio=round(degradation, 3),
            is_parameter_plateau_robust=(degradation >= 0.70),
        )
