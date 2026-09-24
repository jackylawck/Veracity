# Changelog (歷史變更日誌)

所有對《揭古 · The Veracity》數據結構與 API 的實質變更均記錄於此。
本專案嚴格遵循 [Semantic Versioning 2.0.0](https://semver.org/)。

## [2.1.0] - 2026-09-24
### Added
- 企業級 CI SAST 防禦：整合 Trivy 容器/依賴掃描與 CycloneDX SBOM 自動導出。
- 前端安全加固：實裝 Strict Content-Security-Policy (CSP) 與 XSS 消毒過濾。
- 動態發現機制：依據法定 30 年規則自動推進時間窗口，實裝分頁集合去重防禦。

### Changed
- 斷路器訊號校準：改以「實質淨變更量（Mutations）」為統計視窗輸入，避免死水樣態。
- 法律聲明精確化：明文化排除 EU AI Act 適用，誠實降調 ISO 42001/27001 聲明為原則借鑒。

## [2.0.0] - 2026-09-23
### Added
- 繁英雙語支援：`archival_context` 與前端儀表板全面對齊中英雙語映射。
- 插件化動態適配器反射引擎（`adapters/base.py` + `adapters/tna_adapter.py`）。
- 離線可驗證性：Sigstore Keyless 簽署包生成與 Wayback 外部留底工作流。
