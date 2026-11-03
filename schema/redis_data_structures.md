# AlphaMind AI — Polyglot Persistence Architecture
## Layer 3: Redis 7 In-Memory Hot Data & Stream Topologies

為確保盤中 Tick 與五檔報價延遲低於 1ms，並支援即時資金流向計算與前端 WebSocket 推播，設計以下 Redis 鍵值與資料結構規範：

---

### 1. 個股盤中即時快照 (Hash)
* **Key Pattern**: `quote:live:{symbol}` (例如 `quote:live:2330.TW`)
* **TTL**: 當日收盤後 16:30 清理或歸檔 (TTL: 86400 秒)
* **Fields**:
  - `p`: 最新成交價 (`NUMERIC(14, 4)`)
  - `chg`: 漲跌金額
  - `pct`: 漲跌幅 (%)
  - `v`: 當日累計成交量 (股)
  - `tv`: 當日累計成交額 (TWD)
  - `vwap`: 當日量加權均價
  - `b1` ~ `b5`: 買一至買五報價
  - `bv1` ~ `bv5`: 買一至買五掛單量
  - `a1` ~ `a5`: 賣一至賣五報價
  - `av1` ~ `av5`: 賣一至賣五掛單量
  - `buy_v`: 外盤主動買進累積量
  - `sell_v`: 內盤主動賣出累積量
  - `net_large_inflow`: 大戶淨流入金額 (單筆 > 500 萬累計)
  - `ts`: Unix Timestamp (毫秒)

---

### 2. 資金板塊熱度排行榜 (Sorted Set - ZSET)
* **Key Patterns**:
  - `rank:sector:flow_ratio:5m`: 過去 5 分鐘資金流向比排行榜（Score = `flow_ratio`，Member = `sector_id`）
  - `rank:sector:flow_ratio:15m`: 過去 15 分鐘資金流向比排行榜
  - `rank:sector:turnover_ratio`: 當前族群成交額佔大盤比例排行榜（Score = `turnover_ratio`）
  - `rank:sector:large_inflow`: 族群大戶資金淨流入排行榜（Score = `net_large_inflow`）
* **常用操作**:
  - 快速取得前 5 大資金流入族群：`ZREVRANGE rank:sector:flow_ratio:5m 0 4 WITHSCORES`

---

### 3. 多標籤族群成員關聯 (Set)
* **族群成員集合**:
  - Key: `sector:members:{sector_id}` (例如 `sector:members:CoWoS`)
  - Members: `['2330.TW', '3131.TW', '3583.TW', ...]`
* **個股所屬族群集合**:
  - Key: `stock:sectors:{symbol}` (例如 `stock:sectors:2330.TW`)
  - Members: `['Foundry', 'CoWoS', 'AI_Chip']`

---

### 4. 異常資金異動與事件串流 (Redis Stream & Pub/Sub)
* **持久化事件佇列 (Redis Stream)**:
  - Key: `stream:market:anomalies`
  - 使用 `XADD stream:market:anomalies * type "SECTOR_SPIKE" sector "CoWoS" flow_ratio 2.85 trigger_stock "3131.TW"`
  - 供盤後檢索與消費者組（Consumer Groups）保證至少交付一次。
* **即時推播頻道 (Pub/Sub)**:
  - Channel: `channel:live:alerts` (給前端 WebSocket Gateway 監聽並廣播)
  - Channel: `channel:quotes:{symbol}` (針對前端用戶開啟之個股訂閱視窗)
