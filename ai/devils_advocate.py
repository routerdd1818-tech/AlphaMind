"""
AlphaMind AI — AI Devil's Advocate (Red Teaming Agent)
Generates counter-thesis and identifies fatal bear risks before entering long positions.
"""

from typing import Dict, List, Optional
from alphamind.ai.schemas import DevilsAdvocateReport


DEVILS_ADVOCATE_SYSTEM_PROMPT = """
你是一位專門做空高估值泡沫與財務造假公司的「華爾街激進放空對沖基金首席分析師（魔鬼代言人）」。
當交易員準備做多一檔股票時，你的唯一職責是潑冷水，列出該公司最致命、最可能導致虧損的 3 個看空理由。
審查面向包含：
1. 財務體質漏洞：應收帳款天數暴增、自由現金流為負、存貨週轉率惡化。
2. 供應鏈脆弱度：客戶抽單傳聞、第二供應商導入、原料成本激增侵蝕毛利。
3. 籌碼與預期陷阱：融資暴增、利多出盡、估值處於歷史極端 90% 分位數。
請給出毫不留情的脆弱度評分 (0~100) 與紅隊審查結論。
"""


class DevilsAdvocateAgent:
    """AI 魔鬼代言人逆向抗辯代理"""

    @staticmethod
    def audit_bull_thesis(
        symbol: str,
        name: str,
        bull_thesis: str,
        pe_ratio: float,
        margin_debt_high: bool = False,
        receivables_stretched: bool = False,
    ) -> DevilsAdvocateReport:
        bear_reasons = []

        if pe_ratio > 35.0:
            bear_reasons.append(f"估值定價處於完美預期（本益比 {pe_ratio:.1f}x），若下季獲利成長不如預期將引發本益比劇烈戴維斯雙殺。")
        else:
            bear_reasons.append("終端需求能見度若因地緣政治或關稅政策放緩，擴產資本支出將轉為沉重折舊負擔。")

        if margin_debt_high:
            bear_reasons.append("散戶融資餘額位處近半年高檔，浮額凌亂，一旦外資轉賣極易引發多殺多斷頭潮。")
        else:
            bear_reasons.append("大客戶正在積極扶植第二與第三供應商以分散風險，毛利率難以長期維持在歷史高點。")

        if receivables_stretched:
            bear_reasons.append("應收帳款與存貨週轉天數異常拉長，營收成長未轉化為實質營運現金流，存在呆帳提列隱憂。")
        else:
            bear_reasons.append("同業競爭對手新產能將於下半年集中開出，未來恐面臨價格競爭壓力。")

        vulnerability = 30.0
        if pe_ratio > 40.0:
            vulnerability += 25.0
        if margin_debt_high:
            vulnerability += 20.0
        if receivables_stretched:
            vulnerability += 20.0

        vulnerability = min(100.0, vulnerability)

        verdict = "SAFE_TO_BUY"
        if vulnerability >= 70.0:
            verdict = "HIGH_RISK_AVOID"
        elif vulnerability >= 45.0:
            verdict = "PROCEED_WITH_CAUTION"

        return DevilsAdvocateReport(
            target_symbol=symbol,
            target_name=name,
            primary_bull_thesis=bull_thesis,
            three_fatal_bear_reasons=bear_reasons[:3],
            vulnerability_score=round(vulnerability, 1),
            red_team_verdict=verdict,
            suggested_risk_hedges=[
                "強制將移動停損幅度從 2.5 ATR 縮緊為 1.8 ATR。",
                "建倉首筆部位不得超過總資產 8%，待突破壓力區再加碼。",
            ],
        )
