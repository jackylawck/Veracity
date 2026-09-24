"""
United Nations Archives and Records Management Section (UN ARMS) Production Adapter
符合 BaseAdapter 統一時間窗口，採集聯合國安理會與維和行動歷史解密檔案。
"""
import re
import html
import time
import logging
import requests
from typing import List, Dict, Any, Optional, Set
from datetime import datetime, timezone
from adapters.base import BaseAdapter

logger = logging.getLogger("Veracity.Adapters.UN")

class UnArchivesIngestionError(Exception):
    pass

class UnArchivesProductionAdapter(BaseAdapter):
    NAME = "UN_ARCHIVES"
    # 聯合國檔案公開檢索端點 (OAI-PMH / REST 開放查詢通道)
    API_URL = "https://search.archives.un.org/api/records/search"
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
            return "Untitled United Nations Archival Dossier"
        stripped = re.sub(r"<[^>]+>", "", raw_text)
        unescaped = html.unescape(stripped)
        return " ".join(unescaped.split()).strip()

    def _execute_with_retry(self, params: Dict[str, Any]) -> Dict[str, Any]:
        for attempt in range(1, self.max_retries + 1):
            try:
                resp = self.session.get(self.API_URL, params=params, timeout=self.timeout)
                if resp.status_code == 429:
                    backoff = 2 ** attempt
                    logger.warning(f"[UN] Rate limited (429). Retrying in {backoff}s...")
                    time.sleep(backoff)
                    continue
                if not resp.ok:
                    logger.error(f"[UN] API Error {resp.status_code}: {resp.text}")
                resp.raise_for_status()
                return resp.json()
            except requests.RequestException as exc:
                if attempt == self.max_retries:
                    raise UnArchivesIngestionError(f"UN Archives API unreachable: {exc}") from exc
                time.sleep(2 ** attempt)
        raise UnArchivesIngestionError("UN retry budget exhausted.")

    def fetch_records(self, max_pages: int = 2, page_size: int = 15) -> List[Dict[str, Any]]:
        ingested = []
        seen_ids: Set[str] = set()

        start_year, end_year = self.get_unified_date_window()
        logger.info(f"[UN] Applying Unified Historical Window: {start_year} to {end_year}")

        for page_idx in range(max_pages):
            params = {
                "q": "Security Council Peacekeeping Mission",
                "start_year": start_year,
                "end_year": end_year,
                "page": str(page_idx + 1),
                "limit": str(page_size)
            }

            try:
                payload = self._execute_with_retry(params)
                records_batch = payload.get("results", [])

                if not records_batch:
                    logger.info(f"[UN] No more records found at page {page_idx + 1}.")
                    break

                for item in records_batch:
                    doc_id = item.get("id") or item.get("identifier")
                    if not doc_id or doc_id in seen_ids:
                        continue
                    seen_ids.add(doc_id)

                    title_clean = self.clean_text(item.get("title"))
                    ref_code = item.get("reference_code", f"UN-{doc_id}")
                    
                    # 聯合國全宗號拆解（例如 AG-044 代表特定特別專使署）
                    fonds_name = item.get("fonds_title", "UN General Secretariat Fonds")
                    dates_str = item.get("date_range", f"{start_year}-{end_year}")

                    record: Dict[str, Any] = {
                        "record_id": f"un:{doc_id}",
                        "verification_level": "metadata_only",
                        "fixity": {"hash_algorithm": "NONE", "hash_value": None, "file_size_bytes": None},
                        "archival_context": {
                            "repository": {
                                "en": "United Nations Archives and Records Management Section (New York)",
                                "zh": "聯合國檔案和記錄管理科 (紐約總部)"
                            },
                            "fonds": fonds_name,
                            "series": item.get("series_title", "Central Peacekeeping & Political Series"),
                            "call_number": ref_code,
                            "title": {
                                "en": title_clean,
                                "zh": None
                            },
                            "covering_dates": dates_str
                        },
                        "heuristic_clues": {
                            "phase_2_status": "STUB_ACTIVE"
                        },
                        "rights_statement": {
                            "license_category": "UN_Public_Information",
                            "reuse_permitted": True,
                            "legal_disclaimer": {
                                "en": "Declassified UN historical records open for research under UN ARMS Access Policy.",
                                "zh": "依聯合國檔案查閱政策（UN ARMS Policy）公開之歷史檔案，可用於學術與公眾檢驗。"
                            }
                        },
                        "provenance": {
                            "source_manifest_url": f"https://search.archives.un.org/detail/{doc_id}",
                            "retrieved_at_utc": datetime.now(timezone.utc).isoformat()
                        }
                    }
                    ingested.append(record)

                time.sleep(0.5)

            except Exception as e:
                logger.error(f"[UN] Page {page_idx + 1} isolated failure: {e}")
                break

        logger.info(f"[UN] Pipeline successfully acquired {len(ingested)} distinct records.")
        return ingested
