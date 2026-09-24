# Changelog (歷史變更日誌)

All notable changes to the data schema, ingestion pipeline, and verification architecture of "The Veracity (揭古)" are documented here.  
所有對《揭古 · The Veracity》數據結構、採集管線與驗證架構的實質變更均記錄於此。  
This project adheres to [Semantic Versioning 2.0.0](https://semver.org/).  
本專案嚴格遵循語意化版本規範 2.0.0。

---

## [2.1.0] - 2026-09-24

### Added / 新增功能
* **74 Sovereign & Global Archival Matrix / 74 大全球與主權法證節點矩陣**:
  * **EN**: Scaled pipeline dynamically across 74 sovereign and international entities, including UNTS, ICJ, IMTFE (Tokyo Trials), Nuremberg IMT, US NARA, UK TNA, BStU (Stasi), China NAAC, and Academia Historica.
  * **ZH**: 動態擴展覆蓋聯合國條約集 (UNTS)、海牙國際法院 (ICJ)、東京審判 (IMTFE)、紐倫堡審判 (IMT)、美英五眼情報 (NARA/TNA/CIA CREST)、東德史塔西 (BStU)、中國中央檔案館 (NAAC)、國史館大溪檔案 (TW_HISTORICA) 等 74 個主權檔案館。
* **Curated Authority Seed Fallback Engine / 法定權威種子回退機制**:
  * **EN**: Implemented baseline verified seeds in `adapters/base.py` covering 16 landmark treaties and judicial rulings. When upstream portals encounter Cloudflare 403 blocks, 404 maintenance, or network errors, verified historical primary dossiers are automatically injected to preserve the transnational evidentiary chain.
  * **ZH**: 於 `adapters/base.py` 實裝 16 大指標性歷史條約與法庭審判種子庫；當海外端點遭遇 Cloudflare 403 攔截、維護 404 或連線異常時，自動注入具備國際法證地位的法定真實文獻，確保跨國對比鏈不斷裂。
* **Total Ingested Dossiers Surpassed 120+ / 總帳公文筆數突破 120+ 筆**:
  * **EN**: Live cryptographically anchored ledger expanded from 46 baseline items to 121 verified sovereign dossiers.
  * **ZH**: 採集引擎順利將經密碼學錨定之公文由 46 筆基礎資料推升至 121 筆法定卷宗。
* **Statutory Compliance & ISO Governance Architecture / 全域合規與資安治理體系**:
  * **EN**: Published `COMPLIANCE.md` (Non-AI deterministic system carve-out, US EAR 15 CFR § 734.3(b)(3) / ITAR public domain export exemptions, and GDPR Art. 89 / HK PDPO Sec. 62 deceased and historical research exemptions).
  * **ZH**: 發佈 `COMPLIANCE.md`（明文化非 AI 系統排除聲明、美國 EAR 15 CFR § 734.3(b)(3) 及 ITAR 公共領域出口管制豁免，以及 GDPR 第 89 條 / 香港私隱條例第 62 條之已故人士與歷史研究豁免）。
  * **EN**: Published `DATA_GOVERNANCE.md` aligned with ISO/IEC 27001:2022 (InfoSec) and ISO/IEC 27701:2019 (PIMS).
  * **ZH**: 發佈 `DATA_GOVERNANCE.md`（對標 ISO/IEC 27001:2022 資訊安全控制與 ISO/IEC 27701:2019 隱私資訊管理規範）。
* **Enterprise CI SAST & Automated Compliance Suite / 企業級 CI SAST 與動態測試**:
  * **EN**: Integrated Trivy dependency scanning, CycloneDX SBOM generation, and added `tests/test_adapters.py` with `pytest.ini` pythonpath resolution (76/76 unit tests passed).
  * **ZH**: 整合 Trivy 依賴掃描與 CycloneDX SBOM 自動導出；新增 `tests/test_adapters.py` 並配置 `pytest.ini`，實現 76 項單元測試 100% 通過。
* **Client-Side Forensics Terminal / 前端即時法證驗證終端升級**:
  * **EN**: Upgraded `public/index.html` with browser-native Web Cryptography API (`crypto.subtle`) for zero-MITM SHA-256 verification and multi-field live search across call numbers, repositories, and fonds.
  * **ZH**: 前端網頁整合瀏覽器原生 Web Cryptography API，支援客戶端即時計算總帳 SHA-256 雜湊，並提供檔號、全宗、年代多維度即時檢索。

### Changed / 調整與優化
* **Statistical Circuit Breaker Recalibration / 滑動統計斷路器校準與擴容批准**:
  * **EN**: Transitioned moving-window input to net mutations ($\Delta M$), providing mathematical anomaly prevention ($\pm 2.5\sigma$) alongside explicit maintainer expansion approvals.
  * **ZH**: 改以實質淨變更量（$\Delta M$）為統計視窗輸入，建立 $\pm 2.5\sigma$ 異常防護與維護者合法全量擴容批准機制。
* **Dynamic Rolling Historical Window / 動態滾動歷史時間窗口**:
  * **EN**: Dynamic statutory declassification calculator anchored to 1945 and advancing automatically via `current_year - 30` without manual code edits.
  * **ZH**: 以 1945 年為起點，依據國際法定 30 年法則（`當前年份 - 30`）自動滾動截止年份，無需人工硬編碼。

---

## [2.0.0] - 2026-09-23

### Added / 新增功能
* **Bilingual Schema & Dashboard / 繁英雙語架構**:
  * **EN**: Complete English and Traditional Chinese localization for archival context and UI console.
  * **ZH**: `archival_context` 與前端儀表板全面對齊繁體中文與英文雙語映射。
* **Plugin-Based Dynamic Adapter Engine / 插件化動態適配器反射引擎**:
  * **EN**: Modular class discovery in `adapters/` inheriting from `BaseAdapter`.
  * **ZH**: 模組化動態類別載入架構，所有適配器統一繼承 `BaseAdapter` 介面契約。
* **Offline Attestation & Archiving / 離線可驗證性存證**:
  * **EN**: Integrated Sigstore Keyless bundle generation and Wayback Machine external archiving workflows.
  * **ZH**: 實裝 Sigstore Keyless 無金鑰透明簽署包與 Wayback Machine 外部留底工作流。
