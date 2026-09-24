"""
Archives New Zealand (Te Rua Mahara o te Kāwanatanga) Production Adapter
符合 BaseAdapter 統一時間窗口，採集五眼聯盟情報、ANZUS 條約與南太平洋冷戰防衛解密檔案。
"""
import re
import html
import time
import logging
import requests
from typing import List, Dict, Any, Optional, Set
from datetime import datetime, timezone
from adapters.base import BaseAdapter

logger = logging.getLogger("Veracity.Adapters.ANZ")

class AnzIngestionError(Exception):
    pass

class NewZealandAnzProductionAdapter(BaseAdapter):
    NAME = "NZ_ANZ"
    # 紐西蘭國家檔案館公開 API (Collections Search REST 端點)
    API_URL = "https://collections.archives.govt.nz/api/v1/records/search"
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
            return "Untitled New Zealand Crown Archival Record"
        stripped = re.sub(r"<[^>]+>", "", raw_text)
        unescaped = html.unescape(stripped)
        return " ".join(unescaped.split()).strip()

    def _execute_with_retry(self, params: Dict[str, Any]) -> Dict[str, Any]:
        for attempt in range(1, self.max_retries + 1):
            try:
                resp = self.session.get(self.API_URL, params=params, timeout=self.timeout)
                if resp.status_code == 429:
                    backoff = 2 ** attempt
                    logger.warning(f"[ANZ] Rate limit (429). Retrying in {backoff}s...")
                    time.sleep(backoff)
                    continue
                if resp.status_code in (404, 502, 503):
                    logger.warning(f"[ANZ] Collections gateway offline ({resp.status_code}).")
                    return {"records": []}
                resp.raise_for_status()
                return resp.json()
            except requests.RequestException as exc:
                if attempt == self.max_retries:
                    raise AnzIngestionError(f"ANZ API unreachable: {exc}") from exc
                time.sleep(2 ** attempt)
        raise AnzIngestionError("ANZ retry budget exhausted.")

    def fetch_records(self, max_pages: int = 2, page_size: int = 15) -> List[Dict[str, Any]]:
        ingested = []
        seen_ids: Set[str] = set()

        start_year, end_year = self.get_unified_date_window()
        logger.info(f"[ANZ] Applying Unified Historical Window: {start_year} to {end_year}")

        for page_idx in range(max_pages):
            params = {
                "q": "Foreign Affairs Intelligence Defence Security Cold War",
                "startYear": start_year,
                "endYear": end_year,
                "page": str(page_idx + 1),
                "pageSize": str(page_size)
            }

            try:
                payload = self._execute_with_retry(params)
                records = payload.get("records", []) or payload.get("data", [])

                if not records:
                    break

                for doc in records:
                    record_id = str(doc.get("id") or doc.get("recordCode", "")).strip()
                    if not record_id or record_id in seen_ids:
                        continue
                    seen_ids.add(record_id)

                    clean_title = self.clean_text(doc.get("title"))
                    fonds_name = doc.get("agency", "Ministry of Foreign Affairs and Trade / NZSIS")
                    call_no = doc.get("referenceNumber", f"ANZ-R-{record_id}")

                    record: Dict[str, Any] = {
                        "record_id": f"nzanz:{record_id.replace('/', '_').replace(' ', '')}",
                        "verification_level": "metadata_only",
                        "fixity": {"hash_algorithm": "NONE", "hash_value": None, "file_size_bytes": None},
                        "archival_context": {
                            "repository": {
                                "en": "Archives New Zealand (Wellington)",
                                "zh": "紐西蘭國家檔案館 (威靈頓)"
                            },
                            "fonds": fonds_name,
                            "series": doc.get("series", "External Intelligence & Defence Treaties"),
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
                            "license_category": "NZ_Crown_Copyright_Open_Data",
                            "reuse_permitted": True,
                            "legal_disclaimer": {
                                "en": "Declassified public records subject to New Zealand Crown Copyright, available for public research.",
                                "zh": "依紐西蘭公共檔案法解密開放之皇家版權歷史檔案。"
                            }
                        },
                        "provenance": {
                            "source_manifest_url": f"https://collections.archives.govt.nz/en/web/arena/search#/entity/aims-archive/{record_id}",
                            "retrieved_at_utc": datetime.now(timezone.utc).isoformat()
                        }
                    }
                    ingested.append(record)

                time.sleep(0.5)

            except Exception as e:
                logger.error(f"[ANZ] Batch isolated failure: {e}")
                break

        logger.info(f"[ANZ] Pipeline successfully acquired {len(ingested)} distinct records.")
        return ingested
