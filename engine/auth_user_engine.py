"""
AlphaMind AI — Multi-User Authentication, Session Token & Isolated User Profile Engine.
- 強制所有人必須登入才能存取任何功能與 API。
- 不同使用者（User ID）的現金、持倉、自選股、智慧提醒與策略參數完全隔離。
- 全台股與全台灣 ETF 市場資料、即時報價快取（TaiwanMarketUniverseEngine）全站共用。
- 支援長效 Session Token + 瀏覽器 Credential Management 自動記憶帳號密碼，免重複輸入。
"""

import base64
import hashlib
import hmac
import json
import os
import secrets
import tempfile
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from alphamind.engine.portfolio_alert_engine import (
    PortfolioAndAlertEngine,
    PositionEntry,
    WatchlistEntry,
)


@dataclass
class UserAccount:
    user_id: str
    username: str
    display_name: str
    email: str
    password_salt: str
    password_hash: str
    role: str = "MEMBER"  # 'ADMIN', 'PRO_TRADER', 'MEMBER'
    created_at: str = ""
    last_login_at: str = ""
    strategy_prefs: Dict[str, Any] = field(
        default_factory=lambda: {
            "atr_period": 14,
            "atr_multiplier": 2.5,
            "base_position_pct": 15.0,
            "min_f_score": 6,
            "fee_discount": 0.60,
            "poll_interval_sec": 6,
        }
    )


class MultiUserAuthAndStoreEngine:
    """
    多使用者認證與隔離資料儲存引擎：
    1. 密碼雜湊驗證（PBKDF2-HMAC-SHA256）與長效 Session Token 管理。
    2. 每個 `user_id` 擁有獨立的 `PortfolioAndAlertEngine` 實例與獨立 JSON 儲存檔
       （`alphamind/user_data/portfolio_<user_id>.json`），同時具備 Supabase `alphamind_users` /
       `user_portfolios` / `user_positions` / `user_watchlists` 對應結構。
    3. 內建 2 組預設展示帳號（方便一鍵切換驗證「不同帳號資料完全隔離、但台股與 ETF 行情共用」），
       並支援即時註冊新帳號。
    """

    _TOKEN_SECRET = os.environ.get("ALPHAMIND_SESSION_SECRET", "alphamind-serverless-hmac-key-2026")

    def __init__(self, base_dir: Optional[Path] = None) -> None:
        default_dir = Path(__file__).resolve().parent.parent / "user_data"
        if base_dir is not None:
            self.base_dir = base_dir
        elif os.environ.get("VERCEL") or os.environ.get("AWS_LAMBDA_FUNCTION_NAME"):
            self.base_dir = Path(tempfile.gettempdir()) / "alphamind_user_data"
        else:
            self.base_dir = default_dir

        try:
            self.base_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            self.base_dir = Path(tempfile.gettempdir()) / "alphamind_user_data"
            self.base_dir.mkdir(parents=True, exist_ok=True)

        self.users_file = self.base_dir / "users_registry.json"
        self.sessions_file = self.base_dir / "active_sessions.json"

        self.users_by_id: Dict[str, UserAccount] = {}
        self.users_by_username: Dict[str, UserAccount] = {}
        self.sessions: Dict[str, str] = {}  # token -> user_id
        self.revoked_tokens: set[str] = set()
        self.portfolio_engines: Dict[str, PortfolioAndAlertEngine] = {}

        self._load_or_seed_users()
        self._load_sessions()

    # --------------------------------------------------------------------------
    # 密碼雜湊與驗證 (PBKDF2-HMAC-SHA256)
    # --------------------------------------------------------------------------
    @staticmethod
    def _hash_password(password: str, salt: str) -> str:
        dk = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt.encode("utf-8"),
            120_000,
        )
        return dk.hex()

    def _verify_password(self, user: UserAccount, password: str) -> bool:
        expected = self._hash_password(password, user.password_salt)
        return hmac.compare_digest(expected, user.password_hash)

    # --------------------------------------------------------------------------
    # 初始化與預設隔離帳號建立
    # --------------------------------------------------------------------------
    def _load_or_seed_users(self) -> None:
        if self.users_file.exists():
            try:
                raw = json.loads(self.users_file.read_text(encoding="utf-8"))
                for item in raw.get("users", []):
                    acc = UserAccount(**item)
                    self.users_by_id[acc.user_id] = acc
                    self.users_by_username[acc.username.lower()] = acc
                if self.users_by_id:
                    return
            except Exception:
                pass

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 預設帳號 1：主帳號 (波段與科技成長配置)
        salt1 = secrets.token_hex(16)
        u1 = UserAccount(
            user_id="usr_alpha_admin_01",
            username="tang921118",
            display_name="Tang (主力波段帳戶)",
            email="tangghgh@gmail.com",
            password_salt=salt1,
            password_hash=self._hash_password("alpha8888", salt1),
            role="ADMIN",
            created_at=now_str,
            last_login_at=now_str,
            strategy_prefs={
                "atr_period": 14,
                "atr_multiplier": 2.5,
                "base_position_pct": 15.0,
                "min_f_score": 6,
                "fee_discount": 0.60,
                "poll_interval_sec": 6,
            },
        )

        # 預設帳號 2：存股與高股息 ETF 示範帳號 (驗證不同使用者資料隔離)
        salt2 = secrets.token_hex(16)
        u2 = UserAccount(
            user_id="usr_dividend_vip_02",
            username="etf_income",
            display_name="陳先生 (高股息領息專戶)",
            email="dividend@alphamind.tw",
            password_salt=salt2,
            password_hash=self._hash_password("alpha8888", salt2),
            role="PRO_TRADER",
            created_at=now_str,
            last_login_at=now_str,
            strategy_prefs={
                "atr_period": 20,
                "atr_multiplier": 3.0,
                "base_position_pct": 20.0,
                "min_f_score": 7,
                "fee_discount": 0.28,
                "poll_interval_sec": 10,
            },
        )

        for acc in (u1, u2):
            self.users_by_id[acc.user_id] = acc
            self.users_by_username[acc.username.lower()] = acc

        self._save_users()
        self._seed_isolated_portfolios()

    def _seed_isolated_portfolios(self) -> None:
        """為兩個預設帳號建立截然不同的初始資產、持倉與自選股，直觀驗證多使用者資料隔離。"""
        # 帳號 1 (tang921118)：AI 半導體與權值波段部位
        p1_path = self.base_dir / "portfolio_usr_alpha_admin_01.json"
        if not p1_path.exists():
            eng1 = PortfolioAndAlertEngine(state_path=p1_path, auto_seed=True)
            eng1._save_state()

        # 帳號 2 (etf_income)：純 ETF 高股息與金融存股部位
        p2_path = self.base_dir / "portfolio_usr_dividend_vip_02.json"
        if not p2_path.exists():
            eng2 = PortfolioAndAlertEngine(state_path=p2_path, auto_seed=False)
            eng2.cash_twd = 850_000.0
            eng2.fee_discount = 0.28
            eng2.positions = [
                PositionEntry(
                    symbol="00878",
                    name="國泰永續高股息",
                    shares=50000,
                    avg_cost_price=21.10,
                    custom_target_price=24.5,
                    custom_stop_price=19.8,
                    last_recorded_pattern="均線多頭排列穩步推升",
                    notes="季配息核心底倉 50 張",
                ),
                PositionEntry(
                    symbol="00919",
                    name="群益台灣精選高息",
                    shares=30000,
                    avg_cost_price=23.20,
                    custom_target_price=26.5,
                    custom_stop_price=21.8,
                    last_recorded_pattern="區間箱型量縮整理",
                    notes="高殖利率雙核心 30 張",
                ),
                PositionEntry(
                    symbol="2881",
                    name="富邦金",
                    shares=10000,
                    avg_cost_price=84.50,
                    custom_target_price=98.0,
                    custom_stop_price=79.0,
                    last_recorded_pattern="均線多頭排列穩步推升",
                    notes="金融控配息部位",
                ),
            ]
            eng2.watchlist = [
                WatchlistEntry(symbol="0056", name="元大高股息", target_buy_price=37.5, added_at="2026-11-01"),
                WatchlistEntry(symbol="00713", name="元大台灣高息低波", target_buy_price=54.0, added_at="2026-11-02"),
                WatchlistEntry(symbol="2891", name="中信金", target_buy_price=35.8, added_at="2026-11-03"),
            ]
            eng2._save_state()

    def _save_users(self) -> None:
        try:
            payload = {"users": [u.__dict__ for u in self.users_by_id.values()]}
            self.users_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

    def _load_sessions(self) -> None:
        if self.sessions_file.exists():
            try:
                raw = json.loads(self.sessions_file.read_text(encoding="utf-8"))
                self.sessions = {
                    str(k): str(v)
                    for k, v in raw.get("sessions", {}).items()
                    if str(v) in self.users_by_id
                }
            except Exception:
                self.sessions = {}

    def _save_sessions(self) -> None:
        try:
            self.sessions_file.write_text(
                json.dumps({"sessions": self.sessions}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception:
            pass

    # --------------------------------------------------------------------------
    # 認證 API：註冊、登入、Token 驗證、登出、偏好設定儲存
    # --------------------------------------------------------------------------
    def register_user(
        self,
        username: str,
        password: str,
        display_name: str = "",
        email: str = "",
        initial_cash_twd: float = 1_000_000.0,
    ) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        uname = username.strip()
        if len(uname) < 3:
            return False, "帳號長度至少需 3 個字元", None
        if len(password) < 4:
            return False, "密碼長度至少需 4 個字元", None
        if uname.lower() in self.users_by_username:
            return False, f"帳號「{uname}」已被註冊，請直接登入或換一個帳號", None

        uid = f"usr_{uuid.uuid4().hex[:12]}"
        salt = secrets.token_hex(16)
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        acc = UserAccount(
            user_id=uid,
            username=uname,
            display_name=display_name.strip() or uname,
            email=email.strip() or f"{uname}@alphamind.tw",
            password_salt=salt,
            password_hash=self._hash_password(password, salt),
            role="MEMBER",
            created_at=now_str,
            last_login_at=now_str,
        )
        self.users_by_id[uid] = acc
        self.users_by_username[uname.lower()] = acc
        self._save_users()

        # 初始化該新使用者的專屬空白（含基礎自選股）資產池
        user_p_path = self.base_dir / f"portfolio_{uid}.json"
        eng = PortfolioAndAlertEngine(state_path=user_p_path, auto_seed=False)
        eng.cash_twd = float(initial_cash_twd)
        eng.fee_discount = 0.60
        eng.positions = []
        eng.watchlist = [
            WatchlistEntry(symbol="2330", name="台積電", target_buy_price=1025.0, added_at=now_str[:10]),
            WatchlistEntry(symbol="0050", name="元大台灣50", target_buy_price=189.0, added_at=now_str[:10]),
        ]
        eng._save_state()
        self.portfolio_engines[uid] = eng

        token = self._issue_session_token(uid)
        return True, "註冊並登入成功", self._format_auth_response(acc, token)

    def login_user(self, username_or_email: str, password: str) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        key = username_or_email.strip().lower()
        user = self.users_by_username.get(key)
        if not user:
            # 支援以 Email 登入
            user = next((u for u in self.users_by_id.values() if u.email.lower() == key), None)

        if not user or not self._verify_password(user, password):
            return False, "帳號或密碼錯誤，請重新確認", None

        user.last_login_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._save_users()
        token = self._issue_session_token(user.user_id)
        return True, "登入成功", self._format_auth_response(user, token)

    def _issue_session_token(self, user_id: str) -> str:
        user = self.users_by_id.get(user_id)
        claims = {
            "uid": user_id,
            "u": user.username if user else user_id,
            "dn": user.display_name if user else user_id,
            "em": user.email if user else "",
            "r": user.role if user else "MEMBER",
            "n": secrets.token_hex(8),
        }
        b64 = base64.urlsafe_b64encode(json.dumps(claims, separators=(",", ":")).encode("utf-8")).decode("ascii").rstrip("=")
        sig = hmac.new(self._TOKEN_SECRET.encode("utf-8"), b64.encode("ascii"), hashlib.sha256).hexdigest()[:32]
        token = f"am_tok.{b64}.{sig}"
        self.sessions[token] = user_id
        self._save_sessions()
        return token

    def verify_session_token(self, token: Optional[str]) -> Optional[UserAccount]:
        if not token:
            return None
        clean_tok = token.replace("Bearer ", "").strip()
        if clean_tok in self.revoked_tokens:
            return None
        uid = self.sessions.get(clean_tok)
        if uid and uid in self.users_by_id:
            return self.users_by_id[uid]

        # Stateless HMAC token verification fallback for Serverless (Vercel / AWS Lambda)
        if clean_tok.startswith("am_tok."):
            parts = clean_tok.split(".")
            if len(parts) == 3:
                _, b64, sig = parts
                expected_sig = hmac.new(self._TOKEN_SECRET.encode("utf-8"), b64.encode("ascii"), hashlib.sha256).hexdigest()[:32]
                if hmac.compare_digest(sig, expected_sig):
                    try:
                        pad = "=" * (-len(b64) % 4)
                        claims = json.loads(base64.urlsafe_b64decode(b64 + pad).decode("utf-8"))
                        c_uid = str(claims.get("uid", ""))
                        if c_uid in self.users_by_id:
                            self.sessions[clean_tok] = c_uid
                            return self.users_by_id[c_uid]
                        # Reconstruct dynamically registered user across serverless cold start
                        acc = UserAccount(
                            user_id=c_uid,
                            username=str(claims.get("u", c_uid)),
                            display_name=str(claims.get("dn", c_uid)),
                            email=str(claims.get("em", "")),
                            password_salt="",
                            password_hash="",
                            role=str(claims.get("r", "MEMBER")),
                        )
                        self.users_by_id[c_uid] = acc
                        self.users_by_username[acc.username.lower()] = acc
                        self.sessions[clean_tok] = c_uid
                        return acc
                    except Exception:
                        return None
        return None

    def logout_token(self, token: Optional[str]) -> None:
        if not token:
            return
        clean_tok = token.replace("Bearer ", "").strip()
        self.revoked_tokens.add(clean_tok)
        if clean_tok in self.sessions:
            del self.sessions[clean_tok]
            self._save_sessions()

    def get_user_portfolio_engine(self, user_id: str) -> PortfolioAndAlertEngine:
        """取得該使用者專屬隔離的 PortfolioAndAlertEngine 實例"""
        if user_id not in self.portfolio_engines:
            p_path = self.base_dir / f"portfolio_{user_id}.json"
            is_default_admin = user_id == "usr_alpha_admin_01"
            self.portfolio_engines[user_id] = PortfolioAndAlertEngine(
                state_path=p_path,
                auto_seed=is_default_admin and not p_path.exists(),
            )
        return self.portfolio_engines[user_id]

    def update_user_strategy_prefs(self, user_id: str, prefs: Dict[str, Any]) -> Dict[str, Any]:
        user = self.users_by_id.get(user_id)
        if not user:
            return {}
        for k in ("atr_period", "atr_multiplier", "base_position_pct", "min_f_score", "fee_discount", "poll_interval_sec"):
            if k in prefs and prefs[k] is not None:
                user.strategy_prefs[k] = prefs[k]
        self._save_users()
        return user.strategy_prefs

    def list_demo_accounts_public(self) -> List[Dict[str, str]]:
        """提供登入頁快速填入測試之展示帳號摘要"""
        return [
            {
                "username": "tang921118",
                "display_name": "Tang (主力波段帳戶)",
                "desc": "AI 半導體波段持倉（台積電、鴻海、世芯-KY）",
            },
            {
                "username": "etf_income",
                "display_name": "陳先生 (高股息領息專戶)",
                "desc": "純高股息 ETF 與金融存股（00878、00919、富邦金）",
            },
        ]

    @staticmethod
    def _format_auth_response(user: UserAccount, token: str) -> Dict[str, Any]:
        return {
            "token": token,
            "user": {
                "user_id": user.user_id,
                "username": user.username,
                "display_name": user.display_name,
                "email": user.email,
                "role": user.role,
                "last_login_at": user.last_login_at,
                "strategy_prefs": user.strategy_prefs,
            },
        }
