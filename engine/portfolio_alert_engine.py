"""
AlphaMind AI — Asset Calculator, Position Strategy Evaluator, Watchlist Manager,
and Price Target / K-Line Pattern Transition Alert Engine.
"""

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class PositionEntry:
    symbol: str
    name: str
    shares: int                          # 持有股數 (如 1000 股 = 1 張)
    avg_cost_price: float                # 買進平均成本價
    custom_target_price: Optional[float] = None
    custom_stop_price: Optional[float] = None
    last_recorded_pattern: str = "區間箱型量縮整理"
    notes: str = ""


@dataclass
class WatchlistEntry:
    symbol: str
    name: str
    target_buy_price: Optional[float] = None
    added_at: str = ""


@dataclass
class SmartAlertItem:
    alert_id: str
    symbol: str
    name: str
    alert_type: str        # 'TARGET_PRICE_REACHED', 'STOP_LOSS_WARNING', 'KLINE_PATTERN_TRANSITION', 'WATCHLIST_ENTRY_ZONE'
    severity: str          # 'HIGH', 'MEDIUM', 'INFO'
    title: str
    message: str
    current_price: float
    trigger_level: float
    kline_pattern: str
    triggered_at: str


class PortfolioAndAlertEngine:
    """
    資產計算、持倉精算（含台股手續費與證交稅）、自選股管理，
    以及「到達策略目標價提醒」與「K 線型態轉變提醒」引擎。
    """

    def __init__(self, state_path: Optional[Path] = None, auto_seed: bool = True) -> None:
        default_path = Path(__file__).resolve().parent.parent / "user_portfolio_state.json"
        self.state_path = state_path or default_path
        self.auto_seed = auto_seed
        self.cash_twd: float = 1_500_000.0
        self.fee_discount: float = 0.60  # 預設電子下單手續費 6 折 (0.1425% * 0.6)
        self.positions: List[PositionEntry] = []
        self.watchlist: List[WatchlistEntry] = []
        self._load_or_init_default_state()

    def _load_or_init_default_state(self) -> None:
        if self.state_path.exists():
            try:
                raw = json.loads(self.state_path.read_text(encoding="utf-8"))
                self.cash_twd = float(raw.get("cash_twd", 1_500_000.0))
                self.fee_discount = float(raw.get("fee_discount", 0.60))
                self.positions = [PositionEntry(**p) for p in raw.get("positions", [])]
                self.watchlist = [WatchlistEntry(**w) for w in raw.get("watchlist", [])]
                return
            except Exception:
                pass

        if not self.auto_seed:
            return

        # 預設展示持倉與自選股（可隨時由前端新增/修改/刪除）
        self.cash_twd = 1_500_000.0
        self.positions = [
            PositionEntry(
                symbol="2330",
                name="台積電",
                shares=2000,
                avg_cost_price=920.0,
                custom_target_price=1050.0,
                custom_stop_price=985.0,
                last_recorded_pattern="均線多頭排列穩步推升",
                notes="核心半導體長線部位",
            ),
            PositionEntry(
                symbol="2317",
                name="鴻海",
                shares=5000,
                avg_cost_price=186.0,
                custom_target_price=215.0,
                custom_stop_price=196.0,
                last_recorded_pattern="區間箱型量縮整理",
                notes="GB200 機櫃出貨波段",
            ),
            PositionEntry(
                symbol="00878",
                name="國泰永續高股息",
                shares=20000,
                avg_cost_price=21.40,
                custom_target_price=24.0,
                custom_stop_price=20.2,
                last_recorded_pattern="均線多頭排列穩步推升",
                notes="高股息現金流底倉",
            ),
            PositionEntry(
                symbol="3661",
                name="世芯-KY",
                shares=200,
                avg_cost_price=2750.0,
                custom_target_price=3100.0,
                custom_stop_price=2560.0,
                last_recorded_pattern="區間箱型量縮整理",
                notes="ASIC 零股波段單",
            ),
        ]
        self.watchlist = [
            WatchlistEntry(symbol="2330", name="台積電", target_buy_price=1025.0, added_at="2026-11-01"),
            WatchlistEntry(symbol="2454", name="聯發科", target_buy_price=1285.0, added_at="2026-11-01"),
            WatchlistEntry(symbol="3017", name="奇鋐", target_buy_price=645.0, added_at="2026-11-02"),
            WatchlistEntry(symbol="2382", name="廣達", target_buy_price=304.0, added_at="2026-11-02"),
            WatchlistEntry(symbol="0050", name="元大台灣50", target_buy_price=189.0, added_at="2026-11-02"),
            WatchlistEntry(symbol="2603", name="長榮", target_buy_price=206.0, added_at="2026-11-03"),
        ]
        self._save_state()

    def _save_state(self) -> None:
        try:
            payload = {
                "cash_twd": self.cash_twd,
                "fee_discount": self.fee_discount,
                "positions": [p.__dict__ for p in self.positions],
                "watchlist": [w.__dict__ for w in self.watchlist],
            }
            self.state_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

    # --------------------------------------------------------------------------
    # 1. 台股交易成本精算 (手續費 0.1425% * 折數 + 證交稅 一般股 0.3% / ETF 0.1%)
    # --------------------------------------------------------------------------
    def calc_tw_transaction_costs(
        self, symbol: str, shares: int, entry_price: float, current_price: float
    ) -> Dict[str, float]:
        is_etf = str(symbol).strip().startswith("00")
        tax_rate = 0.001 if is_etf else 0.003
        eff_fee_rate = 0.001425 * self.fee_discount

        gross_cost = shares * entry_price
        buy_fee = max(20.0, round(gross_cost * eff_fee_rate)) if shares > 0 else 0.0
        total_invested_cost = gross_cost + buy_fee

        gross_market_val = shares * current_price
        sell_fee = max(20.0, round(gross_market_val * eff_fee_rate)) if shares > 0 else 0.0
        sell_tax = round(gross_market_val * tax_rate)
        net_liquidation_val = gross_market_val - sell_fee - sell_tax

        net_pnl = net_liquidation_val - total_invested_cost
        net_pnl_pct = (net_pnl / total_invested_cost * 100.0) if total_invested_cost > 0 else 0.0

        return {
            "is_etf": is_etf,
            "tax_rate_pct": round(tax_rate * 100.0, 2),
            "gross_cost": round(gross_cost, 0),
            "buy_fee": round(buy_fee, 0),
            "total_invested_cost": round(total_invested_cost, 0),
            "gross_market_value": round(gross_market_val, 0),
            "est_sell_fee": round(sell_fee, 0),
            "est_sell_tax": round(sell_tax, 0),
            "net_liquidation_value": round(net_liquidation_val, 0),
            "net_unrealized_pnl": round(net_pnl, 0),
            "net_unrealized_pnl_pct": round(net_pnl_pct, 2),
        }

    # --------------------------------------------------------------------------
    # 2. 資產總覽、持倉計算與「目標價 / 型態轉變」智慧提醒評估
    # --------------------------------------------------------------------------
    def evaluate_portfolio_and_alerts(self, universe_engine: Any) -> Dict[str, Any]:
        # 建立市場快照索引
        stock_items = universe_engine.get_stock_universe()
        stock_map = {s.symbol: s for s in stock_items}
        etf_hub = universe_engine.get_etf_hub_data()
        etf_map = {e["etf_symbol"]: e for e in etf_hub["etf_list"]}

        evaluated_positions: List[Dict[str, Any]] = []
        alerts: List[SmartAlertItem] = []

        total_invested = 0.0
        total_market_value = 0.0
        total_net_liquidation = 0.0
        now_str = datetime.now().strftime("%H:%M:%S")

        for pos in self.positions:
            sym = pos.symbol.upper()
            st = stock_map.get(sym)
            et = etf_map.get(sym)

            if st:
                cur_px = st.price
                chg_pct = st.change_pct
                k_pat = st.kline_pattern
                k_bias = st.kline_bias
                sector = st.primary_sector
                strat_target = st.consensus_target
                strat_stop = st.stop_loss
            elif et:
                cur_px = float(et["price"])
                chg_pct = float(et["change_pct"])
                k_pat = "均線多頭排列穩步推升" if chg_pct >= 0 else "區間箱型量縮整理"
                k_bias = "BULLISH" if chg_pct >= 0 else "NEUTRAL"
                sector = f"ETF ({et['category']})"
                strat_target = round(pos.avg_cost_price * 1.12, 2)
                strat_stop = round(pos.avg_cost_price * 0.94, 2)
            else:
                cur_px = pos.avg_cost_price
                chg_pct = 0.0
                k_pat = pos.last_recorded_pattern
                k_bias = "NEUTRAL"
                sector = "台股一般"
                strat_target = round(pos.avg_cost_price * 1.15, 2)
                strat_stop = round(pos.avg_cost_price * 0.93, 2)

            costs = self.calc_tw_transaction_costs(sym, pos.shares, pos.avg_cost_price, cur_px)
            total_invested += costs["total_invested_cost"]
            total_market_value += costs["gross_market_value"]
            total_net_liquidation += costs["net_liquidation_value"]

            # 計算以「購入均價」為錨點之階梯停利與保本停損
            tier_1_target = round(pos.avg_cost_price * 1.15, 2)
            tier_2_target = round(pos.avg_cost_price * 1.25, 2)
            effective_target = pos.custom_target_price if pos.custom_target_price else min(strat_target, tier_1_target)

            # 若帳面報酬 >= 8% 啟動保本停損 (成本 * 1.01)
            break_even_active = costs["net_unrealized_pnl_pct"] >= 8.0
            break_even_stop = round(pos.avg_cost_price * 1.01, 2) if break_even_active else 0.0
            base_stop = pos.custom_stop_price if pos.custom_stop_price else strat_stop
            effective_stop = max(base_stop, break_even_stop)

            dist_to_target_pct = round((effective_target - cur_px) / cur_px * 100.0, 2)
            dist_to_stop_pct = round((cur_px - effective_stop) / cur_px * 100.0, 2)

            # 判斷持倉策略建議動作
            if cur_px <= effective_stop:
                pos_action = "STOP_LOSS_EXIT"
                pos_action_zh = "觸及停損・立即出場"
            elif cur_px >= effective_target:
                pos_action = "TARGET_REACHED_TAKE_PROFIT"
                pos_action_zh = "達標停利・分批減碼 1/3"
            elif k_bias == "BEARISH":
                pos_action = "PATTERN_WEAKENING_TRIM"
                pos_action_zh = "型態轉弱・提高警覺"
            elif break_even_active:
                pos_action = "HOLD_WITH_BREAKEVEN_LOCK"
                pos_action_zh = "保本鎖利・續抱移動停損"
            else:
                pos_action = "HOLD_NORMAL"
                pos_action_zh = "守穩支撐・依紀律續抱"

            # --- 觸發提醒 1：到達策略目標價提醒 ---
            if cur_px >= effective_target or dist_to_target_pct <= 1.2:
                reached = cur_px >= effective_target
                alerts.append(
                    SmartAlertItem(
                        alert_id=f"ALT-TGT-{sym}",
                        symbol=sym,
                        name=pos.name,
                        alert_type="TARGET_PRICE_REACHED",
                        severity="HIGH" if reached else "MEDIUM",
                        title=f"{sym} {pos.name} {'已達策略目標價' if reached else '逼近策略目標價 (差距 < 1.2%)'}",
                        message=(
                            f"現價 {cur_px} {'已突破' if reached else '即將觸及'}設定之策略目標價 {effective_target} "
                            f"（持股均價 {pos.avg_cost_price}，淨損益 {costs['net_unrealized_pnl_pct']:+.2f}%）。"
                            f"建議執行階梯停利減碼 1/3 鎖定獲利，並將剩餘部位停損上移至保本價 {max(break_even_stop, round(pos.avg_cost_price * 1.01, 2))}。"
                        ),
                        current_price=cur_px,
                        trigger_level=effective_target,
                        kline_pattern=k_pat,
                        triggered_at=now_str,
                    )
                )

            # --- 觸發提醒 2：停損防護警示 ---
            if cur_px <= effective_stop or dist_to_stop_pct <= 2.5:
                breached = cur_px <= effective_stop
                alerts.append(
                    SmartAlertItem(
                        alert_id=f"ALT-STP-{sym}",
                        symbol=sym,
                        name=pos.name,
                        alert_type="STOP_LOSS_WARNING",
                        severity="HIGH",
                        title=f"{sym} {pos.name} {'跌破有效停損線' if breached else '逼近停損防線警戒'}",
                        message=(
                            f"現價 {cur_px} 距離有效停損價 {effective_stop} 僅剩 {dist_to_stop_pct:.2f}%。"
                            f"請嚴格執行本金保護紀律，禁止向下攤平。"
                        ),
                        current_price=cur_px,
                        trigger_level=effective_stop,
                        kline_pattern=k_pat,
                        triggered_at=now_str,
                    )
                )

            # --- 觸發提醒 3：K 線型態轉變提醒 ---
            if k_pat != pos.last_recorded_pattern or any(
                kw in k_pat for kw in ["吞噬", "突破", "射擊之星", "晨星", "夜星", "跌破"]
            ):
                is_bear_shift = k_bias == "BEARISH"
                alerts.append(
                    SmartAlertItem(
                        alert_id=f"ALT-PAT-{sym}",
                        symbol=sym,
                        name=pos.name,
                        alert_type="KLINE_PATTERN_TRANSITION",
                        severity="HIGH" if is_bear_shift else "MEDIUM",
                        title=f"{sym} {pos.name} K 線型態轉變：{k_pat}",
                        message=(
                            f"型態由「{pos.last_recorded_pattern}」轉變為「{k_pat}」（方向：{k_bias}）。"
                            + (
                                f"高檔出現轉弱訊號，建議收緊移動停損至 {effective_stop}。"
                                if is_bear_shift
                                else f"多頭型態確認，支撐上移至 {effective_stop}，目標看至 {effective_target}。"
                            )
                        ),
                        current_price=cur_px,
                        trigger_level=effective_stop if is_bear_shift else effective_target,
                        kline_pattern=k_pat,
                        triggered_at=now_str,
                    )
                )

            evaluated_positions.append({
                "symbol": sym,
                "name": pos.name,
                "sector": sector,
                "shares": pos.shares,
                "avg_cost_price": pos.avg_cost_price,
                "current_price": cur_px,
                "change_pct": chg_pct,
                "gross_market_value": costs["gross_market_value"],
                "total_invested_cost": costs["total_invested_cost"],
                "net_liquidation_value": costs["net_liquidation_value"],
                "est_fee_and_tax": costs["buy_fee"] + costs["est_sell_fee"] + costs["est_sell_tax"],
                "net_unrealized_pnl": costs["net_unrealized_pnl"],
                "net_unrealized_pnl_pct": costs["net_unrealized_pnl_pct"],
                "effective_target_price": effective_target,
                "tier_1_target_price": tier_1_target,
                "tier_2_target_price": tier_2_target,
                "effective_stop_price": effective_stop,
                "break_even_active": break_even_active,
                "dist_to_target_pct": dist_to_target_pct,
                "dist_to_stop_pct": dist_to_stop_pct,
                "kline_pattern": k_pat,
                "kline_bias": k_bias,
                "action_code": pos_action,
                "action_label": pos_action_zh,
                "notes": pos.notes,
            })

        # 評估自選股清單與買點提醒
        evaluated_watchlist: List[Dict[str, Any]] = []
        for w in self.watchlist:
            sym = w.symbol.upper()
            st = stock_map.get(sym)
            et = etf_map.get(sym)
            if st:
                cur_px = st.price
                chg_pct = st.change_pct
                k_pat = st.kline_pattern
                k_bias = st.kline_bias
                gate_action = st.gate_action
                entry_zone = st.entry_zone
                stop_px = st.stop_loss
                target_px = st.consensus_target
                rr = st.risk_reward
                sector = st.primary_sector
            elif et:
                cur_px = float(et["price"])
                chg_pct = float(et["change_pct"])
                k_pat = "ETF 淨值追蹤穩定"
                k_bias = "BULLISH" if chg_pct >= 0 else "NEUTRAL"
                gate_action = "ACCUMULATE"
                entry_zone = f"{cur_px * 0.985:.2f} ~ {cur_px:.2f}"
                stop_px = round(cur_px * 0.94, 2)
                target_px = round(cur_px * 1.12, 2)
                rr = 2.0
                sector = f"ETF ({et['category']})"
            else:
                cur_px = 100.0
                chg_pct = 0.0
                k_pat = "區間箱型量縮整理"
                k_bias = "NEUTRAL"
                gate_action = "HOLD"
                entry_zone = "98.0 ~ 100.0"
                stop_px = 93.0
                target_px = 112.0
                rr = 1.8
                sector = "台股一般"

            in_buy_zone = bool(w.target_buy_price and cur_px <= w.target_buy_price * 1.015)
            if in_buy_zone and w.target_buy_price:
                alerts.append(
                    SmartAlertItem(
                        alert_id=f"ALT-WCH-{sym}",
                        symbol=sym,
                        name=w.name,
                        alert_type="WATCHLIST_ENTRY_ZONE",
                        severity="INFO",
                        title=f"自選股 {sym} {w.name} 進入理想承接區間",
                        message=f"現價 {cur_px} 已回測接近自訂買進提醒價 {w.target_buy_price}（策略建議區間 {entry_zone}，K 線：{k_pat}）。",
                        current_price=cur_px,
                        trigger_level=w.target_buy_price,
                        kline_pattern=k_pat,
                        triggered_at=now_str,
                    )
                )

            evaluated_watchlist.append({
                "symbol": sym,
                "name": w.name,
                "sector": sector,
                "price": cur_px,
                "change_pct": chg_pct,
                "target_buy_price": w.target_buy_price,
                "in_buy_zone": in_buy_zone,
                "kline_pattern": k_pat,
                "kline_bias": k_bias,
                "gate_action": gate_action,
                "entry_zone": entry_zone,
                "stop_loss": stop_px,
                "consensus_target": target_px,
                "risk_reward": rr,
            })

        total_equity = self.cash_twd + total_net_liquidation
        total_net_pnl = total_net_liquidation - total_invested
        total_net_pnl_pct = (total_net_pnl / total_invested * 100.0) if total_invested > 0 else 0.0
        cash_weight_pct = (self.cash_twd / total_equity * 100.0) if total_equity > 0 else 100.0
        stock_weight_pct = 100.0 - cash_weight_pct

        # 產業部位權重分佈
        sector_alloc: Dict[str, float] = {"現金儲備 (TWD)": round(self.cash_twd, 0)}
        for ep in evaluated_positions:
            sec = ep["sector"]
            sector_alloc[sec] = sector_alloc.get(sec, 0.0) + ep["net_liquidation_value"]

        allocation_breakdown = [
            {
                "category": k,
                "value_twd": round(v, 0),
                "weight_pct": round(v / total_equity * 100.0, 1) if total_equity > 0 else 0.0,
            }
            for k, v in sector_alloc.items()
        ]
        allocation_breakdown.sort(key=lambda x: x["value_twd"], reverse=True)

        return {
            "asset_summary": {
                "total_equity_twd": round(total_equity, 0),
                "cash_twd": round(self.cash_twd, 0),
                "total_invested_cost_twd": round(total_invested, 0),
                "gross_market_value_twd": round(total_market_value, 0),
                "net_liquidation_value_twd": round(total_net_liquidation, 0),
                "total_net_unrealized_pnl_twd": round(total_net_pnl, 0),
                "total_net_unrealized_pnl_pct": round(total_net_pnl_pct, 2),
                "cash_weight_pct": round(cash_weight_pct, 1),
                "invested_weight_pct": round(stock_weight_pct, 1),
                "fee_discount": self.fee_discount,
                "position_count": len(evaluated_positions),
                "allocation_breakdown": allocation_breakdown,
            },
            "positions": evaluated_positions,
            "watchlist": evaluated_watchlist,
            "alerts": [a.__dict__ for a in alerts],
        }

    # --------------------------------------------------------------------------
    # 3. 持倉、現金與自選股 CRUD 操作
    # --------------------------------------------------------------------------
    def update_cash_and_settings(self, cash_twd: Optional[float] = None, fee_discount: Optional[float] = None) -> None:
        if cash_twd is not None and cash_twd >= 0:
            self.cash_twd = float(cash_twd)
        if fee_discount is not None and 0.1 <= fee_discount <= 1.0:
            self.fee_discount = float(fee_discount)
        self._save_state()

    def upsert_position(
        self,
        symbol: str,
        name: str,
        shares: int,
        avg_cost_price: float,
        custom_target_price: Optional[float] = None,
        custom_stop_price: Optional[float] = None,
        notes: str = "",
    ) -> None:
        sym = symbol.strip().upper()
        existing = next((p for p in self.positions if p.symbol.upper() == sym), None)
        if existing:
            existing.name = name or existing.name
            existing.shares = int(shares)
            existing.avg_cost_price = float(avg_cost_price)
            existing.custom_target_price = float(custom_target_price) if custom_target_price else None
            existing.custom_stop_price = float(custom_stop_price) if custom_stop_price else None
            existing.notes = notes
        else:
            self.positions.append(
                PositionEntry(
                    symbol=sym,
                    name=name or sym,
                    shares=int(shares),
                    avg_cost_price=float(avg_cost_price),
                    custom_target_price=float(custom_target_price) if custom_target_price else None,
                    custom_stop_price=float(custom_stop_price) if custom_stop_price else None,
                    notes=notes,
                )
            )
        self._save_state()

    def remove_position(self, symbol: str) -> None:
        sym = symbol.strip().upper()
        self.positions = [p for p in self.positions if p.symbol.upper() != sym]
        self._save_state()

    def add_watchlist_item(self, symbol: str, name: str, target_buy_price: Optional[float] = None) -> None:
        sym = symbol.strip().upper()
        existing = next((w for w in self.watchlist if w.symbol.upper() == sym), None)
        if existing:
            existing.name = name or existing.name
            existing.target_buy_price = float(target_buy_price) if target_buy_price else existing.target_buy_price
        else:
            self.watchlist.append(
                WatchlistEntry(
                    symbol=sym,
                    name=name or sym,
                    target_buy_price=float(target_buy_price) if target_buy_price else None,
                    added_at=datetime.now().strftime("%Y-%m-%d"),
                )
            )
        self._save_state()

    def remove_watchlist_item(self, symbol: str) -> None:
        sym = symbol.strip().upper()
        self.watchlist = [w for w in self.watchlist if w.symbol.upper() != sym]
        self._save_state()
