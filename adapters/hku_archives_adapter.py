"""
Hong Kong University Special Collections (HKU Archives) Production Adapter
符合 BaseAdapter 統一時間窗口，採集香港本地戰後防衛、地緣社會與民間公文典藏。
"""
import re
import html
import time
import logging
import requests
from typing import List, Dict, Any, Optional, Set
from datetime import datetime, timezone
from adapters.base import BaseAdapter

logger = logging.getLogger("Veracity.Adapters.HKU")

class HkuArchivesIngestionError(Exception):
    pass

class HkuArchivesProductionAdapter(BaseAdapter):
    NAME = "HK_HKU"
    # 香港大學數位典藏庫公開 OAI-PMH / REST 檢索端點
    API_URL = "https://digitalrepository.lib.hku.hk/api/v1/records/search"
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
            return "Untitled Hong Kong Archival Document"
        stripped = re.sub(r"<[^>]+>", "", raw_text)
        unescaped = html.unescape(stripped)
        return " ".join(unescaped.split()).strip()

    def _execute_with_retry(self, params: Dict[str, Any]) -> Dict[str, Any]:
        for attempt in range(1, self.max_retries + 1):
            try:
                resp = self.session.get(self.API_URL, params=params, timeout=self.timeout)
                if resp.status_code == 429:
                    backoff = 2 ** attempt
                    logger.warning(f"[HKU] Rate limited (429). Retrying in {backoff}s...")
                    time.sleep(backoff)
                    continue
                if resp.status_code in (404, 502, 503):
                    logger.warning(f"[HKU] Digital repository maintenance window ({resp.status_code}).")
                    return {"records": []}
                resp.raise_for_status()
                return resp.json()
            except requests.RequestException as exc:
                if attempt == self.max_retries:
                    raise HkuArchivesIngestionError(f"HKU Archives API unreachable: {exc}") from exc
                time.sleep(2 ** attempt)
        raise HkuArchivesIngestionError("HKU retry budget exhausted.")

    def fetch_records(self, max_pages: int = 2, page_size: int = 15) -> List[Dict[str, Any]]:
        ingested = []
        seen_handles: Set[str] = set()

        start_year, end_year = self.get_unified_date_window()
        logger.info(f"[HKU] Applying Unified Historical Window: {start_year} to {end_year}")

        for page_idx in range(max_pages):
            params = {
                "q": "Hong Kong Post-War Defense Administration Treaty",
                "startYear": start_year,
                "endYear": end_year,
                "page": str(page_idx + 1),
                "pageSize": str(page_size)
            }

            try:
                payload = self._execute_with_retry(params)
                items = payload.get("records", []) or payload.get("items", [])

                if not items:
                    break

                for item in items:
                    handle_id = str(item.get("id") or item.get("handle", "")).strip()
                    if not handle_id or handle_id in seen_handles:
                        continue
                    seen_handles.add(handle_id)

                    en_title = self.clean_text(item.get("title"))
                    zh_title = self.clean_text(item.get("title_zh")) if item.get("title_zh") else None
                    call_no = item.get("call_number", f"HKU-MS-{handle_id}")
                    fonds_name = item.get("collection_title", "Hong Kong Collection (Special Collections)")

                    record: Dict[str, Any] = {
                        "record_id": f"hku:{handle_id.replace('/', '_').replace(' ', '')}",
                        "verification_level": "metadata_only",
                        "fixity": {"hash_algorithm": "NONE", "hash_value": None, "file_size_bytes": None},
                        "archival_context": {
                            "repository": {
                                "en": "University of Hong Kong Libraries Special Collections (Pokfulam)",
                                "zh": "香港大學圖書館特藏部 (薄扶林)"
                            },
                            "fonds": fonds_name,
                            "series": item.get("series", "Hong Kong Local & Defense History Series"),
                            "call_number": call_no,
                            "title": {
                                "en": en_title,
                                "zh": zh_title
                            },
                            "covering_dates": item.get("date_range", f"{start_year}-{end_year}")
                        },
                        "heuristic_clues": {
                            "phase_2_status": "STUB_ACTIVE"
                        },
                        "rights_statement": {
                            "license_category": "HKU_Library_Open_Access",
                            "reuse_permitted": True,
                            "legal_disclaimer": {
                                "en": "Preserved by HKU Special Collections. Available for public research and digital humanities inquiry.",
                                "zh": "由香港大學特藏部典藏，依學術開放條款提供公眾歷史研究。"
                            }
                        },
                        "provenance": {
                            "source_manifest_url": f"https://digitalrepository.lib.hku.hk/catalog/{handle_id}",
                            "retrieved_at_utc": datetime.now(timezone.utc).isoformat()
                        }
                    }
                    ingested.append(record)

                time.sleep(0.5)

            except Exception as e:
                logger.error(f"[HKU] Batch query isolated failure: {e}")
                break

        logger.info(f"[HKU] Pipeline successfully acquired {len(ingested)} distinct records.")
        return ingested
