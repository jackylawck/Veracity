"""
Woodrow Wilson International Center for Scholars (CWIHP) Production Adapter
符合 BaseAdapter 統一時間窗口，採集前蘇聯、東歐華約及中國冷戰多邊解密公文檔案。
"""
import re
import html
import time
import logging
import requests
from typing import List, Dict, Any, Optional, Set
from datetime import datetime, timezone
from adapters.base import BaseAdapter

logger = logging.getLogger("Veracity.Adapters.WilsonCWIHP")

class WilsonCwihpIngestionError(Exception):
    pass

class WilsonCwihpProductionAdapter(BaseAdapter):
    NAME = "GLOBAL_CWIHP"
    # Wilson Center Digital Archive REST API
    API_URL = "https://digitalarchive.wilsoncenter.org/api/v1/records"
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
            return "Untitled Cold War Declassified Intelligence Record"
        stripped = re.sub(r"<[^>]+>", "", raw_text)
        unescaped = html.unescape(stripped)
        return " ".join(unescaped.split()).strip()

    def _execute_with_retry(self, params: Dict[str, Any]) -> Dict[str, Any]:
        for attempt in range(1, self.max_retries + 1):
            try:
                resp = self.session.get(self.API_URL, params=params, timeout=self.timeout)
                if resp.status_code == 429:
                    backoff = 2 ** attempt
                    logger.warning(f"[CWIHP] Rate limited (429). Retrying in {backoff}s...")
                    time.sleep(backoff)
                    continue
                if resp.status_code in (404, 502, 503):
                    logger.warning(f"[CWIHP] Archive endpoint temporarily offline ({resp.status_code}).")
                    return {"data": []}
                resp.raise_for_status()
                return resp.json()
            except requests.RequestException as exc:
                if attempt == self.max_retries:
                    raise WilsonCwihpIngestionError(f"CWIHP API unreachable: {exc}") from exc
                time.sleep(2 ** attempt)
        raise WilsonCwihpIngestionError("CWIHP retry budget exhausted.")

    def fetch_records(self, max_pages: int = 2, page_size: int = 15) -> List[Dict[str, Any]]:
        ingested = []
        seen_ids: Set[str] = set()

        start_year, end_year = self.get_unified_date_window()
        logger.info(f"[CWIHP] Applying Unified Historical Window: {start_year} to {end_year}")

        for page_idx in range(max_pages):
            params = {
                "filter[keyword]": "Soviet Chinese Nuclear Intelligence Cold War",
                "filter[start_date]": f"{start_year}-01-01",
                "filter[end_date]": f"{end_year}-12-31",
                "page[number]": str(page_idx + 1),
                "page[size]": str(page_size)
            }

            try:
                payload = self._execute_with_retry(params)
                records = payload.get("data", []) or payload.get("records", [])

                if not records:
                    break

                for doc in records:
                    doc_id = str(doc.get("id") or doc.get("identifier", "")).strip()
                    if not doc_id or doc_id in seen_ids:
                        continue
                    seen_ids.add(doc_id)

                    attributes = doc.get("attributes", doc)
                    title_clean = self.clean_text(attributes.get("title"))
                    
                    # 原始保存檔案庫（例如：RGANI、TsKhSD 俄羅斯國家當代史檔案館）
                    origin_archive = attributes.get("original_archive", "Former Soviet/Eastern Bloc State Archives")
                    collection_name = attributes.get("collection_name", "Cold War International History Project (CWIHP)")
                    doc_date = attributes.get("date", f"{start_year}-{end_year}")

                    record: Dict[str, Any] = {
                        "record_id": f"cwihp:{doc_id}",
                        "verification_level": "metadata_only",
                        "fixity": {"hash_algorithm": "NONE", "hash_value": None, "file_size_bytes": None},
                        "archival_context": {
                            "repository": {
                                "en": "Wilson Center Digital Archive / CWIHP (Washington, D.C.)",
                                "zh": "威爾遜中心冷戰國際史檔案庫 (華盛頓)"
                            },
                            "fonds": origin_archive,
                            "series": collection_name,
                            "call_number": f"CWIHP-DOC-{doc_id}",
                            "title": {
                                "en": title_clean,
                                "zh": None
                            },
                            "covering_dates": doc_date
                        },
                        "heuristic_clues": {
                            "phase_2_status": "STUB_ACTIVE"
                        },
                        "rights_statement": {
                            "license_category": "Educational_Academic_Fair_Use",
                            "reuse_permitted": True,
                            "legal_disclaimer": {
                                "en": "Declassified primary documents curated for non-commercial scholarly research and historical education.",
                                "zh": "依學術公平使用原則收錄之前東歐與中蘇解密史料，供非營利歷史法證核驗。"
                            }
                        },
                        "provenance": {
                            "source_manifest_url": f"https://digitalarchive.wilsoncenter.org/document/{doc_id}",
                            "retrieved_at_utc": datetime.now(timezone.utc).isoformat()
                        }
                    }
                    ingested.append(record)

                time.sleep(0.5)

            except Exception as e:
                logger.error(f"[CWIHP] Batch isolated failure: {e}")
                break

        logger.info(f"[CWIHP] Pipeline successfully acquired {len(ingested)} distinct records.")
        return ingested
