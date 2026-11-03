"""
AlphaMind AI — Fugle (富果) API Adapter
Handles authentication, market data streaming, and trade SDK configuration.
"""

import os
from configparser import ConfigParser
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Optional
import urllib.request
import json

from alphamind.engine.sector_flow_engine import TickData


@dataclass
class FugleCredentials:
    api_key: str
    api_secret: str
    config_path: Optional[str] = None


def load_fugle_credentials(env_path: Optional[str] = None, config_path: Optional[str] = None) -> FugleCredentials:
    """從環境變數、.env 或 config.ini 載入富果金鑰憑證（自動搜尋候選路徑）"""
    api_key = os.getenv("FUGLE_API_KEY", "")
    api_secret = os.getenv("FUGLE_API_SECRET", "")

    # 搜尋候選 .env 路徑
    base_dir = os.path.dirname(os.path.abspath(__file__))
    candidate_envs = [
        env_path,
        os.path.join(base_dir, "../.env"),
        ".env",
        os.path.join(base_dir, "../../.env"),
    ]

    for p in candidate_envs:
        if (api_key and api_secret) or not p or not os.path.exists(p):
            continue
        with open(p, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip().strip("'\"")
                if k == "FUGLE_API_KEY" and not api_key:
                    api_key = v
                elif k == "FUGLE_API_SECRET" and not api_secret:
                    api_secret = v

    # 搜尋候選 config.ini 路徑
    candidate_configs = [
        config_path,
        os.path.join(base_dir, "../config.ini"),
        "config.ini",
        os.path.join(base_dir, "../../config.ini"),
    ]

    resolved_config_path = None
    for cp_path in candidate_configs:
        if not cp_path or not os.path.exists(cp_path):
            continue
        resolved_config_path = cp_path
        if not api_key or not api_secret:
            cp = ConfigParser()
            cp.read(cp_path, encoding="utf-8")
            if cp.has_section("Api"):
                api_key = api_key or cp.get("Api", "Key", fallback="")
                api_secret = api_secret or cp.get("Api", "Secret", fallback="")
        if api_key and api_secret:
            break

    return FugleCredentials(
        api_key=api_key,
        api_secret=api_secret,
        config_path=resolved_config_path,
    )



class FugleMarketDataClient:
    """富果行情 REST / WebSocket 客戶端封裝"""

    BASE_URL = "https://api.fugle.tw/marketdata/v1.0/stock"

    def __init__(self, credentials: Optional[FugleCredentials] = None) -> None:
        self.creds = credentials or load_fugle_credentials()
        if not self.creds.api_key:
            raise ValueError("Fugle API Key is missing. Please set FUGLE_API_KEY in .env or config.ini.")

    def _get_headers(self) -> Dict[str, str]:
        key = os.getenv("FUGLE_BASE64_TOKEN") or self.creds.api_key
        return {
            "X-API-KEY": key,
            "User-Agent": "AlphaMind-Engine/1.0",
        }

    def fetch_intraday_quote(self, symbol: str) -> Dict[str, Any]:
        """抓取盤中即時報價"""
        clean_symbol = symbol.replace(".TW", "").replace(".TWO", "")
        url = f"{self.BASE_URL}/intraday/quote/{clean_symbol}"
        req = urllib.request.Request(url, headers=self._get_headers())
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"Fugle API request failed [{e.code}]: {err_body}")

    def parse_to_tick(self, symbol: str, quote_payload: Dict[str, Any]) -> TickData:
        """將富果盤中 Quote 轉換為 AlphaMind 統一的 TickData 格式"""
        close_px = float(quote_payload.get("closePrice", quote_payload.get("lastPrice", 0.0)))
        total_vol = int(quote_payload.get("total", {}).get("unit", 0))
        total_turnover = float(quote_payload.get("total", {}).get("turnover", 0.0))

        # 判定外盤或內盤 (以成交價相對於最新買賣價判斷)
        bids = quote_payload.get("bids", [])
        asks = quote_payload.get("asks", [])
        bid_ask_flag = 0
        if asks and close_px >= asks[0].get("price", 0.0):
            bid_ask_flag = 1
        elif bids and close_px <= bids[0].get("price", 0.0):
            bid_ask_flag = -1

        return TickData(
            symbol=symbol,
            price=close_px,
            volume=total_vol,
            turnover=total_turnover,
            bid_ask_flag=bid_ask_flag,
            timestamp=datetime.now(),
            is_large_order=(total_turnover >= 5_000_000.0),
        )
