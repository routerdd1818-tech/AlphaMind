/**
 * AlphaMind AI — End-to-End TypeScript Domain Interfaces
 * Strictly typed definitions for PostgreSQL/TimescaleDB, Neo4j Graph, Redis payloads,
 * Global Macro / Rates / FX, and Unallocated vs. Allocated Target/Stop Recommendations.
 */

// ------------------------------------------------------------------------------
// 0. Geographic Regions & Market Types
// ------------------------------------------------------------------------------
export type MacroRegion = 'TW' | 'US' | 'JP' | 'KR' | 'HK' | 'EU';
export type MarketType = 'TWSE' | 'TPEx' | 'NYSE' | 'NASDAQ' | 'TSE' | 'KRX' | 'HKEX' | 'EURONEXT';
export type CurrencyCode = 'TWD' | 'USD' | 'JPY' | 'KRW' | 'HKD' | 'EUR';

// ------------------------------------------------------------------------------
// 1. Relational & Time-Series Entities (PostgreSQL + TimescaleDB)
// ------------------------------------------------------------------------------

export interface CompanyEntity {
  stockSymbol: string;
  name: string;
  market: MarketType;
  region: MacroRegion;
  currency: CurrencyCode;
  sharesOutstanding: number | null;
  industryCategory: string;
  isActive: boolean;
  createdAt: string;
  updatedAt: string;
}

export interface ConceptSectorEntity {
  sectorId: string;
  name: string;
  description: string | null;
  createdAt: string;
}

export interface CompanySectorTagEntity {
  stockSymbol: string;
  sectorId: string;
  weight: number; // 0.000 ~ 1.000
  createdAt: string;
}

export interface MarketTickEntity {
  time: string; // ISO 8601
  stockSymbol: string;
  price: number;
  volume: number;
  turnover: number;
  bidAskFlag: 1 | -1 | 0;
  isLargeOrder: boolean;
  createdAt: string;
}

export interface MarketOHLCV1mEntity {
  time: string;
  stockSymbol: string;
  open: number;
  high: number;
  low: number;
  close: number;
  vwap: number;
  volume: number;
  turnover: number;
  buyVolume: number;
  sellVolume: number;
  largeOrderNetVolume: number;
}

export interface MarketOHLCV1dEntity {
  time: string;
  stockSymbol: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  turnover: number;
  foreignBuyNet: number;
  investmentTrustBuyNet: number;
  dealerBuyNet: number;
  marginBalance: number;
  shortBalance: number;
  majorHoldersRatio: number | null;
  createdAt: string;
}

export interface SectorMoneyFlowSnapshotEntity {
  time: string;
  sectorId: string;
  turnover: number;
  marketTurnover: number;
  turnoverRatio: number;
  deltaTurnoverRatio5m: number | null;
  deltaTurnoverRatio15m: number | null;
  deltaTurnoverRatio60m: number | null;
  marketCapRatio: number;
  flowRatio: number;
  leadingStockSymbol: string | null;
  netLargeOrderInflow: number | null;
}

// ------------------------------------------------------------------------------
// 2. Global Macro, FX, Rates, Expectations & Sentiment
// ------------------------------------------------------------------------------

export type MacroMetricName =
  | 'CPI_YOY'
  | 'CORE_CPI'
  | 'PPI_YOY'
  | 'MANUFACTURING_PMI'
  | 'SERVICES_PMI'
  | 'GDP_GROWTH'
  | 'UNEMPLOYMENT_RATE';

export interface MacroEconomicMetricEntity {
  time: string;
  region: MacroRegion;
  metricName: MacroMetricName;
  value: number;
  consensusValue: number | null;
  previousValue: number | null;
  surprisePct: number | null;
  source: string;
  createdAt: string;
}

export interface MacroRatesFxEntity {
  time: string;
  region: MacroRegion;
  centralBankPolicyRate: number;
  yield2y: number | null;
  yield10y: number | null;
  yieldSpread10y2y: number | null;
  fxToUsd: number;
  fxChangePct1d: number | null;
  dxyIndex: number | null;
  createdAt: string;
}

export interface RateCutExpectationsEntity {
  time: string;
  region: MacroRegion;
  targetMeetingDate: string;
  currentTargetRateRange: string;
  probCut25bp: number;
  probCut50bp: number;
  probHold: number;
  probHike25bp: number;
  impliedTerminalRate: number | null;
  source: string;
}

export interface MarketVolatilitySentimentEntity {
  time: string;
  region: MacroRegion;
  volatilityIndexValue: number;
  volatilityTermStructureRatio: number | null;
  putCallRatio: number | null;
  fearGreedScore: number | null;
  marginMaintenanceRatio: number | null;
  foreignLiquidityBias: 'STRONG_INFLOW' | 'NEUTRAL' | 'FLIGHT_TO_SAFETY' | null;
}

// ------------------------------------------------------------------------------
// 3. Unallocated (Market Price) vs Allocated (Avg Cost) Targets & Stops
// ------------------------------------------------------------------------------

export interface UnallocatedTargetStopRecommendation {
  stockSymbol: string;
  currentMarketPrice: number;
  suggestedEntryZoneLow: number;
  suggestedEntryZoneHigh: number;
  initialStopLossPrice: number;
  maxRiskPct: number;
  takeProfitTargetConservative: number;
  takeProfitTargetConsensus: number;
  takeProfitTargetOptimistic: number;
  riskRewardRatio: number;
  isFavorableEntry: boolean;
}

export type AllocatedActionRecommendation =
  | 'HOLD_AND_TRAILING'
  | 'TAKE_PROFIT_TIER_1'
  | 'TAKE_PROFIT_TIER_2'
  | 'BREAK_EVEN_STOP'
  | 'FORCE_CUT_LOSS'
  | 'HOLD_STRICT_STOP';

export interface AllocatedPositionStrategyRecommendation {
  stockSymbol: string;
  avgCostPrice: number;
  currentMarketPrice: number;
  unrealizedPnlPct: number;
  holdingDays: number;
  breakEvenProtectionActive: boolean;
  breakEvenStopPrice: number;
  effectiveTrailingStopPrice: number;
  effectiveStopDistancePct: number;
  tieredTakeProfitLadder: {
    tier1TakeProfit33pct: number;
    tier2TakeProfit33pct: number;
  };
  actionRecommendation: AllocatedActionRecommendation;
  actionRationale: string;
}

export type MarketBiasType =
  | 'STRONG_BULLISH'
  | 'LEAN_BULLISH'
  | 'NEUTRAL'
  | 'LEAN_BEARISH'
  | 'STRONG_BEARISH';

export interface NeutralAIAnalysisReport {
  stockSymbol: string;
  companyName: string;
  analysisTimestamp: string;
  overallMarketBias: MarketBiasType;
  confidenceScore: number;
  macroEnvironmentSummary: string;
  supplyChainMoatSummary: string;
  fundamentalHealthSummary: string;
  smartMoneySummary: string;
  bullCatalysts: string[];
  bearRisks: string[];
  neutralSynthesisJudgment: string;
  unallocatedActionPlan: string;
  allocatedPositionPlan: string;
  recommendedPositionCapPct: number;
}

// ------------------------------------------------------------------------------
// 4. Fundamental Health & Target/Stop-Loss Levels
// ------------------------------------------------------------------------------

export interface FinancialReportEntity {
  id: number;
  stockSymbol: string;
  year: number;
  quarter: 1 | 2 | 3 | 4;
  revenue: number;
  grossProfit: number;
  operatingIncome: number;
  netIncome: number;
  eps: number;
  operatingCashFlow: number | null;
  freeCashFlow: number | null;
  grossMargin: number;
  operatingMargin: number;
  netMargin: number;
  grossMarginQoqSlope: number | null;
  operatingMarginQoqSlope: number | null;
  piotroskiFScore: number | null;
  altmanZScore: number | null;
  rawStatementData: Record<string, unknown> | null;
  createdAt: string;
}

export interface PriceTargetStopLevelsEntity {
  id: number;
  stockSymbol: string;
  asOfDate: string;
  targetPriceConservative: number | null;
  targetPriceConsensus: number | null;
  targetPriceOptimistic: number | null;
  forwardReturn20dPred: number | null;
  atr14: number;
  dynamicStopLossPrice: number;
  institutionalVwap20d: number | null;
  createdAt: string;
}

export type EventCategory =
  | 'CAPEX_EXPANSION'
  | 'ORDER_LOSS'
  | 'EARNINGS_CALL'
  | 'GEOPOLITICS'
  | 'MANAGEMENT_CHANGE'
  | 'PRODUCT_LAUNCH'
  | 'GENERAL_INDUSTRY';

export type ImpactHorizon = 'SHORT_TERM' | 'LONG_TERM';

export interface NewsFeatureEntity {
  id: string;
  source: string;
  title: string;
  content: string;
  url: string | null;
  publishedAt: string;
  sentimentScore: number;
  eventCategory: EventCategory;
  impactHorizon: ImpactHorizon;
  mentionedSymbols: string[];
  affectedGraphNodes: string[];
  embedding?: number[];
  rawMetadata?: Record<string, unknown>;
  createdAt: string;
}

// ------------------------------------------------------------------------------
// 5. Neo4j Supply Chain Graph Node & Relationship Models
// ------------------------------------------------------------------------------

export interface GraphCompanyNode {
  symbol: string;
  name: string;
  market: MarketType;
  region: MacroRegion;
  marketCap: number;
  industry: string;
}

export interface GraphProductNode {
  id: string;
  name: string;
  category: string;
}

export interface GraphMaterialNode {
  id: string;
  name: string;
  chemicalType: string;
}

export interface GraphConceptTagNode {
  id: string;
  name: string;
  category: string;
}

export interface SuppliesToRelationship {
  revenueShare: number;
  confidence: number;
  isSoleSupplier: boolean;
  substitutabilityScore: number;
  sourceDoc: string;
  verifiedByHuman: boolean;
  updatedAt: string;
}

// ------------------------------------------------------------------------------
// 6. Redis In-Memory Real-Time Models
// ------------------------------------------------------------------------------

export interface RedisLiveQuotePayload {
  p: number;
  chg: number;
  pct: number;
  v: number;
  tv: number;
  vwap: number;
  b1: number;
  bv1: number;
  a1: number;
  av1: number;
  buy_v: number;
  sell_v: number;
  net_large_inflow: number;
  ts: number;
}
