"""
United Nations High Commissioner for Refugees (UNHCR Archives) Production Adapter
符合 BaseAdapter 統一時間窗口，採集戰後難民危機、越戰船民（含香港難民營）與庇護審批原始公文。
"""
import re
import html
import time
import logging
import requests
from typing import List, Dict, Any, Optional, Set
from datetime import datetime, timezone
from adapters.base import BaseAdapter

logger = logging.getLogger("Veracity.Adapters.UNHCR")

class UnhcrArchivesIngestionError(Exception):
    pass

class UnhcrArchivesProductionAdapter(BaseAdapter):
    NAME = "GLOBAL_UNHCR"
    # 聯合國難民署公開歷史檔案檢索 API
    API_URL = "https://www.unhcr.org/api/v1/archives/search"
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
            return "Untitled UNHCR Humanitarian Archival Record"
        stripped = re.sub(r"<[^>]+>", "", raw_text)
        unescaped = html.unescape(stripped)
        return " ".join(unescaped.split()).strip()

    def _execute_with_retry(self, params: Dict[str, Any]) -> Dict[str, Any]:
        for attempt in range(1, self.max_retries + 1):
            try:
                resp = self.session.get(self.API_URL, params=params, timeout=self.timeout)
                if resp.status_code == 429:
                    backoff = 2 ** attempt
                    logger.warning(f"[UNHCR] Rate limit (429). Retrying in {backoff}s...")
                    time.sleep(backoff)
                    continue
                if resp.status_code in (404, 502, 503):
                    logger.warning(f"[UNHCR] Gateway offline ({resp.status_code}).")
                    return {"results": []}
                resp.raise_for_status()
                return resp.json()
            except requests.RequestException as exc:
                if attempt == self.max_retries:
                    raise UnhcrArchivesIngestionError(f"UNHCR API unreachable: {exc}") from exc
                time.sleep(2 ** attempt)
        raise UnhcrArchivesIngestionError("UNHCR retry budget exhausted.")

    def fetch_records(self, max_pages: int = 2, page_size: int = 15) -> List[Dict[str, Any]]:
        ingested = []
        seen_ids: Set[str] = set()

        start_year, end_year = self.get_unified_date_window()
        # 聯合國難民署於 1950 年成立
        unhcr_start = max(1950, int(start_year))
        logger.info(f"[UNHCR] Applying Historical Window: {unhcr_start} to {end_year}")

        for page_idx in range(max_pages):
            params = {
                "q": "Refugees Asylum Hong Kong Boat People Resettlement",
                "startYear": str(unhcr_start),
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
                    fonds_id = str(doc.get("referenceCode") or doc.get("id", "")).strip()
                    if not fonds_id or fonds_id in seen_ids:
                        continue
                    seen_ids.add(fonds_id)

                    clean_title = self.clean_text(doc.get("title"))
                    series_name = doc.get("series", "Field Operations & Protection Missions Series")
                    call_no = doc.get("referenceCode", f"UNHCR-{fonds_id}")

                    record: Dict[str, Any] = {
                        "record_id": f"unhcr:{fonds_id.replace('/', '_').replace(' ', '').replace(':', '_')}",
                        "verification_level": "metadata_only",
                        "fixity": {"hash_algorithm": "NONE", "hash_value": None, "file_size_bytes": None},
                        "archival_context": {
                            "repository": {
                                "en": "UNHCR Records and Archives Section (Geneva)",
                                "zh": "聯合國難民署歷史檔案部 (日內瓦)"
                            },
                            "fonds": "Fonds 11 (UNHCR Central Registry)",
                            "series": series_name,
                            "call_number": call_no,
                            "title": {
                                "en": clean_title,
                                "zh": None
                            },
                            "covering_dates": doc.get("dateDisplay", f"{unhcr_start}-{end_year}")
                        },
                        "heuristic_clues": {
                            "phase_2_status": "STUB_ACTIVE"
                        },
                        "rights_statement": {
                            "license_category": "UN_Public_Information_Rules",
                            "reuse_permitted": True,
                            "legal_disclaimer": {
                                "en": "Declassified UNHCR historical archives made available under the UNHCR Access to Archives Policy (20-year rule).",
                                "zh": "依聯合國難民署《檔案查閱政策》（20年解密法則）向公眾開放之歷史檔案。"
                            }
                        },
                        "provenance": {
                            "source_manifest_url": f"https://www.unhcr.org/archives/{fonds_id}",
                            "retrieved_at_utc": datetime.now(timezone.utc).isoformat()
                        }
                    }
                    ingested.append(record)

                time.sleep(0.5)

            except Exception as e:
                logger.error(f"[UNHCR] Batch isolated failure: {e}")
                break

        logger.info(f"[UNHCR] Pipeline successfully acquired {len(ingested)} distinct records.")
        return ingested
