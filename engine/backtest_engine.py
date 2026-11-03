"""
AlphaMind AI — Multi-Strategy Vectorized & Event-Driven Backtesting Engine
Simulates portfolio equity curve, calculates CAGR, Max Drawdown (MDD), Sharpe Ratio,
Win Rate, Profit Factor, and trade log history.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional
import numpy as np
import pandas as pd


@dataclass
class TradeRecord:
    symbol: str
    entry_date: str
    entry_price: float
    exit_date: str
    exit_price: float
    shares: int
    return_pct: float
    pnl: float
    exit_reason: str


@dataclass
class BacktestSummary:
    strategy_name: str
    initial_capital: float
    final_equity: float
    total_return_pct: float
    cagr: float
    max_drawdown_pct: float
    sharpe_ratio: float
    win_rate_pct: float
    profit_factor: float
    total_trades: int
    equity_curve: List[Dict[str, float]]
    trade_history: List[TradeRecord]


class BacktestEngine:
    """向量化與事件驅動回測引擎"""

    def __init__(
        self,
        initial_capital: float = 10_000_000.0,
        risk_free_rate: float = 0.02, # 無風險利率 2%
        transaction_fee_rate: float = 0.001425 * 0.6, # 券商 6 折手續費
        transaction_tax_rate: float = 0.003,          # 台股證券交易稅 0.3%
        slippage_rate: float = 0.0015,                # 實盤滑價保護 (預設 0.15%)
    ) -> None:
        self.initial_capital = initial_capital
        self.risk_free_rate = risk_free_rate
        self.transaction_fee_rate = transaction_fee_rate
        self.transaction_tax_rate = transaction_tax_rate
        self.slippage_rate = slippage_rate

    def run_backtest(
        self,
        strategy_name: str,
        price_df: pd.DataFrame,          # 需包含: ['date', 'close', 'high', 'low', 'signal', 'stop_loss']
        symbol: str = "TARGET",
        position_size_pct: float = 0.90, # 預設單檔資金佔比 (可調為 0.15 模擬分散投資組合)
    ) -> BacktestSummary:
        """
        執行單標的回測：
        signal: 1 (買進/持倉), 0 (空手/平倉)
        stop_loss: 當日動態移動停損價
        """
        df = price_df.copy().reset_index(drop=True)
        cash = self.initial_capital
        shares = 0
        entry_price = 0.0
        entry_date = ""

        trades: List[TradeRecord] = []
        equity_curve: List[Dict[str, float]] = []

        for i in range(len(df)):
            row = df.iloc[i]
            cur_date = str(row["date"])
            close_px = float(row["close"])
            open_px = float(row.get("open", close_px))
            low_px = float(row["low"])
            sig = int(row.get("signal", 0))
            stop_px = float(row.get("stop_loss", 0.0))

            # 1. 檢查是否觸及停損或出場訊號 (防範隔夜跳空開低與滑價之過度理想化假設)
            if shares > 0:
                is_stopped = (low_px <= stop_px and stop_px > 0)
                is_signal_exit = (sig == 0)

                if is_stopped or is_signal_exit:
                    if is_stopped:
                        # 若隔夜跳空開低 (open_px < stop_px)，實盤只能以開盤價扣除滑價成交，不可理想化以 stop_px 成交
                        raw_exit_px = min(open_px, stop_px)
                    else:
                        raw_exit_px = close_px
                    exec_exit_px = raw_exit_px * (1.0 - self.slippage_rate)
                    revenue = shares * exec_exit_px
                    cost_exit = revenue * (self.transaction_fee_rate + self.transaction_tax_rate)
                    net_cash = revenue - cost_exit
                    cash += net_cash

                    ret_pct = ((exec_exit_px - entry_price) / entry_price) * 100.0
                    pnl = net_cash - (shares * entry_price)
                    reason = "STOP_LOSS_TRIGGERED" if is_stopped else "STRATEGY_EXIT_SIGNAL"

                    trades.append(
                        TradeRecord(
                            symbol=symbol,
                            entry_date=entry_date,
                            entry_price=entry_price,
                            exit_date=cur_date,
                            exit_price=round(exec_exit_px, 2),
                            shares=shares,
                            return_pct=round(ret_pct, 2),
                            pnl=round(pnl, 2),
                            exit_reason=reason,
                        )
                    )
                    shares = 0

            # 2. 檢查進場訊號 (尚未持倉且 signal == 1)
            if shares == 0 and sig == 1:
                # 依設定比例建倉 (例如 15% 投資組合部位)
                alloc_capital = (cash + shares * close_px) * position_size_pct
                fee_est = alloc_capital * self.transaction_fee_rate
                max_shares = int((alloc_capital - fee_est) / close_px)
                if max_shares > 0 and cash >= (max_shares * close_px):
                    trade_cost = max_shares * close_px
                    fee = trade_cost * self.transaction_fee_rate
                    cash -= (trade_cost + fee)
                    shares = max_shares
                    entry_price = close_px
                    entry_date = cur_date


            # 3. 記錄當日權益淨值
            current_portfolio_value = cash + (shares * close_px)
            equity_curve.append({
                "date": cur_date,
                "equity": round(current_portfolio_value, 2),
            })

        # 4. 指標計算
        final_equity = equity_curve[-1]["equity"] if equity_curve else self.initial_capital
        total_ret = ((final_equity - self.initial_capital) / self.initial_capital) * 100.0

        # 年化報酬率 (CAGR)
        total_days = max(len(df), 1)
        years = total_days / 252.0
        cagr = (((final_equity / self.initial_capital) ** (1.0 / max(years, 0.01))) - 1.0) * 100.0 if years > 0 else 0.0

        # 最大回撤 (MDD)
        eq_series = pd.Series([e["equity"] for e in equity_curve])
        peak_series = eq_series.cummax()
        drawdown = (eq_series - peak_series) / peak_series
        max_drawdown = float(drawdown.min() * 100.0) if len(drawdown) > 0 else 0.0

        # 夏普值 (Sharpe Ratio)
        daily_returns = eq_series.pct_change().dropna()
        if len(daily_returns) > 1 and daily_returns.std() > 0:
            excess_return = daily_returns.mean() - (self.risk_free_rate / 252.0)
            sharpe = float((excess_return / daily_returns.std()) * np.sqrt(252.0))
        else:
            sharpe = 0.0

        # 勝率與獲利因子
        winning_trades = [t for t in trades if t.pnl > 0]
        losing_trades = [t for t in trades if t.pnl <= 0]
        win_rate = (len(winning_trades) / len(trades) * 100.0) if trades else 0.0

        gross_profit = sum(t.pnl for t in winning_trades)
        gross_loss = abs(sum(t.pnl for t in losing_trades))
        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (99.0 if gross_profit > 0 else 0.0)

        return BacktestSummary(
            strategy_name=strategy_name,
            initial_capital=self.initial_capital,
            final_equity=round(final_equity, 2),
            total_return_pct=round(total_ret, 2),
            cagr=round(cagr, 2),
            max_drawdown_pct=round(abs(max_drawdown), 2),
            sharpe_ratio=round(sharpe, 3),
            win_rate_pct=round(win_rate, 2),
            profit_factor=round(profit_factor, 2),
            total_trades=len(trades),
            equity_curve=equity_curve,
            trade_history=trades,
        )
