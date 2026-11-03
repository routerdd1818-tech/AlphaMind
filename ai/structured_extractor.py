"""
AlphaMind AI — Structured NLP Extractor
Extracts supply chain edges and news features using structured schemas.
"""

import json
from typing import Dict, List, Optional
from alphamind.ai.schemas import (
    NewsFeatureExtractionResponse,
    SupplyChainEdgeItem,
    SupplyChainExtractionResponse,
)


SUPPLY_CHAIN_SYSTEM_PROMPT = """
你是一位資深的產業研究員與量化圖資料庫專家。
你的任務是解析上市櫃公司的年報「產業概況」及「主要進銷貨客戶名單」或法說會逐字稿。
請嚴格萃取：
1. 供應商與客戶名稱與股票代號。
2. 供貨產品類別。
3. 營收佔比（若未明寫請依語意合理估算）。
4. 是否為獨家供應商（Sole Supplier）。
5. 替代難度評分（Substitutability Score: 0.0 表示標準品極易替代，1.0 表示客製化或專利獨占難以替代）。
6. 定價與成本轉嫁能力簡述。
請一律依據提供的 JSON Schema 輸出結構化資料。
"""

NEWS_FEATURE_SYSTEM_PROMPT = """
你是一位量化避險基金的資深事件驅動分析師。
你的任務是針對即時財經新聞進行結構化特徵標注：
1. 情緒指數 sentiment_score (-1.0 至 +1.0)。
2. 事件類別 event_category。
3. 影響時效 impact_horizon (短線激情 SHORT_TERM 或 長線結構 LONG_TERM)。
4. 關聯股票代號與上下游節點。
請去除公關廢話，精準輸出 JSON Schema 結構。
"""


class StructuredExtractor:
    """結構化抽取器"""

    @staticmethod
    def parse_mock_supply_chain_text(text: str, reporting_company: str = "台積電") -> SupplyChainExtractionResponse:
        """模擬/離線抽取測試樣板"""
        edges = [
            SupplyChainEdgeItem(
                supplier_name="弘塑科技",
                supplier_symbol="3131.TW",
                customer_name="台積電",
                customer_symbol="2330.TW",
                product_or_service="CoWoS 濕製程單晶圓清洗設備",
                revenue_share=0.38,
                is_sole_supplier=False,
                substitutability_score=0.85,
                pricing_power_summary="先進封裝擴產關鍵機台，交期長且獲驗證通過，轉嫁能力強。",
                confidence=0.95,
            ),
            SupplyChainEdgeItem(
                supplier_name="台積電",
                supplier_symbol="2330.TW",
                customer_name="NVIDIA",
                customer_symbol="NVDA",
                product_or_service="4N/3nm 晶圓代工與 CoWoS-L 封裝",
                revenue_share=0.15,
                is_sole_supplier=True,
                substitutability_score=0.98,
                pricing_power_summary="AI 旗艦晶片唯一量產晶圓廠，享有全面定價權。",
                confidence=0.99,
            ),
        ]
        return SupplyChainExtractionResponse(
            source_document="113年股東會年報",
            reporting_company=reporting_company,
            edges=edges,
        )

    @staticmethod
    def parse_mock_news_text(headline: str, content: str) -> NewsFeatureExtractionResponse:
        """模擬/離線新聞特徵抽取樣板"""
        # 檢測利多關鍵詞
        is_bull = any(kw in headline for kw in ["擴產", "大增", "出貨提前", "創高", "追單"])
        sentiment = 0.85 if is_bull else (-0.75 if "掉單" in headline or "砍單" in headline else 0.1)

        return NewsFeatureExtractionResponse(
            headline=headline,
            sentiment_score=sentiment,
            event_category="CAPEX_EXPANSION" if is_bull else "ORDER_LOSS",
            impact_horizon="LONG_TERM" if is_bull else "SHORT_TERM",
            mentioned_symbols=["2330.TW", "3131.TW"],
            affected_supply_chain_nodes=["CoWoS_Packaging", "Wet_Cleaning_Equipment"],
            bullet_summary="台積電擴充 CoWoS 先進封裝月產能至 6.5 萬片，設備供應商弘塑訂單能見度直達明年下半年。",
        )
