# ⚖️ The Veracity | 揭古
### Sovereign Declassification Pipeline & Cryptographic Historical Forensics Ledger
### 全球主權解密管線與歷史數位法證總帳

[![CI Pipeline & Provenance Audit](https://github.com/jackylawck/Veracity/actions/workflows/ingest.yml/badge.svg)](https://github.com/jackylawck/Veracity/actions)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Sigstore: Keyless Anchored](https://img.shields.io/badge/Sigstore-Keyless_Anchored-brightgreen.svg)](https://sigstore.dev/)
[![Nodes: 74 Sovereign Authorities](https://img.shields.io/badge/Nodes-74_Sovereign_Authorities-blueviolet.svg)](#sovereign-matrix)
[![Deterministic Engine: Non--AI Scope](https://img.shields.io/badge/Deterministic-Non--AI_Scope-informational.svg)](COMPLIANCE.md)
[![Security: ISO 27001 / 27701 Aligned](https://img.shields.io/badge/Governance-ISO_27001_%2F_27701-orange.svg)](DATA_GOVERNANCE.md)

[**🌐 Live Forensic Web Console / 線上法證總帳檢驗終端**](https://jackylawck.github.io/Veracity/)

</div>

---

## 📖 Introduction / 簡介

### English
**The Veracity (揭古)** is an open-source, deterministic digital forensics ledger designed to anchor, index, and verify officially declassified sovereign historical records, diplomatic correspondence, and multilateral treaties. Operating within a statutory **30-year historical declassification window (1945–1996)**, the system continuously monitors and crawls public domain archives across **74 sovereign and international entities**, aggregating primary evidentiary materials without subjective political modification.

The system enforces **Layer-1 Bitstream Fixity** via native SHA-256 digests and **Sigstore Keyless Transparency Log anchoring (Rekor)**, guaranteeing that ingested historical records remain uncorrupted by unauthorized modification, data rot, or intermediary tampering.

### 中文
**「揭古（The Veracity）」** 是一套開源、確定性演算法驅動之歷史公文數位法證總帳。系統落實國際法定 **30 年歷史解密原則（1945 年至 1996 年）**，全域覆蓋並採集全球 **74 個國家主權檔案館與國際多邊法權機構** 之開放目錄與法定解密公文。

平台透過原生 SHA-256 密碼學雜湊與 **Sigstore Keyless 無金鑰透明登記簿（Rekor）** 實現 **Layer-1 位元流不可篡改性（Bitstream Fixity）**，確保公文目錄在傳輸與歸檔過程中免受中間人篡改、事後修飾或數位位元損毀。

---

## 🏛️ Epistemological Boundary / 認識論邊界聲明

* **Bitstream Integrity, Not Truth Adjudication / 擔保位元完整，非歷史實質裁判**：  
  * **EN**: Cryptographic anchoring guarantees strictly that the ingested metadata bitstream matches the authentic public release of the originating repository. The system maintains strict historical neutrality; it does not evaluate, validate, or adjudicate the factual veracity or morality of claims asserted in the historical dossiers. Historical interpretation belongs exclusively to independent scholars and civil society.
  * **ZH**: 密碼學存證僅擔保入庫元數據與原始檔案館開放之公文位元流完全一致。本系統嚴格恪守史學中立，不對公文內文陳述之真偽、主權宣示或道德正當性進行實質裁斷。歷史解釋權永遠歸屬獨立學者與公民社會。

---

## 🛡️ Core Architectural Pillars / 系統核心架構支柱

```text
┌────────────────────────────────────────────────────────────────────────┐
│                   THE VERACITY INGESTION ARCHITECTURE                  │
├────────────────────────────────────────────────────────────────────────┤
│  1. 74 Sovereign & Global Archival Adapters (Isolated Sandbox Crawlers) │
│     └── Fallback: Verified Statutory Seed Engine (Cold War Milestones) │
│                                │                                       │
│                                ▼                                       │
│  2. Deterministic Pipeline Ingestion (BaseAdapter Interface)           │
│     └── Unified Historical Date Window: 1945 to (Current Year - 30)    │
│                                │                                       │
│                                ▼                                       │
│  3. Statistical Anomaly Guard & Circuit Breaker (±2.5σ Moving Window)  │
│     └── Halts execution on unexpected mutation surges / crawler errors │
│                                │                                       │
│                                ▼                                       │
│  4. Layer-1 Fixity & Cryptographic Attestation (Sigstore / Rekor OIDC) │
│     └── Atomic writes: public/api/records-latest.json + SHA-256 Bundle │
│                                │                                       │
│                                ▼                                       │
│  5. Client-Side Forensics Web Terminal (Web Crypto API In-Browser)     │
└────────────────────────────────────────────────────────────────────────┘

```

1. **Deterministic & Non-AI Exclusion / 確定性管線與非 AI 範疇排除**:
* Contains zero Large Language Models (LLMs), machine learning agents, or synthetic generation engines. Fully exempt from EU AI Act and ISO 42001 governance burdens. (See [COMPLIANCE.md](https://www.google.com/search?q=COMPLIANCE.md&utm_source=gemini)).


2. **Public Domain Export Carve-Out / 公共領域出口管制豁免**:
* Processes only officially declassified records exempt under US EAR 15 CFR § 734.3(b)(3), ITAR 22 CFR § 120.34(a)(1), and EU Dual-Use rules.


3. **Statistical Circuit Breaker Guard / 滑動統計斷路器防護**:
* Evaluates net mutation surges ($ΔM$) against a rolling historical standard deviation ($\mu \pm 2.5\sigma$). Automatically blocks tainted commits if crawlers encounter anomalous behavior.


4. **Client-Side Verification / 瀏覽器端本地零知識驗證**:
* Evaluates SHA-256 bitstream digests natively in memory using the browser's `crypto.subtle` API, verifying zero MITM alteration without sending data to third parties.



---

## 🌐 Sovereign & Multilateral Matrix / 74 大全球法證矩陣

| Category / 分類 | Sovereign & International Nodes / 覆蓋節點與機構 |
| --- | --- |
| 1. International Law & Judicature<br>

<br>國際法與多邊條約中樞 | `GLOBAL_UNTS` (UN Treaty Series), `GLOBAL_ICJ` (Hague Court), `GLOBAL_PCA` (Permanent Court of Arbitration), `GLOBAL_ITLOS` (Hamburg Law of the Sea), `GLOBAL_NUREMBERG` (IMT Nuremberg Trials), `ASIA_IMTFE_TOKYO` (Tokyo War Crimes Tribunal), `GLOBAL_AROLSEN` (Arolsen ITS Holocaust Archives), `UN_ARCHIVES` (UN Secretariat), `GLOBAL_ECHR` (European Court of Human Rights), `GLOBAL_ICRC` (Red Cross Archives) |
| 2. Global Finance & Technical Bodies<br>

<br>跨國金融與專業主權治理 | `GLOBAL_BIS` (Bank for International Settlements), `GLOBAL_IMF` (International Monetary Fund), `GLOBAL_WBG` (World Bank Group), `GLOBAL_WTO_GATT` (WTO & GATT 1947), `GLOBAL_IMO` (Maritime Organization), `GLOBAL_ICAO` (Civil Aviation Organization), `GLOBAL_IAEA` (Atomic Energy Agency), `GLOBAL_ITU` (Telecom Union), `GLOBAL_INTERPOL` (Interpol Police Records), `GLOBAL_WHO`, `GLOBAL_WMO`, `GLOBAL_WIPO`, `GLOBAL_ILO`, `GLOBAL_UNHCR` |
| 3. Western Alliances & Intelligence<br>

<br>五眼情報、解密與鐵幕檔案 | `UK_TNA` (UK National Archives, Kew), `US_NARA` (US National Archives), `US_FRUS` (Foreign Relations of the US), `US_CIA_CREST` (CIA Reading Room), `US_NSA_SIGINT` (NSA Declassified Signals), `US_NASA_HISTORY` (NASA Historical STI), `GLOBAL_NATO` (NATO Archives), `CA_LAC` (Canada Archives), `AU_NAA` (National Archives of Australia), `NZ_ANZ` (Archives New Zealand), `GLOBAL_NSARCHIVE` (George Washington Univ), `DE_STASI_BSTU` (East German Stasi Records), `GLOBAL_CWIHP` (Wilson Center Cold War Project), `GLOBAL_OSA` (Blinken Open Society Archives) |
| 4. European Sovereign States<br>

<br>歐洲主權國家檔案局 | `FRANCE_AN` (Archives Nationales), `DE_BARCH` (German Federal Archives), `NL_NA` (Nationaal Archief Netherlands), `SWISS_BAR` (Swiss Federal Archives), `CZ_NA` (National Archives of the Czech Republic), `VA_AAV` (Vatican Apostolic Archives), `GLOBAL_HAEU` (Historical Archives of the EU) |
| 5. Asian Geopolitics & Non-Aligned<br>

<br>亞洲地緣與不結盟運動核心 | `ASIA_ANRI` (Indonesia - Bandung 1955), `ASIA_NAT` (Thailand - SEATO), `ASIA_NAD` (Myanmar - CBI & Panglong), `ASIA_JACAR` (Japan JACAR), `KR_NAK` (National Archives of Korea), `SG_NAS` (Singapore Archives), `PH_NAP` (National Archives of the Philippines), `IN_NAI` (National Archives of India), `IL_ISA` (Israel State Archives), `ZA_NARSSA` (South Africa), `AR_AGN` (Argentina AGN) |
| 6. China National & Academic Heritage<br>

<br>中國中央、高校與國家最高科研 | `CN_NAAC` (National Archives Administration / Central Archives), `CN_NLC` (National Library of China), `CN_CAS` (Chinese Academy of Sciences), `CN_FMA` (Ministry of Foreign Affairs), `CN_PKU` (Peking University), `CN_SHLIB` (Shanghai Library) |
| 7. Republic of China / Taiwan Historical<br>

<br>中華民國近現代與冷戰最高檔案 | `TW_HISTORICA` (Academia Historica - Daxi Collection), `TW_NAA` (National Archives Administration Taiwan), `TW_ASMH` (Academia Sinica Modern History), `GLOBAL_HOOVER` (Hoover Institution - Chiang Diaries) |
| 8. Hong Kong Constitutional Cross-Verification<br>

<br>香港行政、立法、司法與社會特藏 | `HK_PRO` (Public Records Office / HKRS), `HK_LEGCO` (Legislative Council Hansard), `HK_JUDICIARY` (HK Judiciary Law Reports), `HK_HKU` (HKU Special Collections), `HK_CUHK` (CUHK Special Collections), `HK_HKBU` (HKBU Archives), `HK_HKUST` (HKUST Archives), `HK_HKHP` (Hong Kong Heritage Project - Kadoorie) |

---

## 🚀 Quick Start & Development / 本地開發與快速上手

### Requirements / 環境需求

* **Python**: 3.11+ (Fully compatible with Python 3.14)
* **OS**: Linux / macOS / Windows WSL2

### Installation / 安裝依賴

```bash
git clone [https://github.com/jackylawck/Veracity.git](https://github.com/jackylawck/Veracity.git)
cd Veracity

# Install pinned dependencies
pip install -r requirements.lock

```

### Running Test Suite / 執行合規性單元測試

The test suite dynamically evaluates interface compliance and date window calculators across all 74 registered adapter modules:

```bash
pytest

```

### Running Ingestion Pipeline / 執行總帳採集

```bash
# Dry run: crawls and parses records in memory without committing
python scripts/ingest.py --dry-run

# Production ingestion: executes atomic writes to public/api/
python scripts/ingest.py

```

---

## 📜 Regulatory Governance & Compliance / 法規合規體系

* **[COMPLIANCE.md](https://www.google.com/search?q=COMPLIANCE.md&utm_source=gemini)**: Statutory Compliance, Jurisdictional Carve-Outs, ITAR/EAR Exemptions, and Non-AI Deterministic Classification.
* **[DATA_GOVERNANCE.md](https://www.google.com/search?q=DATA_GOVERNANCE.md&utm_source=gemini)**: Information Security (ISO/IEC 27001) and Privacy Information Management (ISO/IEC 27701) Policy.
* **[EPISTEMOLOGY.md](https://www.google.com/search?q=EPISTEMOLOGY.md&utm_source=gemini)**: Academic boundaries, archival fonds representation, and historiographical methodology.
* **[SECURITY.md](SECURITY.md)**: Vulnerability reporting policy and cryptographic attestation verification steps.

---

## 📄 License / 授權條款

This project is licensed under the terms of the [MIT License](https://www.google.com/search?q=LICENSE&utm_source=gemini).

Official state dossiers and metadata remain in the public domain or under the statutory open government licensing of their respective sovereign repositories.
