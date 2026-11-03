"""
AlphaMind AI — FinMind Data Collector
Pulls Taiwan stock OHLCV, institutional trading, margin balance, and financial statements.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
import json
from typing import Any, Dict, List, Optional
import urllib.request
import urllib.parse
import pandas as pd


@dataclass
class FinMindConfig:
    token: Optional[str] = None
    timeout: int = 15


class FinMindCollector:
    """FinMind 資料收集器與時序轉換器"""

    BASE_URL = "https://api.finmindtrade.com/api/v4/data"

    def __init__(self, config: Optional[FinMindConfig] = None) -> None:
        self.config = config or FinMindConfig()

    def fetch_dataset(
        self,
        dataset: str,
        data_id: str,
        start_date: str,
        end_date: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        params = {
            "dataset": dataset,
            "data_id": data_id,
            "start_date": start_date,
        }
        if end_date:
            params["end_date"] = end_date
        if self.config.token:
            params["token"] = self.config.token

        query_str = urllib.parse.urlencode(params)
        url = f"{self.BASE_URL}?{query_str}"
        req = urllib.request.Request(url, headers={"User-Agent": "AlphaMind-Ingestion/1.0"})

        try:
            with urllib.request.urlopen(req, timeout=self.config.timeout) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                return result.get("data", [])
        except Exception as e:
            # 離線或網路中斷時拋出例外或回退
            raise RuntimeError(f"FinMind fetch failed for {dataset} ({data_id}): {e}")

    @staticmethod
    def generate_synthetic_taiwan_stock_history(
        symbol: str = "2330.TW",
        days: int = 60,
    ) -> pd.DataFrame:
        """離線與測試用的標準化台股合成資料產生器"""
        dates = pd.date_range(end=datetime.now(), periods=days, freq="B")
        base_price = 1000.0 if "2330" in symbol else 500.0

        records = []
        for i, dt in enumerate(dates):
            change = (hash(f"{symbol}-{i}") % 30) - 13.0
            base_price = max(10.0, base_price + change)
            high = base_price + abs(change) * 0.8 + 5.0
            low = base_price - abs(change) * 0.8 - 4.0
            close_px = base_price + change * 0.5
            vol = 15_000_000 + (hash(f"vol-{i}") % 10_000_000)

            records.append({
                "date": dt.strftime("%Y-%m-%d"),
                "symbol": symbol,
                "open": round(base_price, 2),
                "high": round(high, 2),
                "low": round(low, 2),
                "close": round(close_px, 2),
                "volume": int(vol),
                "foreign_buy_net": int((hash(f"f-{i}") % 5000 - 2000) * 1000),
                "investment_trust_buy_net": int((hash(f"it-{i}") % 2000 - 500) * 1000),
                "margin_balance": int(50000 + (hash(f"m-{i}") % 5000)),
            })

        return pd.DataFrame(records)
