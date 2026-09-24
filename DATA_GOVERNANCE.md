# Information Security & Privacy Information Governance Framework
# 資訊安全與個人資料歷史法證保護管理規範
*(Aligned with ISO/IEC 27001:2022 and ISO/IEC 27701:2019 Controls)*

---

## 1. Information Security Architecture (ISO/IEC 27001 Controls)
## 1. 資訊安全控制架構（對標 ISO/IEC 27001 標準）

### English
* **A.8.7 Protection Against Malware & Ingestion Isolation:**  
  All 74 sovereign adapter pipelines execute within isolated Python execution sandboxes. Ingestion failures (such as HTTP 403, 502, or SSL failures) are strictly isolated with exponential backoff and error boundaries to prevent denial-of-service or pipeline cascade failures.
* **A.8.9 Configuration Management & Deterministic Builds:**  
  The system utilizes immutable, auditable schema structures (`schemas/record.schema.json` v2.0.0). No pipeline execution may bypass JSON schema validation.
* **A.8.12 Data Leakage Prevention:**  
  The repository is strictly an open-metadata and public-registry platform. Secret keys, cloud credentials, and sensitive private tokens are strictly forbidden; automated builds utilize ephemeral, Keyless OpenID Connect (OIDC) identities via GitHub Actions and Sigstore/Fulcio.
* **A.8.24 Use of Cryptography & Non-Repudiation:**  
  Every release cycle produces an SHA-256 digest of `records-latest.json`. Keyless identity bundles (`records-latest.json.bundle`) are permanently logged into the Rekor transparency ledger, guaranteeing mathematical non-repudiation.

### 中文
* **A.8.7 惡意程式防範與採集沙盒隔離：**  
  全域 74 個主權檔案適配器均於獨立 Python 沙盒環境中執行。任何單一端點之連線異常（如 HTTP 403、502、SSL 憑證失效）均由防禦性斷路邊界攔截，絕不引發系統級級聯崩潰或阻斷服務。
* **A.8.9 配置管理與確定性建置：**  
  全面採用不可篡改之標準規範（`schemas/record.schema.json` v2.0.0），所有採集資料必須通過嚴格的結構化 Schema 驗證方可入帳。
* **A.8.12 資料外洩防護與零金鑰憑證（Zero-Key Identity）：**  
  平台嚴格限定處理公開目錄與開放元數據。系統絕對禁止在伺服器端存放靜態私鑰或長期金鑰；自動化發佈採用 GitHub Actions 搭配 Sigstore/Fulcio 發行之短暫性 OIDC 身分憑證，消除金鑰遭竊或外洩風險。
* **A.8.24 密碼學控制與不可抵賴性：**  
  每個發佈週期皆對 `records-latest.json` 計算 SHA-256 雜湊，並透過 Keyless 憑證束（`records-latest.json.bundle`）將存證資料永久寫入 Linux 基金會託管之 Rekor 公共透明登記簿，達成密碼學不可抵賴性。

---

## 2. Privacy Information Management (ISO/IEC 27701 & PIMS)
## 2. 隱私資訊管理規範（對標 ISO/IEC 27701 標準）

### English
* **Clause 6.3.2.1 Collection Limitation & Minimization:**  
  "The Veracity" indexes only statutory public metadata (Document Title, Call Number, Creating Government Agency, Fonds, Series, and Year of Declassification). The platform actively refrains from collecting personal contact information, residential addresses, financial accounts, biometric data, or contemporary living private data.
* **Clause 6.3.2.2 Deceased Individuals & Historical Archival Exemption:**  
  In compliance with international data privacy doctrines (GDPR, HK PDPO, PIPL), records are governed by the **30-Year Statutory Declassification Rule**. Primary records pertain to public governance acts from 1945 to 1996. Any historical personalities cited in diplomatic correspondence are treated under statutory archival research exemptions.
* **Clause 6.5.3 Data Rectification & Erasure Requests (Triage Policy):**  
  Because "The Veracity" acts as an immutable cryptographic index of external sovereign archives (and does not author or maintain the physical original paper archives), any demand to expunge or redact an archival record must be submitted directly to the originating national repository (e.g., UK TNA, US NARA, UN Archives). Upon receipt of an official notification of sovereign court-ordered redaction, "The Veracity" maintainers will annotate the ledger entry according to Archival Description Standards (ISAD(G) / RiC-O).

### 中文
* **條款 6.3.2.1 採集限制與最小化原則：**  
  「揭古」僅索引法定公開目錄之客觀全宗元數據（公文題名、檔號、創作者機關、全宗名、系列名及解密年份）。系統主動排除收集個人聯絡方式、居住地址、金融帳號、生物特徵等當代個人敏感隱私數據。
* **條款 6.3.2.2 已故人士與歷史檔案法定豁免：**  
  遵循國際個人資料保護原則，本總帳以 **30 年法定解密規則**（1945 年至 1996 年）為嚴格邊界。公文中出現之人名皆為戰後與冷戰時期公務履職之歷史公眾人物或已故歷史人士，依法受公共檔案學學術研究原則保護。
* **條款 6.5.3 異議、更正與刪除請求分流政策（Triage Policy）：**  
  「揭古」作為外部主權檔案館之數位存證與索引平台，本身並非檔案的原始產製者或實體所有人。任何主張公文記載失實或要求封卷之請求，依法應向原管轄主權國家檔案局（如英國 TNA、美國 NARA、聯合國秘書處）提出。若原權責機構發佈正式司法撤銷裁定或官方勘誤公報，本平台將依國際檔案描述標準（ISAD(G) / RiC-O）於總帳中更新法證附註，確保歷史記錄之客觀追蹤。

---

## 3. Statistical Anomaly & Circuit Breaker Guard
## 3. 滑動統計斷路器防護機制（防篡改與完整性監控）

```text
┌─────────────────────────────────────────────────────────────┐
│             STATISTICAL CIRCUIT BREAKER (±2.5σ)             │
│                                                             │
│   Ingestion Run ──> Calculate Net Mutations (ΔM)            │
│                            │                                │
│                            ▼                                │
│               Rolling Mean (μ) & StDev (σ)                  │
│                            │                                │
│         ┌──────────────────┴──────────────────┐             │
│         ▼                                     ▼             │
│   ΔM <= μ + 2.5σ                       ΔM > μ + 2.5σ        │
│   (Normal Operation)                   (Anomalous Surge)    │
│         │                                     │             │
│         ▼                                     ▼             │
│   Commit to Ledger                   HALT Pipeline & Alert  │
│   Sign with Sigstore                 Write Warning Snapshot │
└─────────────────────────────────────────────────────────────┘
