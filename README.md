# AlphaMind AI — 智慧選股與供應鏈資金動能分析平台

全端量化架構，整合即時報價、供應鏈傳導圖譜、財報河流圖、雙軌停利停損、四維狀態機決策與 AI 首席投資長中性研判。

---

## 一、 目錄架構

```
alphamind/
├── .env / .env.example          # 富果 API 憑證 (金鑰自動隔離保護)
├── config.ini / config.example.ini # 富果交易 SDK 設定檔
├── requirements.txt             # Python 依賴清單
├── run.py                       # 一鍵啟動入口腳本
├── schema/                      # 資料庫 DDL 與領域型別
│   ├── supabase_alphamind_schema.sql  # ★ Supabase 專用（原生分區 + 遞迴 CTE 圖譜 + pgvector）
│   ├── postgres_timescaledb_schema.sql # 傳統 TimescaleDB 備用架構
│   ├── neo4j_cypher_schema.cql        # Neo4j Cypher 備用圖譜
│   ├── redis_data_structures.md       # Redis 快取與 Stream 規範
│   └── domain_types.ts                # 全端 TypeScript 嚴格領域型別
├── engine/                      # 核心量化演算法引擎
│   ├── sector_flow_engine.py    # 即時資金板塊流向比 (Flow Ratio)
│   ├── risk_engine.py           # ATR 移動停損與雙軌停利停損模型
│   ├── supply_chain_engine.py   # 供應鏈落後補漲套利
│   ├── macro_engine.py          # 6 國跨市場總經、日圓平倉與風控乘數
│   ├── valuation_engine.py      # Piotroski F-Score、Altman Z、PE/PB 河流圖、DCF
│   ├── decision_synthesizer.py  # 四維階層式決策狀態機 (核心樞紐)
│   ├── backtest_engine.py       # 向量化與事件驅動回測器
│   ├── overfitting_guard.py     # 過擬合防禦、Point-in-Time 稽核與 DSR
│   └── fugle_adapter.py         # 富果行情介接適配器
├── ai/                          # 結構化 AI 代理模組
│   ├── schemas.py               # Pydantic 結構化 JSON Schemas
│   ├── structured_extractor.py  # 年報圖譜邊與新聞特徵抽取
│   ├── devils_advocate.py       # AI 魔鬼代言人 (做多前強制逆向抗辯)
│   └── neutral_synthesizer.py   # AI 首席投資長中性綜合研判
├── ingestion/                   # 資料收集排程模組
│   ├── finmind_collector.py     # FinMind 台股時序收集
│   └── macro_collector.py       # 全球 6 國總經快照收集
├── tests/                       # 測試與驗證套件
│   ├── test_full_pipeline.py    # 端到端全管線整合測試 (8大步驟)
│   └── test_trading_viability.py # 四大極端行情實盤可行性壓力測試
└── web/                         # 前端 UI 與 API 服務
    ├── index.html               # 極簡 Toss 風格戰情室單頁應用
    ├── server.py                # Python 本地 HTTP/JSON API 伺服器
    └── vercel.json              # Vercel 一鍵部署路由設定檔
```

---

## 二、 快速開始

### 1. 安裝環境依賴
```bash
pip install -r requirements.txt
```

### 2. 啟動本機決策戰情室
```bash
python run.py
```
瀏覽器開啟 [http://localhost:8888](http://localhost:8888) 即可即時互動操作。

---

## 三、 雲端整合指南

### 1. Supabase 資料庫建置
1. 登入 [Supabase Dashboard](https://supabase.com/) 建立專案。
2. 開啟專案左側 **SQL Editor**。
3. 複製貼上 [schema/supabase_alphamind_schema.sql](schema/supabase_alphamind_schema.sql) 的全部內容並點擊 **Run**。
4. 完成：已自動建立原生時序分區、`get_supply_chain_network` 遞迴圖譜遍歷函數、`pgvector` 支援及初始種子資料。

### 2. Vercel 前端一鍵部署
1. 將專案推至 GitHub Repository。
2. 登入 [Vercel](https://vercel.com/) 點擊 **Add New Project**。
3. **Root Directory** 設定填入：`alphamind/web`。
4. 點擊 **Deploy**，30 秒內即可獲得線上正式公開網址。

---

## 四、 執行全模組驗證

```bash
# 1. 執行核心演算法單元驗證
PYTHONPATH=. python3 engine/test_engines.py

# 2. 執行全管線端到端整合測試 (含過擬合防禦與 AI 中性研判)
PYTHONPATH=. python3 tests/test_full_pipeline.py

# 3. 執行四大盤勢實盤可行性壓力測試 (多頭/震盪/黑天鵝/地雷)
PYTHONPATH=. python3 tests/test_trading_viability.py
```
