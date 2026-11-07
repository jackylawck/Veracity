# Epistemological Boundary & Evidence Framework | 四層認識論邊界憲章

### English
The Veracity strictly separates historical verification into four independent layers. Cross-layer causal inference is formally prohibited:

| Layer | Question | Responsible Agent | System Boundary |
|---|---|---|---|
| **Layer 4: Interpretation** | What was the political intent? How should this historical event be assessed? | Human Historians & Scholarly Community | **Deterministic algorithms and LLMs are strictly prohibited from historical adjudication** |
| **Layer 3: Authenticity & Series Context** | Are archival series contiguous? Are custodial gaps or sequence lacunae indicated? | Archival Principle of Provenance (Respect des Fonds) | System outputs **heuristic clues and inspection flags only** (Single-record pass cannot infer fonds-level gaps; no cryptographic finality) |
| **Layer 2: Provenance & Digital Custody** | Which sovereign repository holds the record? What are its covering dates and digital custody trail? | Custodial Chain & Ingestion Provenance (PREMIS / OAIS) | Ingests official catalog metadata and logs retrieval timestamps. **Explicitly distinguishes historical covering dates from physical declassification release timestamps** |
| **Layer 1: Fixity & Ledger Integrity** | Has the ingested payload or structured ledger mutated since retrieval? | Cryptographic Hash (SHA-256) & Transparency Logs (Sigstore) | **Core Deterministic Engineering Guarantee** (Payload bitstream validation; explicitly records `NONE` under `metadata_only` tier) |

> **Cardinal Principle**: Veracity is not a binary verdict computed by algorithms, but an immutable audit trail designed to anchor human scholars in exercising their own historical judgment.

---

### 繁體中文
本專案將歷史數位資料之驗證嚴格劃分為四個獨立層次，嚴禁跨層進行因果推論：

| 層級 | 核心提問 | 負責主體 | 系統能力邊界 |
|---|---|---|---|
| **Layer 4: 歷史解釋 (Interpretation)** | 公文政治意圖為何？歷史因果應如何評價？ | 人類歷史學家與學術社群 | **確定性代碼與語言模型絕對禁止介入進行歷史裁判** |
| **Layer 3: 全宗脈絡 (Authenticity & Context)** | 系列卷宗是否連貫？全宗結構是否存在斷層或缺號待查標註？ | 檔案學全宗原則 (Respect des Fonds) 與文獻考據學 | **僅提供啟發式探索線索與待查標籤**（單卷目錄無法自動推導全域斷層，絕不具備密碼學存證效力） |
| **Layer 2: 來源與託管 (Provenance)** | 公文由何主權檔案館典藏？其歷史涵蓋期與數位擷取鏈為何？ | 檔案館託管鏈與 PREMIS 擷取存證事件 | 如實結構化官方詮釋資料並記錄擷取時間戳。**嚴格分離檔案內容形成涵蓋年限（Covering Dates）與官方實體解密開放日（Release Date）** |
| **Layer 1: 位元完整性 (Fixity)** | 數位檔案或結構化總帳紀錄自取出後是否曾遭未授權篡改？ | 密碼學雜湊（SHA-256）與透明總帳（Sigstore） | **核心確定性工程保障**（驗證位元流完整性；在僅擷取元資料階段顯式宣告 `metadata_only` 與 `NONE` 邊界） |

> **核心原則**：Veracity（揭古求真）不是演算法輸出的二元判決，而是本系統協助人類學者抵達獨立歷史判斷時所依託的不可篡改審計鏈。

---

## 關鍵實作邊界規範 (Implementation Boundaries)

### 1. 時間窗口過濾之認識論界定 (Temporal Filter Semantic)
* **涵蓋年限（Covering Dates）≠ 官方解密日期（Release Date）**：
  本系統適配器（例如 `UK_TNA`）帶入之檢索條件（如 `sps.startDate` 與 `sps.endDate`），過濾的是檔案本身記錄內容與形成的歷史年限（`coveringDates`），而非檔案館實體將公文對公眾開放的解密日期。
* **維護者工程設計裁決（Maintainer Design Choice）**：
  系統使用動態計算之 `current_year - 30` 作為預設涵蓋年限截止線，**此為專案維護者的工程設計選擇，旨在篩選已高度沉澱之冷戰涉外卷宗，非任何國家現行法定解密規範**。總帳記錄於 `provenance.temporal_filter_semantic` 顯式標記 `covering_dates_not_release_date` 以示負責。

### 2. 認識論誠實與零逃生門原則 (Zero-Fallback & Epistemic Honesty)
* **空總帳為合法初始狀態（Valid `UNINITIALIZED` State）**：
  在適配器尚未取得任何真實公文前，總帳保留 0 筆記錄，狀態為未初始化。嚴禁以任何測試 Mock 或合成種子資料（Synthetic Seeds）充作法證數據。
* **主權端點真實規模（True Sovereign Scale）**：
  系統當前具備 **1 個生產中活躍採集管線（UK TNA）** 與 **73 個探索種子（Roadmap Seeds / Scaffolding Stubs）**。全庫文檔杜絕「74 個上線主權節點」之誇大修辭。
* **單遍掃描啟發邊界（Single-Pass Heuristic Limitation）**：
  啟發式引擎（`scripts/heuristics.py`）在處理單筆獨立目錄紀錄時，標記為 `UNCOMPUTED_IN_SINGLE_PASS`，坦承單卷視野無法推導全宗整體斷層，杜絕偽造全域法證結論。
