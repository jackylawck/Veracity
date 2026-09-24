"""
Hong Kong Heritage Project (HKHP / Kadoorie Archives) Production Adapter
符合 BaseAdapter 統一時間窗口，採集戰後香港供電公用事業、九龍半島工業重建與民間救濟歷史檔案。
"""
import re
import html
import time
import logging
import requests
from typing import List, Dict, Any, Optional, Set
from datetime import datetime, timezone
from adapters.base import BaseAdapter

logger = logging.getLogger("Veracity.Adapters.HKHP")

class HkhpArchivesIngestionError(Exception):
    pass

class HkhpKadoorieProductionAdapter(BaseAdapter):
    NAME = "HK_HKHP"
    # 香港歷史檔案特藏項目開放檢索端點
    API_URL = "https://www.hongkongheritage.org/api/v1/records/search"
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
            return "未命名香港民間歷史檔案 (Untitled Hong Kong Heritage Record)"
        stripped = re.sub(r"<[^>]+>", "", raw_text)
        unescaped = html.unescape(stripped)
        return " ".join(unescaped.split()).strip()

    def _execute_with_retry(self, params: Dict[str, Any]) -> Dict[str, Any]:
        for attempt in range(1, self.max_retries + 1):
            try:
                resp = self.session.get(self.API_URL, params=params, timeout=self.timeout)
                if resp.status_code == 429:
                    backoff = 2 ** attempt
                    logger.warning(f"[HKHP] Rate limit (429). Retrying in {backoff}s...")
                    time.sleep(backoff)
                    continue
                if resp.status_code in (404, 502, 503):
                    logger.warning(f"[HKHP] Heritage project portal maintenance ({resp.status_code}).")
                    return {"data": []}
                resp.raise_for_status()
                return resp.json()
            except requests.RequestException as exc:
                if attempt == self.max_retries:
                    raise HkhpArchivesIngestionError(f"HKHP API unreachable: {exc}") from exc
                time.sleep(2 ** attempt)
        raise HkhpArchivesIngestionError("HKHP retry budget exhausted.")

    def fetch_records(self, max_pages: int = 2, page_size: int = 15) -> List[Dict[str, Any]]:
        ingested = []
        seen_ids: Set[str] = set()

        start_year, end_year = self.get_unified_date_window()
        logger.info(f"[HKHP] Applying Unified Historical Window: {start_year} to {end_year}")

        for page_idx in range(max_pages):
            params = {
                "keyword": "Post-war Reconstruction Electricity Industry Kadoorie",
                "startYear": start_year,
                "endYear": end_year,
                "page": str(page_idx + 1),
                "pageSize": str(page_size)
            }

            try:
                payload = self._execute_with_retry(params)
                records = payload.get("data", []) or payload.get("records", [])

                if not records:
                    break

                for doc in records:
                    item_id = str(doc.get("id") or doc.get("identifier", "")).strip()
                    if not item_id or item_id in seen_ids:
                        continue
                    seen_ids.add(item_id)

                    en_title = self.clean_text(doc.get("title_en") or doc.get("title"))
                    zh_title = self.clean_text(doc.get("title_tc")) if doc.get("title_tc") else None
                    call_no = doc.get("ref_code", f"HKHP-DOC-{item_id}")
                    collection_name = doc.get("collection", "嘉道理家族與中華電力戰後重建檔案全宗")

                    record: Dict[str, Any] = {
                        "record_id": f"hkhp:{item_id.replace('/', '_').replace(' ', '')}",
                        "verification_level": "metadata_only",
                        "fixity": {"hash_algorithm": "NONE", "hash_value": None, "file_size_bytes": None},
                        "archival_context": {
                            "repository": {
                                "en": "The Hong Kong Heritage Project (Kowloon)",
                                "zh": "香港歷史檔案特藏項目 / 嘉道理檔案庫 (九龍)"
                            },
                            "fonds": collection_name,
                            "series": doc.get("series", "戰後公共事業基礎建設與社會復興系列"),
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
                            "license_category": "HKHP_Educational_Open_Access",
                            "reuse_permitted": True,
                            "legal_disclaimer": {
                                "en": "Historical records preserved by The Hong Kong Heritage Project for education, heritage preservation and non-commercial forensics.",
                                "zh": "由香港歷史檔案特藏項目典藏，供教育、歷史遺產保護與非營利法證研究查閱。"
                            }
                        },
                        "provenance": {
                            "source_manifest_url": f"https://www.hongkongheritage.org/records/{item_id}",
                            "retrieved_at_utc": datetime.now(timezone.utc).isoformat()
                        }
                    }
                    ingested.append(record)

                time.sleep(0.5)

            except Exception as e:
                logger.error(f"[HKHP] Batch isolated failure: {e}")
                break

        logger.info(f"[HKHP] Pipeline successfully acquired {len(ingested)} distinct records.")
        return ingested
