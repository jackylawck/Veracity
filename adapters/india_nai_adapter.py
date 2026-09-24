"""
National Archives of India (NAI / Abhilekh Patal) Production Adapter
符合 BaseAdapter 統一時間窗口，採集戰後印巴分治、萬隆會議與不結盟運動解密檔案。
"""
import re
import html
import time
import logging
import requests
from typing import List, Dict, Any, Optional, Set
from datetime import datetime, timezone
from adapters.base import BaseAdapter

logger = logging.getLogger("Veracity.Adapters.NAI")

class IndiaNaiIngestionError(Exception):
    pass

class IndiaNaiProductionAdapter(BaseAdapter):
    NAME = "IN_NAI"
    # 印度國家檔案館 Abhilekh Patal 官方公開檢索 API
    API_URL = "https://www.abhilekh-patal.in/api/v1/records/search"
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
            return "Untitled Record of the Government of India"
        stripped = re.sub(r"<[^>]+>", "", raw_text)
        unescaped = html.unescape(stripped)
        return " ".join(unescaped.split()).strip()

    def _execute_with_retry(self, params: Dict[str, Any]) -> Dict[str, Any]:
        for attempt in range(1, self.max_retries + 1):
            try:
                resp = self.session.get(self.API_URL, params=params, timeout=self.timeout)
                if resp.status_code == 429:
                    backoff = 2 ** attempt
                    logger.warning(f"[NAI] Rate limit (429). Retrying in {backoff}s...")
                    time.sleep(backoff)
                    continue
                if resp.status_code in (404, 502, 503):
                    logger.warning(f"[NAI] Abhilekh Patal gateway offline ({resp.status_code}).")
                    return {"results": []}
                resp.raise_for_status()
                return resp.json()
            except requests.RequestException as exc:
                if attempt == self.max_retries:
                    raise IndiaNaiIngestionError(f"NAI API unreachable: {exc}") from exc
                time.sleep(2 ** attempt)
        raise IndiaNaiIngestionError("NAI retry budget exhausted.")

    def fetch_records(self, max_pages: int = 2, page_size: int = 15) -> List[Dict[str, Any]]:
        ingested = []
        seen_ids: Set[str] = set()

        start_year, end_year = self.get_unified_date_window()
        # 印度於 1947 年獨立建國，以 1947 為有效起始點
        india_start = max(1947, int(start_year))
        logger.info(f"[NAI] Applying Historical Window: {india_start} to {end_year}")

        for page_idx in range(max_pages):
            params = {
                "query": "External Affairs Non-Aligned Movement Treaty Border",
                "startYear": str(india_start),
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
                    doc_id = str(doc.get("recordId") or doc.get("fileNo", "")).strip()
                    if not doc_id or doc_id in seen_ids:
                        continue
                    seen_ids.add(doc_id)

                    clean_title = self.clean_text(doc.get("title") or doc.get("subject"))
                    dept = doc.get("department", "Ministry of External Affairs (MEA)")
                    call_no = doc.get("fileNo", f"NAI-MEA-{doc_id}")

                    record: Dict[str, Any] = {
                        "record_id": f"innai:{doc_id.replace('/', '_').replace(' ', '')}",
                        "verification_level": "metadata_only",
                        "fixity": {"hash_algorithm": "NONE", "hash_value": None, "file_size_bytes": None},
                        "archival_context": {
                            "repository": {
                                "en": "National Archives of India (New Delhi)",
                                "zh": "印度國家檔案館 (新德里)"
                            },
                            "fonds": dept,
                            "series": doc.get("branch", "Post-Independence Foreign Affairs & Border Records"),
                            "call_number": call_no,
                            "title": {
                                "en": f"[{dept}] {clean_title}",
                                "zh": None
                            },
                            "covering_dates": doc.get("year", f"{india_start}-{end_year}")
                        },
                        "heuristic_clues": {
                            "phase_2_status": "STUB_ACTIVE"
                        },
                        "rights_statement": {
                            "license_category": "India_Public_Records_Act_1993",
                            "reuse_permitted": True,
                            "legal_disclaimer": {
                                "en": "Declassified government records released under the Public Records Act, 1993.",
                                "zh": "依印度《1993年公共記錄法》（Public Records Act, 1993）法定解密之政府檔案。"
                            }
                        },
                        "provenance": {
                            "source_manifest_url": f"https://www.abhilekh-patal.in/jspui/handle/123456789/{doc_id}",
                            "retrieved_at_utc": datetime.now(timezone.utc).isoformat()
                        }
                    }
                    ingested.append(record)

                time.sleep(0.5)

            except Exception as e:
                logger.error(f"[NAI] Batch isolated failure: {e}")
                break

        logger.info(f"[NAI] Pipeline successfully acquired {len(ingested)} distinct records.")
        return ingested
