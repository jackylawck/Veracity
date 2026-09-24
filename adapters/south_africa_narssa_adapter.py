"""
National Archives and Records Service of South Africa (NARSSA / NAAIRS) Production Adapter
符合 BaseAdapter 統一時間窗口，採集戰後大英國協南部非洲非殖民化、邊界軍事衝突與國家安全檔案。
"""
import re
import html
import time
import logging
import requests
from typing import List, Dict, Any, Optional, Set
from datetime import datetime, timezone
from adapters.base import BaseAdapter

logger = logging.getLogger("Veracity.Adapters.NARSSA")

class NarssaIngestionError(Exception):
    pass

class SouthAfricaNarssaProductionAdapter(BaseAdapter):
    NAME = "ZA_NARSSA"
    # 南非國家檔案系統 NAAIRS 公開查詢 REST API
    API_URL = "http://www.national.archives.gov.za/api/v1/naairs/search"
    USER_AGENT = "VeracityLedger/2.0 (Historical Forensics Engine; Solo-Maintainer Verification)"

    def __init__(self, timeout: int = 15, max_retries: int = 3):
        self.timeout = timeout
        self.max_retries = max_retries
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": self.USER_AGENT,
            "Accept": "application/json"
        })

    @staticmethod
    def clean_text(raw_text: Optional[str]) -> str:
        if not raw_text:
            return "Untitled South African Archival Item"
        stripped = re.sub(r"<[^>]+>", "", raw_text)
        unescaped = html.unescape(stripped)
        return " ".join(unescaped.split()).strip()

    def _execute_with_retry(self, params: Dict[str, Any]) -> Dict[str, Any]:
        for attempt in range(1, self.max_retries + 1):
            try:
                resp = self.session.get(self.API_URL, params=params, timeout=self.timeout)
                if resp.status_code == 429:
                    backoff = 2 ** attempt
                    logger.warning(f"[NARSSA] Rate limited (429). Retrying in {backoff}s...")
                    time.sleep(backoff)
                    continue
                if resp.status_code in (404, 502, 503):
                    logger.warning(f"[NARSSA] NAAIRS gateway maintenance ({resp.status_code}).")
                    return {"results": []}
                resp.raise_for_status()
                return resp.json()
            except requests.RequestException as exc:
                if attempt == self.max_retries:
                    raise NarssaIngestionError(f"NARSSA API unreachable: {exc}") from exc
                time.sleep(2 ** attempt)
        raise NarssaIngestionError("NARSSA retry budget exhausted.")

    def fetch_records(self, max_pages: int = 2, page_size: int = 15) -> List[Dict[str, Any]]:
        ingested = []
        seen_ids: Set[str] = set()

        start_year, end_year = self.get_unified_date_window()
        logger.info(f"[NARSSA] Applying Unified Historical Window: {start_year} to {end_year}")

        for page_idx in range(max_pages):
            params = {
                "term": "Foreign Affairs Commonwealth Border Defence declassified",
                "startYear": str(start_year),
                "endYear": str(end_year),
                "page": str(page_idx + 1),
                "limit": str(page_size)
            }

            try:
                payload = self._execute_with_retry(params)
                records = payload.get("results", []) or payload.get("records", [])

                if not records:
                    break

                for doc in records:
                    doc_id = str(doc.get("recordId") or doc.get("identifier", "")).strip()
                    if not doc_id or doc_id in seen_ids:
                        continue
                    seen_ids.add(doc_id)

                    clean_title = self.clean_text(doc.get("title") or doc.get("description"))
                    dept = doc.get("department", "Department of Foreign Affairs & Defence")
                    ref_code = doc.get("reference", f"NARSSA-SAB-{doc_id}")

                    record: Dict[str, Any] = {
                        "record_id": f"narssa:{doc_id.replace('/', '_').replace(' ', '')}",
                        "verification_level": "metadata_only",
                        "fixity": {"hash_algorithm": "NONE", "hash_value": None, "file_size_bytes": None},
                        "archival_context": {
                            "repository": {
                                "en": "National Archives and Records Service of South Africa (Pretoria)",
                                "zh": "南非國家檔案及記錄服務處 (普勒托利亞)"
                            },
                            "fonds": f"Central Government Archives ({dept})",
                            "series": doc.get("sourceSeries", "Post-War Commonwealth & Border Defence Series"),
                            "call_number": ref_code,
                            "title": {
                                "en": clean_title,
                                "zh": None
                            },
                            "covering_dates": doc.get("dateRange", f"{start_year}-{end_year}")
                        },
                        "heuristic_clues": {
                            "phase_2_status": "STUB_ACTIVE"
                        },
                        "rights_statement": {
                            "license_category": "South_Africa_National_Archives_Act_43_1996",
                            "reuse_permitted": True,
                            "legal_disclaimer": {
                                "en": "Declassified state archives transferred under National Archives and Record Service of South Africa Act (Act No. 43 of 1996).",
                                "zh": "依南非《1996年第43號國家檔案及記錄服務法》（Act No. 43 of 1996）依法解密開放之國家公文。"
                            }
                        },
                        "provenance": {
                            "source_manifest_url": f"http://www.national.archives.gov.za/naairs/details/{doc_id}",
                            "retrieved_at_utc": datetime.now(timezone.utc).isoformat()
                        }
                    }
                    ingested.append(record)

                time.sleep(0.5)

            except Exception as e:
                logger.error(f"[NARSSA] Batch isolated failure: {e}")
                break

        logger.info(f"[NARSSA] Pipeline successfully acquired {len(ingested)} distinct records.")
        return ingested
