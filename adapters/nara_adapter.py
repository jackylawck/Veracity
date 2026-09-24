"""
US National Archives and Records Administration (NARA) Production Adapter
符合 BaseAdapter 統一時間窗口，採集美國主權歷史解密公文（National Archives Catalog API）。
"""
import re
import html
import time
import logging
import requests
from typing import List, Dict, Any, Optional, Set
from datetime import datetime, timezone
from adapters.base import BaseAdapter

logger = logging.getLogger("Veracity.Adapters.NARA")

class NaraIngestionError(Exception):
    pass

class NaraProductionAdapter(BaseAdapter):
    NAME = "US_NARA"
    # NARA 官方公開 API 端點
    API_URL = "https://catalog.archives.gov/api/v2/records/search"
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
            return "Untitled Declassified National Record"
        stripped = re.sub(r"<[^>]+>", "", raw_text)
        unescaped = html.unescape(stripped)
        return " ".join(unescaped.split()).strip()

    def _execute_with_retry(self, params: Dict[str, Any]) -> Dict[str, Any]:
        for attempt in range(1, self.max_retries + 1):
            try:
                resp = self.session.get(self.API_URL, params=params, timeout=self.timeout)
                if resp.status_code == 429:
                    backoff = 2 ** attempt
                    logger.warning(f"[NARA] Rate limit encountered (429). Backing off {backoff}s...")
                    time.sleep(backoff)
                    continue
                if not resp.ok:
                    logger.error(f"[NARA] API responded with error {resp.status_code}: {resp.text}")
                resp.raise_for_status()
                return resp.json()
            except requests.RequestException as exc:
                if attempt == self.max_retries:
                    raise NaraIngestionError(f"NARA Catalog API unreachable: {exc}") from exc
                time.sleep(2 ** attempt)
        raise NaraIngestionError("NARA retry budget exhausted.")

    def fetch_records(self, max_pages: int = 2, page_size: int = 15) -> List[Dict[str, Any]]:
        ingested = []
        seen_ids: Set[str] = set()

        start_year, end_year = self.get_unified_date_window()
        logger.info(f"[NARA] Applying Unified Historical Window: {start_year} to {end_year}")

        for page_idx in range(max_pages):
            params = {
                "q": "Foreign Relations Cold War declassified",
                "record_types": "item",
                "start_date": f"{start_year}-01-01",
                "end_date": f"{end_year}-12-31",
                "limit": str(page_size),
                "offset": str(page_idx * page_size)
            }

            try:
                payload = self._execute_with_retry(params)
                # NARA API v2 標準回傳結構
                body_data = payload.get("body", {})
                hits = body_data.get("hits", {}).get("hits", [])

                if not hits:
                    logger.info(f"[NARA] Page {page_idx + 1} yielded 0 hits. Halting.")
                    break

                for hit in hits:
                    source = hit.get("_source", {})
                    na_id = str(source.get("naId", "")).strip()
                    if not na_id or na_id in seen_ids:
                        continue
                    seen_ids.add(na_id)

                    metadata = source.get("record", {})
                    clean_title = self.clean_text(metadata.get("title"))
                    
                    # 檔案全宗 (Record Group) 解析
                    record_group = "RG Unknown"
                    if "recordGroup" in metadata and isinstance(metadata["recordGroup"], list):
                        record_group = metadata["recordGroup"][0].get("recordGroupNumber", "RG")

                    dates = metadata.get("coverageDates", {})
                    covering_dates = dates.get("dateDisplay", f"{start_year}-{end_year}")

                    record: Dict[str, Any] = {
                        "record_id": f"nara:{na_id}",
                        "verification_level": "metadata_only",
                        "fixity": {"hash_algorithm": "NONE", "hash_value": None, "file_size_bytes": None},
                        "archival_context": {
                            "repository": {
                                "en": "US National Archives at College Park (NARA II)",
                                "zh": "美國國家檔案和記錄管理局 (NARA)"
                            },
                            "fonds": record_group,
                            "series": metadata.get("series", "General Foreign Affairs Series"),
                            "call_number": f"NARA-NAID-{na_id}",
                            "title": {
                                "en": clean_title,
                                "zh": None
                            },
                            "covering_dates": covering_dates
                        },
                        "heuristic_clues": {
                            "phase_2_status": "STUB_ACTIVE"
                        },
                        "rights_statement": {
                            "license_category": "US_Public_Domain",
                            "reuse_permitted": True,
                            "legal_disclaimer": {
                                "en": "Work of the US Federal Government under 17 U.S.C. 105. In Public Domain worldwide.",
                                "zh": "依美國版權法第 105 條，屬美國聯邦政府公有領域史料。"
                            }
                        },
                        "provenance": {
                            "source_manifest_url": f"https://catalog.archives.gov/id/{na_id}",
                            "retrieved_at_utc": datetime.now(timezone.utc).isoformat()
                        }
                    }
                    ingested.append(record)

                time.sleep(0.5)

            except Exception as e:
                logger.error(f"[NARA] Page {page_idx + 1} processing error: {e}")
                break

        logger.info(f"[NARA] Pipeline successfully acquired {len(ingested)} distinct records.")
        return ingested
