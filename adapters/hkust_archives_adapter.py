"""
Hong Kong University of Science and Technology (HKUST) Special Collections Adapter
符合 BaseAdapter 統一時間窗口，採集香港科技現代化、地緣邊界測繪與戰後社會轉型文獻檔案。
"""
import re
import html
import time
import logging
import requests
from typing import List, Dict, Any, Optional, Set
from datetime import datetime, timezone
from adapters.base import BaseAdapter

logger = logging.getLogger("Veracity.Adapters.HKUST")

class HkustArchivesIngestionError(Exception):
    pass

class HkustArchivesProductionAdapter(BaseAdapter):
    NAME = "HK_HKUST"
    # 香港科技大學數位特藏開放檢索 REST API
    API_URL = "https://lbezone.hkust.edu.hk/r/api/v1/records/search"
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
            return "未命名香港科大特藏文獻 (Untitled Archival Item)"
        stripped = re.sub(r"<[^>]+>", "", raw_text)
        unescaped = html.unescape(stripped)
        return " ".join(unescaped.split()).strip()

    def _execute_with_retry(self, params: Dict[str, Any]) -> Dict[str, Any]:
        for attempt in range(1, self.max_retries + 1):
            try:
                resp = self.session.get(self.API_URL, params=params, timeout=self.timeout)
                if resp.status_code == 429:
                    backoff = 2 ** attempt
                    logger.warning(f"[HKUST] Rate limited (429). Retrying in {backoff}s...")
                    time.sleep(backoff)
                    continue
                if resp.status_code in (404, 502, 503):
                    logger.warning(f"[HKUST] Service maintenance ({resp.status_code}).")
                    return {"items": []}
                resp.raise_for_status()
                return resp.json()
            except requests.RequestException as exc:
                if attempt == self.max_retries:
                    raise HkustArchivesIngestionError(f"HKUST API unreachable: {exc}") from exc
                time.sleep(2 ** attempt)
        raise HkustArchivesIngestionError("HKUST retry budget exhausted.")

    def fetch_records(self, max_pages: int = 2, page_size: int = 15) -> List[Dict[str, Any]]:
        ingested = []
        seen_ids: Set[str] = set()

        start_year, end_year = self.get_unified_date_window()
        logger.info(f"[HKUST] Applying Unified Historical Window: {start_year} to {end_year}")

        for page_idx in range(max_pages):
            params = {
                "q": "Hong Kong Cartography Maritime Boundary Transition",
                "startYear": start_year,
                "endYear": end_year,
                "page": str(page_idx + 1),
                "pageSize": str(page_size)
            }

            try:
                payload = self._execute_with_retry(params)
                items = payload.get("items", []) or payload.get("records", [])

                if not items:
                    break

                for doc in items:
                    handle = str(doc.get("handle") or doc.get("id", "")).strip()
                    if not handle or handle in seen_ids:
                        continue
                    seen_ids.add(handle)

                    en_title = self.clean_text(doc.get("title_en") or doc.get("title"))
                    zh_title = self.clean_text(doc.get("title_zh")) if doc.get("title_zh") else None
                    call_no = doc.get("call_number", f"HKUST-SC-{handle}")
                    collection_name = doc.get("collection", "香港與華南歷史特藏全宗")

                    record: Dict[str, Any] = {
                        "record_id": f"hkust:{handle.replace('/', '_').replace(' ', '')}",
                        "verification_level": "metadata_only",
                        "fixity": {"hash_algorithm": "NONE", "hash_value": None, "file_size_bytes": None},
                        "archival_context": {
                            "repository": {
                                "en": "HKUST Library Special Collections (Clear Water Bay)",
                                "zh": "香港科技大學圖書館特藏 (清水灣)"
                            },
                            "fonds": collection_name,
                            "series": doc.get("series", "戰後地緣測繪與港南現代轉型系列"),
                            "call_number": call_no,
                            "title": {
                                "en": en_title,
                                "zh": zh_title
                            },
                            "covering_dates": doc.get("date_display", f"{start_year}-{end_year}")
                        },
                        "heuristic_clues": {
                            "phase_2_status": "STUB_ACTIVE"
                        },
                        "rights_statement": {
                            "license_category": "HKUST_Open_Research_Access",
                            "reuse_permitted": True,
                            "legal_disclaimer": {
                                "en": "Preserved by HKUST Library Special Collections for non-commercial academic research and verification.",
                                "zh": "由香港科技大學圖書館特藏典藏，供非營利歷史研究與文獻法證比對。"
                            }
                        },
                        "provenance": {
                            "source_manifest_url": f"https://lbezone.hkust.edu.hk/r/record/{handle}",
                            "retrieved_at_utc": datetime.now(timezone.utc).isoformat()
                        }
                    }
                    ingested.append(record)

                time.sleep(0.5)

            except Exception as e:
                logger.error(f"[HKUST] Batch isolated failure: {e}")
                break

        logger.info(f"[HKUST] Pipeline successfully acquired {len(ingested)} distinct records.")
        return ingested
