"""
AlphaMind AI — Real-Time Sector Money Flow Engine
Calculates real-time order book force, sector turnover ratios, and money flow velocity.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Set
import numpy as np


@dataclass(frozen=True)
class TickData:
    symbol: str
    price: float
    volume: int              # 股數
    turnover: float          # 成交金額 (TWD)
    bid_ask_flag: int        # 1: 外盤買進, -1: 內盤賣出, 0: 無方向
    timestamp: datetime
    is_large_order: bool = False


@dataclass
class StockRealtimeState:
    symbol: str
    last_price: float = 0.0
    accumulated_volume: int = 0
    accumulated_turnover: float = 0.0
    buy_volume: int = 0
    sell_volume: int = 0
    net_large_inflow: float = 0.0
    vwap: float = 0.0
    last_tick_time: Optional[datetime] = None


@dataclass
class SectorConfig:
    sector_id: str
    name: str
    market_cap: float          # 族群總市值 (TWD)
    symbols: Set[str] = field(default_factory=set)


@dataclass
class SectorFlowSignal:
    sector_id: str
    timestamp: datetime
    turnover: float
    turnover_ratio: float
    delta_turnover_ratio: float
    market_cap_ratio: float
    flow_ratio: float
    is_flow_inflow_breakout: bool
    leading_stock: Optional[str] = None
    leading_stock_price: float = 0.0
    leading_stock_vwap: float = 0.0


class SectorMoneyFlowEngine:
    """
    即時資金流向與族群熱度引擎：
    1. 主動買賣盤力道累計（外盤量 - 內盤量）與大單過濾。
    2. 依滑動窗口（5m / 15m / 60m）計算資金流向比 (Sector Money Flow Ratio)。
    3. 當 Flow Ratio > 1.5 且指標龍頭股站上 VWAP 時觸發異動信號。
    """

    def __init__(
        self,
        total_market_cap: float,
        large_order_threshold: float = 5_000_000.0,
        flow_ratio_threshold: float = 1.5,
    ) -> None:
        self.total_market_cap = max(total_market_cap, 1.0)
        self.large_order_threshold = large_order_threshold
        self.flow_ratio_threshold = flow_ratio_threshold

        self.stocks: Dict[str, StockRealtimeState] = {}
        self.sectors: Dict[str, SectorConfig] = {}
        self.symbol_to_sectors: Dict[str, Set[str]] = {}

        # 族群歷史時間序列滑動紀錄: sector_id -> List of (timestamp, accumulated_turnover, total_market_turnover)
        self.turnover_history: Dict[str, List[tuple[datetime, float, float]]] = {}
        self.total_market_turnover: float = 0.0

    def register_sector(self, sector_id: str, name: str, market_cap: float, symbols: List[str]) -> None:
        cfg = SectorConfig(sector_id=sector_id, name=name, market_cap=market_cap, symbols=set(symbols))
        self.sectors[sector_id] = cfg
        self.turnover_history[sector_id] = []

        for sym in symbols:
            if sym not in self.stocks:
                self.stocks[sym] = StockRealtimeState(symbol=sym)
            if sym not in self.symbol_to_sectors:
                self.symbol_to_sectors[sym] = set()
            self.symbol_to_sectors[sym].add(sector_id)

    def process_tick(self, tick: TickData) -> List[SectorFlowSignal]:
        """處理單筆成交 Tick 並即時更新各族群狀態"""
        # 1. 更新個股狀態
        state = self.stocks.get(tick.symbol)
        if state is None:
            state = StockRealtimeState(symbol=tick.symbol)
            self.stocks[tick.symbol] = state

        state.last_price = tick.price
        state.accumulated_volume += tick.volume
        state.accumulated_turnover += tick.turnover
        self.total_market_turnover += tick.turnover

        if state.accumulated_volume > 0:
            state.vwap = state.accumulated_turnover / state.accumulated_volume

        if tick.bid_ask_flag == 1:
            state.buy_volume += tick.volume
        elif tick.bid_ask_flag == -1:
            state.sell_volume += tick.volume

        # 大單判斷 (單筆金額 > 門檻)
        is_large = tick.turnover >= self.large_order_threshold or tick.is_large_order
        if is_large:
            # 外盤大單加分，內盤大單扣分
            net_inflow = tick.turnover if tick.bid_ask_flag == 1 else (-tick.turnover if tick.bid_ask_flag == -1 else 0.0)
            state.net_large_inflow += net_inflow

        state.last_tick_time = tick.timestamp

        # 2. 更新所屬族群滑動窗口
        affected_sectors = self.symbol_to_sectors.get(tick.symbol, set())
        signals: List[SectorFlowSignal] = []

        for sec_id in affected_sectors:
            sec_cfg = self.sectors[sec_id]
            # 累計族群目前成交額
            sec_turnover = sum(self.stocks[s].accumulated_turnover for s in sec_cfg.symbols if s in self.stocks)
            self.turnover_history[sec_id].append((tick.timestamp, sec_turnover, self.total_market_turnover))

            # 計算 5 分鐘前 (300 秒) 的快照
            delta_ratio = self._calculate_delta_turnover_ratio(sec_id, tick.timestamp, window_seconds=300)

            # 市值比重
            market_cap_ratio = sec_cfg.market_cap / self.total_market_cap
            current_turnover_ratio = sec_turnover / max(self.total_market_turnover, 1.0)

            # 資金流向比 Flow Ratio
            flow_ratio = (delta_ratio / market_cap_ratio) if market_cap_ratio > 0 else 0.0

            # 尋找當前族群龍頭股 (成交額最大或漲幅最強)
            leading_symbol, lead_price, lead_vwap = self._get_sector_leader(sec_cfg)

            # 判斷突破：flow_ratio > threshold 且龍頭股價格站上 VWAP
            is_breakout = bool(flow_ratio >= self.flow_ratio_threshold and lead_price >= lead_vwap and lead_price > 0)

            signals.append(
                SectorFlowSignal(
                    sector_id=sec_id,
                    timestamp=tick.timestamp,
                    turnover=sec_turnover,
                    turnover_ratio=current_turnover_ratio,
                    delta_turnover_ratio=delta_ratio,
                    market_cap_ratio=market_cap_ratio,
                    flow_ratio=flow_ratio,
                    is_flow_inflow_breakout=is_breakout,
                    leading_stock=leading_symbol,
                    leading_stock_price=lead_price,
                    leading_stock_vwap=lead_vwap,
                )
            )

        return signals

    def _calculate_delta_turnover_ratio(self, sector_id: str, current_time: datetime, window_seconds: int) -> float:
        history = self.turnover_history.get(sector_id, [])
        if not history:
            return 0.0

        current_entry = history[-1]
        cur_sec_to, cur_mkt_to = current_entry[1], current_entry[2]
        cur_ratio = cur_sec_to / max(cur_mkt_to, 1.0)

        cutoff = (current_time.timestamp() - window_seconds)
        # 尋找 window_seconds 前最接近的歷史點
        past_entry = None
        for entry in history:
            if entry[0].timestamp() <= cutoff:
                past_entry = entry
            else:
                break

        if past_entry is None:
            # 歷史不足整個 window，使用最早期點
            past_entry = history[0]

        past_sec_to, past_mkt_to = past_entry[1], past_entry[2]
        past_ratio = past_sec_to / max(past_mkt_to, 1.0)

        # 增量
        delta_ratio = max(0.0, cur_ratio - past_ratio)
        return float(delta_ratio)

    def _get_sector_leader(self, sec_cfg: SectorConfig) -> tuple[Optional[str], float, float]:
        best_symbol: Optional[str] = None
        best_turnover: float = -1.0
        lead_price: float = 0.0
        lead_vwap: float = 0.0

        for sym in sec_cfg.symbols:
            st = self.stocks.get(sym)
            if st and st.accumulated_turnover > best_turnover:
                best_turnover = st.accumulated_turnover
                best_symbol = sym
                lead_price = st.last_price
                lead_vwap = st.vwap

        return best_symbol, lead_price, lead_vwap
