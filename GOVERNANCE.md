# Governance, Legal Positioning & Compliance Scope Matrix
## 數據治理、法律邊界與全球法規適用性矩陣

### 1. 監管範圍與法律定位 (Regulatory Scope & Non-Legal Advice)
本專案為公共歷史檔案出處索引庫，所載資訊不構成正式法律諮詢意見。

| 法規 / 國際標準 | 適用性狀態 (Applicability Status) | 專案真實合規措施與實踐 |
|---|---|---|
| **EU AI Act (歐盟人工智慧法案)** | **Uninvolved / Out of Scope (不涉及)** | 本系統為純確定性規則索引引擎，不涉及高風險 AI 系統或通用生成式模型。 |
| **ISO/IEC 42001 (AIMS)** | **Principles Referenced, Not Certified (原則借鑒)** | 僅借鑒其資料來源追溯與資料譜系原則；專案非 ISO 認證組織實體。 |
| **中國國家網信辦 (CAC 深度合成/AI 規定)** | **Not Applicable (非監管主體)** | 境外靜態開源發布，無提供深度合成演算法服務，不涉及境內演算法備案。 |
| **歐盟 GDPR** | **Article 89 Compliant (公共利益存檔)** | 前言第 27 條排除已故者；在世個資嚴格恪守學術存檔與數據最小化原則。 |
| **香港《個人資料（私隱）條例》(PDPO)** | **Privacy-by-Design 實踐** | 前端零 Cookie、零追蹤器、無伺服器端日誌收集，落實保障資料原則 (DPP)。 |
| **ISO/IEC 27001 / 27701** | **Security Principles Referenced (原則借鑒)** | 實踐最小權限、依賴雜湊鎖定、Sigstore 簽章，非認證組織實體。 |
| **出口管制 (EAR 15 CFR § 734.7 / ITAR)** | **Public Domain Exempt (公開出版豁免)** | 僅索引主權檔案館法定解密公報，不涉及受限管制國防技術數據。 |

### 2. 啟發式線索階段宣告 (Heuristic Clues Notice)
- 本庫輸出之 `heuristic_clues` 僅為預留介面（Stub），尚未實裝全域拓撲比對算法。本庫恪守學術誠信，絕不輸出偽造之推論結論。

### 3. 單人維護模式宣告 (Solo-Maintainer Operational Model)
- 本專案由獨立研究者維護，拒絕形式主義。
- 所有代碼變更強制要求 **GPG/SSH 簽名提交**，發布前必須通過 CI 測試與 Schema 閘門。
- 採用滑動視窗 $\pm 2.5\sigma$ 統計斷路器（以淨變更量為訊號源），防止通知疲勞，實現系統長期健康自治。
