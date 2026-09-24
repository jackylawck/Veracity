"""
Arolsen Archives (International Center on Nazi Persecution / ITS) Production Adapter
符合 BaseAdapter 統一時間窗口，採集戰後盟軍軍政府難民營 (DP Camps)、人口遣返與國際尋人局法證檔案。
"""
import re
import html
import time
import logging
import requests
from typing import List, Dict, Any, Optional, Set
from datetime import datetime, timezone
from adapters.base import BaseAdapter

logger = logging.getLogger("Veracity.Adapters.Arolsen")

class ArolsenArchivesIngestionError(Exception):
    pass

class ArolsenArchivesProductionAdapter(BaseAdapter):
    NAME = "GLOBAL_AROLSEN"
    # 阿羅爾森檔案館線上檢索 REST API
    API_URL = "https://collections.arolsen-archives.org/api/v1/search"
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
            return "Untitled Displaced Persons Archival Record"
        stripped = re.sub(r"<[^>]+>", "", raw_text)
        unescaped = html.unescape(stripped)
        return " ".join(unescaped.split()).strip()

    def _execute_with_retry(self, params: Dict[str, Any]) -> Dict[str, Any]:
        for attempt in range(1, self.max_retries + 1):
            try:
                resp = self.session.get(self.API_URL, params=params, timeout=self.timeout)
                if resp.status_code == 429:
                    backoff = 2 ** attempt
                    logger.warning(f"[Arolsen] Rate limited (429). Retrying in {backoff}s...")
                    time.sleep(backoff)
                    continue
                if resp.status_code in (404, 502, 503):
                    logger.warning(f"[Arolsen] Collections API offline ({resp.status_code}).")
                    return {"results": []}
                resp.raise_for_status()
                return resp.json()
            except requests.RequestException as exc:
                if attempt == self.max_retries:
                    raise ArolsenArchivesIngestionError(f"Arolsen Archives API unreachable: {exc}") from exc
                time.sleep(2 ** attempt)
        raise ArolsenArchivesIngestionError("Arolsen retry budget exhausted.")

    def fetch_records(self, max_pages: int = 2, page_size: int = 15) -> List[Dict[str, Any]]:
        ingested = []
        seen_ids: Set[str] = set()

        start_year, end_year = self.get_unified_date_window()
        logger.info(f"[Arolsen] Applying Historical Window: {start_year} to {end_year}")

        for page_idx in range(max_pages):
            params = {
                "q": "Displaced Persons DP Camp Allied Military Government Post-War Repatriation",
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
                    doc_id = str(doc.get("id") or doc.get("signatur", "")).strip()
                    if not doc_id or doc_id in seen_ids:
                        continue
                    seen_ids.add(doc_id)

                    clean_title = self.clean_text(doc.get("title") or doc.get("name"))
                    sub_fonds = doc.get("subCollection", "Allied Post-War Central Tracing Records")
                    call_no = doc.get("signatur", f"ITS-{doc_id}")

                    record: Dict[str, Any] = {
                        "record_id": f"arolsen:{doc_id.replace('/', '_').replace(' ', '').replace(':', '_')}",
                        "verification_level": "metadata_only",
                        "fixity": {"hash_algorithm": "NONE", "hash_value": None, "file_size_bytes": None},
                        "archival_context": {
                            "repository": {
                                "en": "Arolsen Archives - International Center on Nazi Persecution (Bad Arolsen, Germany)",
                                "zh": "阿羅爾森檔案館 / 國際尋人局 (德國巴特阿羅爾森)"
                            },
                            "fonds": "International Tracing Service (ITS) Central Archives",
                            "series": f"戰後盟軍軍政府難民管理與跨國遣返檔案 ({sub_fonds})",
                            "call_number": call_no,
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
                            "license_category": "UNESCO_Memory_of_the_World_Public_Access",
                            "reuse_permitted": True,
                            "legal_disclaimer": {
                                "en": "Part of the UNESCO Memory of the World Register. Preserved for universal public inquiry and legal historical evidence.",
                                "zh": "列入聯合國教科文組織《世界記憶名錄》之國際公有歷史檔案，供全球人權法證與查核。"
                            }
                        },
                        "provenance": {
                            "source_manifest_url": f"https://collections.arolsen-archives.org/en/archive/{doc_id}",
                            "retrieved_at_utc": datetime.now(timezone.utc).isoformat()
                        }
                    }
                    ingested.append(record)

                time.sleep(0.5)

            except Exception as e:
                logger.error(f"[Arolsen] Batch isolated failure: {e}")
                break

        logger.info(f"[Arolsen] Pipeline successfully acquired {len(ingested)} distinct records.")
        return ingested
