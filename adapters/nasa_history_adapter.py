"""
National Aeronautics and Space Administration (NASA History Division) Production Adapter
符合 BaseAdapter 統一時間窗口，採集美蘇太空競賽、軍民兩用飛彈技術、阿波羅計劃與冷戰航天外交解密公文。
"""
import re
import html
import time
import logging
import requests
from typing import List, Dict, Any, Optional, Set
from datetime import datetime, timezone
from adapters.base import BaseAdapter

logger = logging.getLogger("Veracity.Adapters.NASA")

class NasaHistoryIngestionError(Exception):
    pass

class NasaHistoryProductionAdapter(BaseAdapter):
    NAME = "US_NASA_HISTORY"
    # NASA 技術報告與歷史檔案檢索 API (NASA STI Repository REST API)
    API_URL = "https://ntrs.nasa.gov/api/citations/search"
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
            return "Untitled NASA Historical Space Document"
        stripped = re.sub(r"<[^>]+>", "", raw_text)
        unescaped = html.unescape(stripped)
        return " ".join(unescaped.split()).strip()

    def _execute_with_retry(self, params: Dict[str, Any]) -> Dict[str, Any]:
        for attempt in range(1, self.max_retries + 1):
            try:
                resp = self.session.get(self.API_URL, params=params, timeout=self.timeout)
                if resp.status_code == 429:
                    backoff = 2 ** attempt
                    logger.warning(f"[NASA] Rate limit (429). Retrying in {backoff}s...")
                    time.sleep(backoff)
                    continue
                if resp.status_code in (404, 502, 503):
                    logger.warning(f"[NASA] STI gateway maintenance ({resp.status_code}).")
                    return {"results": []}
                resp.raise_for_status()
                return resp.json()
            except requests.RequestException as exc:
                if attempt == self.max_retries:
                    raise NasaHistoryIngestionError(f"NASA STI API unreachable: {exc}") from exc
                time.sleep(2 ** attempt)
        raise NasaHistoryIngestionError("NASA STI retry budget exhausted.")

    def fetch_records(self, max_pages: int = 2, page_size: int = 15) -> List[Dict[str, Any]]:
        ingested = []
        seen_ids: Set[str] = set()

        start_year, end_year = self.get_unified_date_window()
        # NASA 成立於 1958 年（國家航空暨太空法）
        nasa_start = max(1958, int(start_year))
        logger.info(f"[NASA] Applying Historical Window: {nasa_start} to {end_year}")

        for page_idx in range(max_pages):
            params = {
                "q": "Cold War Space Race Ballistic Missile Defense Apollo Soviet Cooperation declassified",
                "published.gte": f"{nasa_start}-01-01",
                "published.lte": f"{end_year}-12-31",
                "page.size": str(page_size),
                "page.from": str(page_idx * page_size)
            }

            try:
                payload = self._execute_with_retry(params)
                records = payload.get("results", [])

                if not records:
                    break

                for doc in records:
                    doc_id = str(doc.get("id") or "").strip()
                    if not doc_id or doc_id in seen_ids:
                        continue
                    seen_ids.add(doc_id)

                    clean_title = self.clean_text(doc.get("title"))
                    source_center = doc.get("center", {}).get("name", "NASA Headquarters / History Division")
                    call_no = f"NASA-STI-{doc_id}"

                    record: Dict[str, Any] = {
                        "record_id": f"nasahist:{doc_id.replace('/', '_').replace(' ', '').replace(':', '_')}",
                        "verification_level": "metadata_only",
                        "fixity": {"hash_algorithm": "NONE", "hash_value": None, "file_size_bytes": None},
                        "archival_context": {
                            "repository": {
                                "en": "NASA History Division & Scientific and Technical Information (STI) Repository (Washington, D.C.)",
                                "zh": "美國國家航空暨太空總署歷史檔案處與科技資訊庫 (華盛頓特區)"
                            },
                            "fonds": f"NASA Historical Reference Collection ({source_center})",
                            "series": "美蘇太空競賽、軍民兩用飛彈技術與航天外交歷史系列",
                            "call_number": call_no,
                            "title": {
                                "en": clean_title,
                                "zh": None
                            },
                            "covering_dates": doc.get("publicationDate", f"{nasa_start}-{end_year}")
                        },
                        "heuristic_clues": {
                            "phase_2_status": "STUB_ACTIVE"
                        },
                        "rights_statement": {
                            "license_category": "US_Public_Domain_NASA_Historical",
                            "reuse_permitted": True,
                            "legal_disclaimer": {
                                "en": "NASA historical work of the United States Government. In the Public Domain worldwide under 17 U.S.C. 105.",
                                "zh": "依美國聯邦版權法第 105 條，NASA 官方歷史公文屬全球公有領域。"
                            }
                        },
                        "provenance": {
                            "source_manifest_url": f"https://ntrs.nasa.gov/citations/{doc_id}",
                            "retrieved_at_utc": datetime.now(timezone.utc).isoformat()
                        }
                    }
                    ingested.append(record)

                time.sleep(0.5)

            except Exception as e:
                logger.error(f"[NASA] Batch isolated failure: {e}")
                break

        logger.info(f"[NASA] Pipeline successfully acquired {len(ingested)} distinct records.")
        return ingested
