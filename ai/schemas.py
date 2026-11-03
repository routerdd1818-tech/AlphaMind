"""
AlphaMind AI — Pydantic Schemas for LLM Structured Outputs
Defines strict JSON Schemas for supply chain extraction, news feature tagging, and AI Red-Teaming.
"""

from typing import List, Literal, Optional
from pydantic import BaseModel, Field


class SupplyChainEdgeItem(BaseModel):
    supplier_name: str = Field(description="供應商名稱")
    supplier_symbol: Optional[str] = Field(None, description="供應商股票代號（例如 2330.TW）")
    customer_name: str = Field(description="下游客戶名稱")
    customer_symbol: Optional[str] = Field(None, description="客戶股票代號（例如 NVDA）")
    product_or_service: str = Field(description="供貨之產品或服務類別（如 CoWoS先進封裝、水冷板）")
    revenue_share: float = Field(default=0.1, ge=0.0, le=1.0, description="供貨金額佔供應商總營收比例預估 (0.0~1.0)")
    is_sole_supplier: bool = Field(default=False, description="是否為獨家/單一關鍵供應商")
    substitutability_score: float = Field(default=0.5, ge=0.0, le=1.0, description="客戶替換該供應商難度 (0.0 極易替代, 1.0 無法替代)")
    pricing_power_summary: str = Field(description="供應商對該客戶之議價能力與轉嫁能力簡述")
    confidence: float = Field(default=0.9, ge=0.0, le=1.0, description="萃取可信度")


class SupplyChainExtractionResponse(BaseModel):
    source_document: str = Field(description="分析來源文件（如 113年股東會年報、法說會簡報）")
    reporting_company: str = Field(description="申報主體公司")
    edges: List[SupplyChainEdgeItem] = Field(default_factory=list, description="抽取出的供應鏈有向邊清單")


class NewsFeatureExtractionResponse(BaseModel):
    headline: str = Field(description="新聞標題")
    sentiment_score: float = Field(ge=-1.0, le=1.0, description="利多/利空情緒指數 (-1.0 極度利空 至 +1.0 極度利多)")
    event_category: Literal[
        "CAPEX_EXPANSION",
        "ORDER_LOSS",
        "EARNINGS_CALL",
        "GEOPOLITICS",
        "MANAGEMENT_CHANGE",
        "PRODUCT_LAUNCH",
        "GENERAL_INDUSTRY",
    ] = Field(description="新聞核心事件分類")
    impact_horizon: Literal["SHORT_TERM", "LONG_TERM"] = Field(description="題材影響時效（短線題材 vs 長線結構改變）")
    mentioned_symbols: List[str] = Field(description="直接關聯股票代碼清單")
    affected_supply_chain_nodes: List[str] = Field(description="受波及之供應鏈上下游節點")
    bullet_summary: str = Field(description="兩句話核心投資洞見摘要")


class DevilsAdvocateReport(BaseModel):
    target_symbol: str = Field(description="目標標的代號")
    target_name: str = Field(description="公司名稱")
    primary_bull_thesis: str = Field(description="市場目前主流做多理由")
    three_fatal_bear_reasons: List[str] = Field(description="空方最致命的三個做空理由（包含應收帳款、客戶抽單、毛利壓縮等）")
    vulnerability_score: float = Field(ge=0.0, le=100.0, description="脆弱度評分 (0~100，越高代表暴雷機率越高)")
    red_team_verdict: Literal["SAFE_TO_BUY", "PROCEED_WITH_CAUTION", "HIGH_RISK_AVOID"] = Field(
        description="魔鬼代言人審查結論"
    )
    suggested_risk_hedges: List[str] = Field(description="若堅持做多，建議之避險或更嚴格停損措施")


class NeutralAIAnalysisReport(BaseModel):
    """資深機構風控投資長（CIO）之中立綜合判斷報告"""
    stock_symbol: str = Field(description="股票代號")
    company_name: str = Field(description="公司名稱")
    analysis_timestamp: str = Field(description="分析時間點 (ISO 8601)")
    overall_market_bias: Literal[
        "STRONG_BULLISH", "LEAN_BULLISH", "NEUTRAL", "LEAN_BEARISH", "STRONG_BEARISH"
    ] = Field(description="總體市場多空傾向")
    confidence_score: float = Field(ge=0.0, le=100.0, description="判斷置信度 (0~100)")
    macro_environment_summary: str = Field(description="全球總經與跨市場流動性環境總結")
    supply_chain_moat_summary: str = Field(description="產業地位、定價權與客戶依賴度總結")
    fundamental_health_summary: str = Field(description="財報健康度、F-Score 與河流圖估值位階總結")
    smart_money_summary: str = Field(description="法人籌碼沉澱度與融資散戶浮額總結")
    bull_catalysts: List[str] = Field(description="支持做多的客觀量化催化劑清單")
    bear_risks: List[str] = Field(description="壓抑股價的潛在致命風險與利空清單")
    neutral_synthesis_judgment: str = Field(
        description="不偏不倚的資深機構投資長客觀研判總結（兼顧催化劑與潛在風險，不盲目樂觀亦不盲目看空）"
    )
    unallocated_action_plan: str = Field(description="針對尚未買進者（現價預測）之具體操作建議")
    allocated_position_plan: str = Field(description="針對已持有者（持倉均價）之保本停損與分批停利建議")
    recommended_position_cap_pct: float = Field(
        ge=0.0, le=30.0, description="整體投資組合建議配置上限比例 (%)"
    )

