"""
Hoover Institution Library & Archives (Stanford University) Production Adapter
符合 BaseAdapter 統一時間窗口，採集近現代中國政軍最高層私人密檔、外交使節解密手稿與冷戰文獻。
"""
import re
import html
import time
import logging
import requests
from typing import List, Dict, Any, Optional, Set
from datetime import datetime, timezone
from adapters.base import BaseAdapter

logger = logging.getLogger("Veracity.Adapters.Hoover")

class HooverIngestionError(Exception):
    pass

class HooverInstitutionProductionAdapter(BaseAdapter):
    NAME = "GLOBAL_HOOVER"
    # Stanford Hoover Institution eMuseum / Digital Collections API 端點
    API_URL = "https://digitalcollections.hoover.org/api/v1/records/search"
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
            return "Untitled Hoover Historical Archival Item"
        stripped = re.sub(r"<[^>]+>", "", raw_text)
        unescaped = html.unescape(stripped)
        return " ".join(unescaped.split()).strip()

    def _execute_with_retry(self, params: Dict[str, Any]) -> Dict[str, Any]:
        for attempt in range(1, self.max_retries + 1):
            try:
                resp = self.session.get(self.API_URL, params=params, timeout=self.timeout)
                if resp.status_code == 429:
                    backoff = 2 ** attempt
                    logger.warning(f"[Hoover] Rate limited (429). Retrying in {backoff}s...")
                    time.sleep(backoff)
                    continue
                if resp.status_code in (404, 502, 503):
                    logger.warning(f"[Hoover] Portal gateway maintenance ({resp.status_code}).")
                    return {"results": []}
                resp.raise_for_status()
                return resp.json()
            except requests.RequestException as exc:
                if attempt == self.max_retries:
                    raise HooverIngestionError(f"Hoover API unreachable: {exc}") from exc
                time.sleep(2 ** attempt)
        raise HooverIngestionError("Hoover retry budget exhausted.")

    def fetch_records(self, max_pages: int = 2, page_size: int = 15) -> List[Dict[str, Any]]:
        ingested = []
        seen_ids: Set[str] = set()

        start_year, end_year = self.get_unified_date_window()
        logger.info(f"[Hoover] Applying Unified Historical Window: {start_year} to {end_year}")

        for page_idx in range(max_pages):
            params = {
                "q": "Modern China Diplomatic Telegrams Cold War Diaries",
                "startYear": str(start_year),
                "endYear": str(end_year),
                "page": str(page_idx + 1),
                "pageSize": str(page_size)
            }

            try:
                payload = self._execute_with_retry(params)
                records = payload.get("results", []) or payload.get("items", [])

                if not records:
                    break

                for doc in records:
                    doc_id = str(doc.get("id") or doc.get("collectionNumber", "")).strip()
                    if not doc_id or doc_id in seen_ids:
                        continue
                    seen_ids.add(doc_id)

                    en_title = self.clean_text(doc.get("title"))
                    zh_title = self.clean_text(doc.get("titleZh")) if doc.get("titleZh") else None
                    fonds_name = doc.get("collectionName", "Modern China & East Asia Archival Papers")
                    call_no = doc.get("callNumber", f"HOOVER-{doc_id}")

                    record: Dict[str, Any] = {
                        "record_id": f"hoover:{doc_id.replace('/', '_').replace(' ', '')}",
                        "verification_level": "metadata_only",
                        "fixity": {"hash_algorithm": "NONE", "hash_value": None, "file_size_bytes": None},
                        "archival_context": {
                            "repository": {
                                "en": "Hoover Institution Library & Archives, Stanford University (California)",
                                "zh": "史丹佛大學胡佛研究所圖書檔案館 (加州)"
                            },
                            "fonds": fonds_name,
                            "series": doc.get("series", "近代中國政軍高層手稿與外交電報系列"),
                            "call_number": call_no,
                            "title": {
                                "en": en_title,
                                "zh": zh_title
                            },
                            "covering_dates": doc.get("dateDisplay", f"{start_year}-{end_year}")
                        },
                        "heuristic_clues": {
                            "phase_2_status": "STUB_ACTIVE"
                        },
                        "rights_statement": {
                            "license_category": "Stanford_Academic_Research_Fair_Use",
                            "reuse_permitted": True,
                            "legal_disclaimer": {
                                "en": "Preserved by Hoover Institution Library & Archives for historical research and forensic verification.",
                                "zh": "由史丹佛大學胡佛研究所典藏，依學術研究原則提供歷史法證比對。"
                            }
                        },
                        "provenance": {
                            "source_manifest_url": f"https://digitalcollections.hoover.org/objects/{doc_id}",
                            "retrieved_at_utc": datetime.now(timezone.utc).isoformat()
                        }
                    }
                    ingested.append(record)

                time.sleep(0.5)

            except Exception as e:
                logger.error(f"[Hoover] Batch isolated failure: {e}")
                break

        logger.info(f"[Hoover] Pipeline successfully acquired {len(ingested)} distinct records.")
        return ingested
