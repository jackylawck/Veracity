"""
National Archives of the Philippines (NAP) Production Adapter
符合 BaseAdapter 統一時間窗口，採集戰後美菲共同防禦、SEATO 東南亞條約與冷戰前哨解密檔案。
"""
import re
import html
import time
import logging
import requests
from typing import List, Dict, Any, Optional, Set
from datetime import datetime, timezone
from adapters.base import BaseAdapter

logger = logging.getLogger("Veracity.Adapters.NAP")

class NapIngestionError(Exception):
    pass

class PhilippinesNapProductionAdapter(BaseAdapter):
    NAME = "PH_NAP"
    # 菲律賓國家檔案館公開開放檢索端點
    API_URL = "https://nationalarchives.gov.ph/api/v1/records/search"
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
            return "Untitled Philippine Historical Archival Record"
        stripped = re.sub(r"<[^>]+>", "", raw_text)
        unescaped = html.unescape(stripped)
        return " ".join(unescaped.split()).strip()

    def _execute_with_retry(self, params: Dict[str, Any]) -> Dict[str, Any]:
        for attempt in range(1, self.max_retries + 1):
            try:
                resp = self.session.get(self.API_URL, params=params, timeout=self.timeout)
                if resp.status_code == 429:
                    backoff = 2 ** attempt
                    logger.warning(f"[NAP] Rate limited (429). Retrying in {backoff}s...")
                    time.sleep(backoff)
                    continue
                if resp.status_code in (404, 502, 503):
                    logger.warning(f"[NAP] Portal service maintenance ({resp.status_code}).")
                    return {"data": []}
                resp.raise_for_status()
                return resp.json()
            except requests.RequestException as exc:
                if attempt == self.max_retries:
                    raise NapIngestionError(f"NAP API unreachable: {exc}") from exc
                time.sleep(2 ** attempt)
        raise NapIngestionError("NAP retry budget exhausted.")

    def fetch_records(self, max_pages: int = 2, page_size: int = 15) -> List[Dict[str, Any]]:
        ingested = []
        seen_ids: Set[str] = set()

        start_year, end_year = self.get_unified_date_window()
        logger.info(f"[NAP] Applying Unified Historical Window: {start_year} to {end_year}")

        for page_idx in range(max_pages):
            params = {
                "q": "Foreign Affairs Defense Treaty Cold War",
                "startYear": start_year,
                "endYear": end_year,
                "page": str(page_idx + 1),
                "pageSize": str(page_size)
            }

            try:
                payload = self._execute_with_retry(params)
                items = payload.get("data", []) or payload.get("records", [])

                if not items:
                    break

                for doc in items:
                    doc_id = str(doc.get("recordId") or doc.get("id", "")).strip()
                    if not doc_id or doc_id in seen_ids:
                        continue
                    seen_ids.add(doc_id)

                    en_title = self.clean_text(doc.get("title"))
                    dept = doc.get("department", "Department of Foreign Affairs / National Defense")
                    accession_no = doc.get("accessionNumber", f"NAP-{doc_id}")

                    record: Dict[str, Any] = {
                        "record_id": f"phnap:{doc_id.replace('/', '_').replace(' ', '')}",
                        "verification_level": "metadata_only",
                        "fixity": {"hash_algorithm": "NONE", "hash_value": None, "file_size_bytes": None},
                        "archival_context": {
                            "repository": {
                                "en": "National Archives of the Philippines (Manila)",
                                "zh": "菲律賓國家檔案館 (馬尼拉)"
                            },
                            "fonds": dept,
                            "series": doc.get("series", "Post-War Republic Treaties & Security Series"),
                            "call_number": accession_no,
                            "title": {
                                "en": en_title,
                                "zh": None
                            },
                            "covering_dates": doc.get("coveringDates", f"{start_year}-{end_year}")
                        },
                        "heuristic_clues": {
                            "phase_2_status": "STUB_ACTIVE"
                        },
                        "rights_statement": {
                            "license_category": "PH_Public_Domain_Archives",
                            "reuse_permitted": True,
                            "legal_disclaimer": {
                                "en": "Public records made accessible under Republic Act No. 9470 (National Archives of the Philippines Act).",
                                "zh": "依菲律賓第 9470 號共和國法案（國家檔案法）解密開放之政府歷史檔案。"
                            }
                        },
                        "provenance": {
                            "source_manifest_url": f"https://nationalarchives.gov.ph/records/{doc_id}",
                            "retrieved_at_utc": datetime.now(timezone.utc).isoformat()
                        }
                    }
                    ingested.append(record)

                time.sleep(0.5)

            except Exception as e:
                logger.error(f"[NAP] Batch isolated failure: {e}")
                break

        logger.info(f"[NAP] Pipeline successfully acquired {len(ingested)} distinct records.")
        return ingested
