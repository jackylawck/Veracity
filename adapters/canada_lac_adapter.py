"""
Library and Archives Canada (LAC / BAC) Production Adapter
符合 BaseAdapter 統一時間窗口，採集北美防衛司令部 (NORAD)、北約外交及五眼聯盟歷史解密檔案。
"""
import re
import html
import time
import logging
import requests
from typing import List, Dict, Any, Optional, Set
from datetime import datetime, timezone
from adapters.base import BaseAdapter

logger = logging.getLogger("Veracity.Adapters.CanadaLAC")

class CanadaLacIngestionError(Exception):
    pass

class CanadaLacProductionAdapter(BaseAdapter):
    NAME = "CA_LAC"
    # 加拿大國家圖書館暨檔案館公開 Open Data REST 端點
    API_URL = "https://recherche-collection-search.bac-lac.gc.ca/api/records/search"
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
            return "Untitled Canadian Government Archival Item"
        stripped = re.sub(r"<[^>]+>", "", raw_text)
        unescaped = html.unescape(stripped)
        return " ".join(unescaped.split()).strip()

    def _execute_with_retry(self, params: Dict[str, Any]) -> Dict[str, Any]:
        for attempt in range(1, self.max_retries + 1):
            try:
                resp = self.session.get(self.API_URL, params=params, timeout=self.timeout)
                if resp.status_code == 429:
                    backoff = 2 ** attempt
                    logger.warning(f"[CA_LAC] Rate limit (429). Retrying in {backoff}s...")
                    time.sleep(backoff)
                    continue
                if resp.status_code in (404, 502, 503):
                    logger.warning(f"[CA_LAC] Portal maintenance ({resp.status_code}).")
                    return {"results": []}
                resp.raise_for_status()
                return resp.json()
            except requests.RequestException as exc:
                if attempt == self.max_retries:
                    raise CanadaLacIngestionError(f"LAC API unreachable: {exc}") from exc
                time.sleep(2 ** attempt)
        raise CanadaLacIngestionError("Canada LAC retry budget exhausted.")

    def fetch_records(self, max_pages: int = 2, page_size: int = 15) -> List[Dict[str, Any]]:
        ingested = []
        seen_ids: Set[str] = set()

        start_year, end_year = self.get_unified_date_window()
        logger.info(f"[CA_LAC] Applying Unified Historical Window: {start_year} to {end_year}")

        for page_idx in range(max_pages):
            params = {
                "q": "Cold War Intelligence Defense External Affairs",
                "startYear": start_year,
                "endYear": end_year,
                "page": str(page_idx + 1),
                "num": str(page_size)
            }

            try:
                payload = self._execute_with_retry(params)
                records = payload.get("results", []) or payload.get("data", [])

                if not records:
                    break

                for doc in records:
                    item_id = str(doc.get("id") or doc.get("mikanNumber", "")).strip()
                    if not item_id or item_id in seen_ids:
                        continue
                    seen_ids.add(item_id)

                    clean_title = self.clean_text(doc.get("title"))
                    rg_number = doc.get("recordGroup", "RG 25 (External Affairs)")
                    call_no = doc.get("referenceNumber", f"LAC-MIKAN-{item_id}")

                    record: Dict[str, Any] = {
                        "record_id": f"calac:{item_id.replace('/', '_').replace(' ', '')}",
                        "verification_level": "metadata_only",
                        "fixity": {"hash_algorithm": "NONE", "hash_value": None, "file_size_bytes": None},
                        "archival_context": {
                            "repository": {
                                "en": "Library and Archives Canada (Ottawa, Ontario)",
                                "zh": "加拿大圖書館與檔案館 (渥太華)"
                            },
                            "fonds": rg_number,
                            "series": doc.get("series", "Department of External Affairs & National Defence Series"),
                            "call_number": call_no,
                            "title": {
                                "en": clean_title,
                                "zh": None
                            },
                            "covering_dates": doc.get("dateDisplay", f"{start_year}-{end_year}")
                        },
                        "heuristic_clues": {
                            "phase_2_status": "STUB_ACTIVE"
                        },
                        "rights_statement": {
                            "license_category": "Canada_Crown_Copyright_Open_Government",
                            "reuse_permitted": True,
                            "legal_disclaimer": {
                                "en": "Contains information licensed under Open Government Licence – Canada.",
                                "zh": "依加拿大開放政府授權條款（OGL-Canada）公開之解密聯邦檔案。"
                            }
                        },
                        "provenance": {
                            "source_manifest_url": f"https://recherche-collection-search.bac-lac.gc.ca/eng/Home/Record?app=fonandcol&IdNumber={item_id}",
                            "retrieved_at_utc": datetime.now(timezone.utc).isoformat()
                        }
                    }
                    ingested.append(record)

                time.sleep(0.5)

            except Exception as e:
                logger.error(f"[CA_LAC] Batch isolated failure: {e}")
                break

        logger.info(f"[CA_LAC] Pipeline successfully acquired {len(ingested)} distinct records.")
        return ingested
