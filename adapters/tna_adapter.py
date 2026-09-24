"""
UK The National Archives (TNA) Production Adapter
符合 TNA API 規格（純年份格式），落實統一歷史窗口與防禦性分頁。
"""
import re
import html
import time
import logging
import requests
from typing import List, Dict, Any, Optional, Set
from datetime import datetime, timezone
from adapters.base import BaseAdapter

logger = logging.getLogger("Veracity.Adapters.TNA")

class AdapterIngestionError(Exception):
    pass

class TnaProductionAdapter(BaseAdapter):
    NAME = "UK_TNA"
    API_URL = "https://discovery.nationalarchives.gov.uk/API/records/v1/collection/search"
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
    def clean_html_markup(raw_text: Optional[str]) -> str:
        if not raw_text:
            return "Untitled Classified Document"
        stripped = re.sub(r"<[^>]+>", "", raw_text)
        unescaped = html.unescape(stripped)
        return " ".join(unescaped.split()).strip()

    def _execute_with_retry(self, params: Dict[str, Any]) -> Dict[str, Any]:
        for attempt in range(1, self.max_retries + 1):
            try:
                resp = self.session.get(self.API_URL, params=params, timeout=self.timeout)
                if resp.status_code == 429:
                    backoff = 2 ** attempt
                    logger.warning(f"[TNA] Rate Limited (429). Retrying in {backoff}s...")
                    time.sleep(backoff)
                    continue
                resp.raise_for_status()
                return resp.json()
            except requests.RequestException as exc:
                if attempt == self.max_retries:
                    raise AdapterIngestionError(f"TNA API unreachable: {exc}") from exc
                time.sleep(2 ** attempt)
        raise AdapterIngestionError("Retry budget exhausted.")

    def fetch_records(self, max_pages: int = 3, page_size: int = 15) -> List[Dict[str, Any]]:
        ingested = []
        seen_batch_ids: Set[str] = set()

        # 獲取純 4 位數年份（例如 "1945" 與 "1996"）
        start_year, end_year = self.get_unified_date_window()
        logger.info(f"[TNA] Applying Unified Historical Window: {start_year} to {end_year}")

        for page_idx in range(max_pages):
            params = {
                "sps.searchQuery": "Cold War",
                "sps.heldByFilter": "TNA",
                "sps.startDate": start_year,
                "sps.endDate": end_year,
                "sps.page": str(page_idx),
                "sps.resultsPageSize": str(page_size)
            }

            try:
                payload = self._execute_with_retry(params)
                records_batch = payload.get("records", [])

                if not records_batch:
                    break

                current_batch_ids = {item.get("id") for item in records_batch if item.get("id")}
                if current_batch_ids.issubset(seen_batch_ids):
                    logger.warning(f"[TNA] Duplicate batch encountered at page {page_idx + 1}. Halting.")
                    break
                seen_batch_ids.update(current_batch_ids)

                for item in records_batch:
                    doc_id = item.get("id")
                    reference = item.get("reference")
                    if not doc_id or not reference:
                        continue

                    clean_title = self.clean_html_markup(item.get("title"))
                    parts = reference.split("/")
                    fonds = parts[0].split()[0] if parts else "UNKNOWN"
                    series = parts[0] if parts else "UNKNOWN"

                    record: Dict[str, Any] = {
                        "record_id": f"tna:{doc_id}",
                        "verification_level": "metadata_only",
                        "fixity": {"hash_algorithm": "NONE", "hash_value": None, "file_size_bytes": None},
                        "archival_context": {
                            "repository": {
                                "en": "The National Archives (Kew, Richmond)",
                                "zh": "英國國家檔案館 (Kew)"
                            },
                            "fonds": fonds,
                            "series": series,
                            "call_number": reference,
                            "title": {
                                "en": clean_title,
                                "zh": None
                            },
                            "covering_dates": item.get("coveringDates", "Historical")
                        },
                        "heuristic_clues": {
                            "phase_2_status": "STUB_ACTIVE"
                        },
                        "rights_statement": {
                            "license_category": "Open_Government_Licence_v3",
                            "reuse_permitted": True,
                            "legal_disclaimer": {
                                "en": "Subject to UK Crown Copyright & OGL v3.0 conditions. Not formal legal advice.",
                                "zh": "受英國王室版權及 OGL v3.0 規範。非正式法律意見。"
                            }
                        },
                        "provenance": {
                            "source_manifest_url": f"https://discovery.nationalarchives.gov.uk/details/r/{doc_id}",
                            "retrieved_at_utc": datetime.now(timezone.utc).isoformat()
                        }
                    }
                    ingested.append(record)

                time.sleep(0.5)

            except Exception as e:
                logger.error(f"[TNA] Page {page_idx + 1} isolated failure: {e}")
                break

        logger.info(f"[TNA] Pipeline successfully acquired {len(ingested)} distinct records.")
        return ingested
