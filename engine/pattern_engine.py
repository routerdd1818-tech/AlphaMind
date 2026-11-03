"""
AlphaMind AI — K-Line Candlestick & Structural Chart Pattern Engine
Detects single/multi-candle patterns and structural breakouts/breakdowns,
generating pattern transition alerts and target-price modifiers without curve-fitting.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional
import numpy as np
from alphamind.engine.risk_engine import DailyBar


@dataclass
class DetectedPattern:
    pattern_code: str          # e.g., 'BULLISH_ENGULFING', 'BOX_BREAKOUT_VOL', 'BEARISH_ENGULFING', 'NECKLINE_BREAKDOWN'
    pattern_name_zh: str       # 中文名稱：多頭吞噬、帶量箱型突破、空頭吞噬、跌破月線頸線...
    direction: str             # 'BULLISH', 'BEARISH', 'NEUTRAL'
    confidence_score: float    # 0.0 ~ 1.0 (依量能配合度與實體比例決定)
    detected_date: str
    key_level_price: float     # 型態關鍵支撐或壓力頸線價位
    description: str


@dataclass
class PatternEvaluationReport:
    symbol: str
    latest_date: str
    overall_pattern_bias: str           # 'BULLISH', 'BEARISH', 'NEUTRAL'
    pattern_regime_state: str           # 'UPTREND_CONTINUATION', 'BOTTOM_REVERSAL', 'TOP_REVERSAL_WARNING', 'CONSOLIDATION', 'BREAKDOWN'
    previous_regime_state: str          # 前一階段型態狀態 (用於偵測型態轉變提醒)
    is_regime_transition: bool          # 是否發生型態轉變 (用於觸發型態轉變提醒)
    transition_alert_message: Optional[str]
    target_price_modifier: float        # 對目標價之保守調整乘數 (範圍限制於 0.92 ~ 1.08 防止過度理想化)
    pattern_neckline_support: float     # 型態關鍵防守頸線
    pattern_resistance_level: float     # 型態上方壓力位
    detected_patterns: List[DetectedPattern] = field(default_factory=list)


class CandlestickPatternEngine:
    """
    K 線與結構型態辨識引擎：
    結合「實體/影線比例」與「成交量確認（Volume Confirmation）」，避免純單根 K 線在無量盤整區產生假訊號。
    """

    def evaluate_bars(self, symbol: str, bars: List[DailyBar]) -> PatternEvaluationReport:
        if len(bars) < 22:
            last_px = bars[-1].close if bars else 100.0
            last_dt = bars[-1].date if bars else ""
            return PatternEvaluationReport(
                symbol=symbol,
                latest_date=last_dt,
                overall_pattern_bias="NEUTRAL",
                pattern_regime_state="CONSOLIDATION",
                previous_regime_state="CONSOLIDATION",
                is_regime_transition=False,
                transition_alert_message=None,
                target_price_modifier=1.0,
                pattern_neckline_support=round(last_px * 0.95, 2),
                pattern_resistance_level=round(last_px * 1.05, 2),
                detected_patterns=[],
            )

        closes = np.array([b.close for b in bars], dtype=float)
        opens = np.array([b.open for b in bars], dtype=float)
        highs = np.array([b.high for b in bars], dtype=float)
        lows = np.array([b.low for b in bars], dtype=float)
        vols = np.array([b.volume for b in bars], dtype=float)

        ma5 = np.mean(closes[-5:])
        ma20 = np.mean(closes[-20:])
        prev_ma20 = np.mean(closes[-21:-1])
        vol_ma20 = max(1.0, float(np.mean(vols[-20:])))

        # 過去 20 日箱型高低點 (不含當日，用於檢驗真突破/真跌破)
        box_high_20 = float(np.max(highs[-21:-1]))
        box_low_20 = float(np.min(lows[-21:-1]))
        box_low_10 = float(np.min(lows[-11:-1]))

        c0, o0, h0, l0, v0 = closes[-1], opens[-1], highs[-1], lows[-1], vols[-1]
        c1, o1, h1, l1, v1 = closes[-2], opens[-2], highs[-2], lows[-2], vols[-2]
        c2, o2, h2, l2, v2 = closes[-3], opens[-3], highs[-3], lows[-3], vols[-3]

        body0 = abs(c0 - o0)
        range0 = max(0.01, h0 - l0)
        upper_shadow0 = h0 - max(c0, o0)
        lower_shadow0 = min(c0, o0) - l0
        vol_ratio0 = v0 / vol_ma20

        body1 = abs(c1 - o1)
        range1 = max(0.01, h1 - l1)
        body2 = abs(c2 - o2)

        patterns: List[DetectedPattern] = []
        latest_date = bars[-1].date

        # 1. 帶量箱型突破 (20D Box Breakout with Volume)
        if c0 > box_high_20 and vol_ratio0 >= 1.25:
            conf = min(0.95, 0.70 + (vol_ratio0 - 1.25) * 0.2)
            patterns.append(
                DetectedPattern(
                    pattern_code="BOX_BREAKOUT_VOL",
                    pattern_name_zh="帶量突破 20 日箱型頂部",
                    direction="BULLISH",
                    confidence_score=round(conf, 2),
                    detected_date=latest_date,
                    key_level_price=round(box_high_20, 2),
                    description=f"收盤價 ({c0}) 突破過去 20 日高點頸線 ({round(box_high_20, 2)})，量能放大至月均量 {vol_ratio0:.1f} 倍。",
                )
            )

        # 2. 多頭吞噬 (Bullish Engulfing)
        if (c1 < o1) and (c0 > o0) and (c0 >= o1) and (o0 <= c1) and (body0 > body1 * 1.05):
            conf = min(0.90, 0.65 + (0.15 if vol_ratio0 >= 1.1 else 0.0))
            patterns.append(
                DetectedPattern(
                    pattern_code="BULLISH_ENGULFING",
                    pattern_name_zh="多頭吞噬線",
                    direction="BULLISH",
                    confidence_score=round(conf, 2),
                    detected_date=latest_date,
                    key_level_price=round(min(l0, l1), 2),
                    description=f"今日長紅實體完全包覆前日黑 K，低檔買盤強勁，防守支撐設於 {round(min(l0, l1), 2)}。",
                )
            )

        # 3. 空頭吞噬 (Bearish Engulfing)
        if (c1 > o1) and (c0 < o0) and (o0 >= c1) and (c0 <= o1) and (body0 > body1 * 1.05):
            conf = min(0.90, 0.65 + (0.15 if vol_ratio0 >= 1.15 else 0.0))
            patterns.append(
                DetectedPattern(
                    pattern_code="BEARISH_ENGULFING",
                    pattern_name_zh="空頭吞噬線",
                    direction="BEARISH",
                    confidence_score=round(conf, 2),
                    detected_date=latest_date,
                    key_level_price=round(max(h0, h1), 2),
                    description=f"高檔長黑實體吞噬前日紅 K，上方 {round(max(h0, h1), 2)} 形成短線出貨壓力。",
                )
            )

        # 4. 晨星轉折 (Morning Star - 3-bar bottom reversal)
        if (c2 < o2 and body2 > range1 * 0.6) and (body1 < body2 * 0.45) and (c0 > o0 and c0 > (o2 + c2) / 2.0):
            patterns.append(
                DetectedPattern(
                    pattern_code="MORNING_STAR",
                    pattern_name_zh="晨星底部反轉",
                    direction="BULLISH",
                    confidence_score=0.78,
                    detected_date=latest_date,
                    key_level_price=round(min(l0, l1, l2), 2),
                    description="三日 K 線構成長黑、十字星止跌、長紅收復中軸之晨星反轉型態。",
                )
            )

        # 5. 夜星轉折 (Evening Star - 3-bar top reversal)
        if (c2 > o2 and body2 > range1 * 0.6) and (body1 < body2 * 0.45) and (c0 < o0 and c0 < (o2 + c2) / 2.0):
            patterns.append(
                DetectedPattern(
                    pattern_code="EVENING_STAR",
                    pattern_name_zh="夜星頂部反轉",
                    direction="BEARISH",
                    confidence_score=0.78,
                    detected_date=latest_date,
                    key_level_price=round(max(h0, h1, h2), 2),
                    description="三日 K 線構成長紅、高檔十字星滯漲、長黑貫穿中軸之夜星轉空型態。",
                )
            )

        # 6. 錘頭線 / 下影線承接 (Hammer / Pin Bar Support)
        if lower_shadow0 >= body0 * 2.0 and upper_shadow0 <= body0 * 0.6 and lower_shadow0 / range0 >= 0.55:
            patterns.append(
                DetectedPattern(
                    pattern_code="HAMMER_PINBAR",
                    pattern_name_zh="長下影線錘頭承接",
                    direction="BULLISH",
                    confidence_score=0.72,
                    detected_date=latest_date,
                    key_level_price=round(l0, 2),
                    description=f"盤中回測 {round(l0, 2)} 湧現低接買盤留長下影線，構成短線支撐錨點。",
                )
            )

        # 7. 射擊之星 / 長上影線避雷針 (Shooting Star)
        if upper_shadow0 >= body0 * 2.0 and lower_shadow0 <= body0 * 0.6 and upper_shadow0 / range0 >= 0.55:
            patterns.append(
                DetectedPattern(
                    pattern_code="SHOOTING_STAR",
                    pattern_name_zh="長上影線射擊之星",
                    direction="BEARISH",
                    confidence_score=0.72,
                    detected_date=latest_date,
                    key_level_price=round(h0, 2),
                    description=f"衝高至 {round(h0, 2)} 遭遇獲利了結賣壓壓回，短線需提防動能衰竭。",
                )
            )

        # 8. 跌破月線與近 10 日頸線 (Neckline & MA20 Breakdown)
        if c0 < ma20 and c0 < box_low_10 and c1 >= prev_ma20:
            patterns.append(
                DetectedPattern(
                    pattern_code="NECKLINE_BREAKDOWN",
                    pattern_name_zh="帶量跌破月線與頸線支撐",
                    direction="BEARISH",
                    confidence_score=0.84 if vol_ratio0 >= 1.2 else 0.74,
                    detected_date=latest_date,
                    key_level_price=round(ma20, 2),
                    description=f"收盤同步跌破 20MA ({round(ma20, 2)}) 與近 10 日低點頸線 ({round(box_low_10, 2)})，波段結構轉弱。",
                )
            )

        # 若無特殊極端 K 線，補充當前均線結構型態
        if not patterns:
            if c0 >= ma5 >= ma20:
                patterns.append(
                    DetectedPattern(
                        pattern_code="MA_BULL_ALIGNMENT",
                        pattern_name_zh="均線多頭排列穩步推升",
                        direction="BULLISH",
                        confidence_score=0.68,
                        detected_date=latest_date,
                        key_level_price=round(ma20, 2),
                        description=f"股價穩守 5 日線 ({round(ma5, 2)}) 與 20 日月線 ({round(ma20, 2)}) 之上，多頭架構延續。",
                    )
                )
            elif c0 < ma20 and ma5 < ma20:
                patterns.append(
                    DetectedPattern(
                        pattern_code="MA_BEAR_PRESSURE",
                        pattern_name_zh="月線蓋頭反壓修正",
                        direction="BEARISH",
                        confidence_score=0.66,
                        detected_date=latest_date,
                        key_level_price=round(ma20, 2),
                        description=f"股價位於 20 日月線 ({round(ma20, 2)}) 之下且五日線下彎，尚未出現底部吞噬訊號。",
                    )
                )
            else:
                patterns.append(
                    DetectedPattern(
                        pattern_code="BOX_CONSOLIDATION",
                        pattern_name_zh="區間箱型量縮整理",
                        direction="NEUTRAL",
                        confidence_score=0.60,
                        detected_date=latest_date,
                        key_level_price=round(box_low_10, 2),
                        description=f"股價於 {round(box_low_10, 2)} ~ {round(box_high_20, 2)} 箱型區間內震盪換手。",
                    )
                )

        # 計算前一日與今日之 Regime 狀態以偵測「型態轉變提醒」
        prev_regime = self._classify_regime_at(closes[:-1], opens[:-1], highs[:-1], lows[:-1])
        curr_regime = self._classify_regime_at(closes, opens, highs, lows)

        bull_score = sum(p.confidence_score for p in patterns if p.direction == "BULLISH")
        bear_score = sum(p.confidence_score for p in patterns if p.direction == "BEARISH")

        if bull_score > bear_score + 0.15:
            overall_bias = "BULLISH"
        elif bear_score > bull_score + 0.15:
            overall_bias = "BEARISH"
        else:
            overall_bias = "NEUTRAL"

        # 目標價修正係數：限制於 [0.94, 1.06] 區間，避免型態過度膨脹目標價造成過度理想化
        raw_mod = 1.0 + (bull_score - bear_score) * 0.04
        target_modifier = round(float(np.clip(raw_mod, 0.94, 1.06)), 4)

        is_transition = curr_regime != prev_regime
        transition_msg: Optional[str] = None
        if is_transition:
            primary_pat = patterns[0].pattern_name_zh if patterns else "結構轉折"
            transition_msg = f"K 線型態由「{self._regime_zh(prev_regime)}」轉變為「{self._regime_zh(curr_regime)}」（觸發：{primary_pat}）"

        neckline_support = round(max(box_low_10, min(ma20, c0 * 0.96)), 2)
        resistance_level = round(max(box_high_20, c0 * 1.03), 2)

        return PatternEvaluationReport(
            symbol=symbol,
            latest_date=latest_date,
            overall_pattern_bias=overall_bias,
            pattern_regime_state=curr_regime,
            previous_regime_state=prev_regime,
            is_regime_transition=is_transition,
            transition_alert_message=transition_msg,
            target_price_modifier=target_modifier,
            pattern_neckline_support=neckline_support,
            pattern_resistance_level=resistance_level,
            detected_patterns=patterns,
        )

    def _classify_regime_at(
        self,
        closes: np.ndarray,
        opens: np.ndarray,
        highs: np.ndarray,
        lows: np.ndarray,
    ) -> str:
        if len(closes) < 20:
            return "CONSOLIDATION"
        c0, o0 = closes[-1], opens[-1]
        c1, o1 = closes[-2], opens[-2]
        ma5 = float(np.mean(closes[-5:]))
        ma20 = float(np.mean(closes[-20:]))
        box_high_15 = float(np.max(highs[-16:-1]))
        box_low_10 = float(np.min(lows[-11:-1]))

        # 檢查高檔空頭吞噬或跌破頸線
        if (c1 > o1 and c0 < o0 and o0 >= c1 and c0 <= o1) and c0 > ma20:
            return "TOP_REVERSAL_WARNING"
        if c0 < ma20 and c0 < box_low_10:
            return "BREAKDOWN"
        # 檢查低檔多頭吞噬
        if (c1 < o1 and c0 > o0 and c0 >= o1 and o0 <= c1) and c1 <= ma20 * 1.02:
            return "BOTTOM_REVERSAL"
        if c0 > box_high_15 or (c0 >= ma5 >= ma20):
            return "UPTREND_CONTINUATION"
        return "CONSOLIDATION"

    @staticmethod
    def _regime_zh(regime: str) -> str:
        mapping = {
            "UPTREND_CONTINUATION": "多頭續航突破",
            "BOTTOM_REVERSAL": "底部反轉確認",
            "TOP_REVERSAL_WARNING": "高檔轉弱警戒",
            "CONSOLIDATION": "區間箱型整理",
            "BREAKDOWN": "跌破頸線轉空",
        }
        return mapping.get(regime, regime)
