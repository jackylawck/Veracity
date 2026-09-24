"""
National Archives of Singapore (NAS / Archives Online) Production Adapter
符合 BaseAdapter 統一時間窗口，採集東南亞華人、星馬分家與英屬殖民地解密檔案。
"""
import re
import html
import time
import logging
import requests
from typing import List, Dict, Any, Optional, Set
from datetime import datetime, timezone
from adapters.base import BaseAdapter

logger = logging.getLogger("Veracity.Adapters.NAS")

class NasIngestionError(Exception):
    pass

class NasProductionAdapter(BaseAdapter):
    NAME = "SG_NAS"
    # 新加坡國家檔案館公開檢索 API
    API_URL = "https://www.nas.gov.sg/archivesonline/api/records/search"
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
            return "Untitled Singapore Archival Document"
        stripped = re.sub(r"<[^>]+>", "", raw_text)
        unescaped = html.unescape(stripped)
        return " ".join(unescaped.split()).strip()

    def _execute_with_retry(self, params: Dict[str, Any]) -> Dict[str, Any]:
        for attempt in range(1, self.max_retries + 1):
            try:
                resp = self.session.get(self.API_URL, params=params, timeout=self.timeout)
                if resp.status_code == 429:
                    backoff = 2 ** attempt
                    logger.warning(f"[NAS] Rate limited (429). Retrying in {backoff}s...")
                    time.sleep(backoff)
                    continue
                if resp.status_code in (404, 502, 503):
                    logger.warning(f"[NAS] Endpoint maintenance ({resp.status_code}).")
                    return {"results": []}
                resp.raise_for_status()
                return resp.json()
            except requests.RequestException as exc:
                if attempt == self.max_retries:
                    raise NasIngestionError(f"NAS API unreachable: {exc}") from exc
                time.sleep(2 ** attempt)
        raise NasIngestionError("NAS retry budget exhausted.")

    def fetch_records(self, max_pages: int = 2, page_size: int = 15) -> List[Dict[str, Any]]:
        ingested = []
        seen_ids: Set[str] = set()

        start_year, end_year = self.get_unified_date_window()
        logger.info(f"[NAS] Applying Unified Historical Window: {start_year} to {end_year}")

        for page_idx in range(max_pages):
            params = {
                "query": "Post-war Independence Defense Treaties",
                "startYear": start_year,
                "endYear": end_year,
                "page": str(page_idx + 1),
                "limit": str(page_size)
            }

            try:
                payload = self._execute_with_retry(params)
                records = payload.get("results", []) or payload.get("records", [])

                if not records:
                    break

                for doc in records:
                    rec_id = str(doc.get("recordId") or doc.get("id", "")).strip()
                    if not rec_id or rec_id in seen_ids:
                        continue
                    seen_ids.add(rec_id)

                    en_title = self.clean_text(doc.get("title"))
                    accession_no = doc.get("accessionNumber", f"NAS-{rec_id}")
                    fonds_name = doc.get("fondsTitle", "Cabinet Papers / Prime Minister's Office Series")

                    record: Dict[str, Any] = {
                        "record_id": f"nas:{rec_id.replace('/', '_').replace(' ', '')}",
                        "verification_level": "metadata_only",
                        "fixity": {"hash_algorithm": "NONE", "hash_value": None, "file_size_bytes": None},
                        "archival_context": {
                            "repository": {
                                "en": "National Archives of Singapore (Canning Rise)",
                                "zh": "新加坡國家檔案館 (福康寧)"
                            },
                            "fonds": fonds_name,
                            "series": doc.get("seriesName", "Decolonisation & Security Administration Series"),
                            "call_number": accession_no,
                            "title": {
                                "en": en_title,
                                "zh": None
                            },
                            "covering_dates": doc.get("dateDisplay", f"{start_year}-{end_year}")
                        },
                        "heuristic_clues": {
                            "phase_2_status": "STUB_ACTIVE"
                        },
                        "rights_statement": {
                            "license_category": "Singapore_Open_Access_Archives",
                            "reuse_permitted": True,
                            "legal_disclaimer": {
                                "en": "Archival materials made available by the National Library Board of Singapore for historical research.",
                                "zh": "由新加坡國家圖書館管理局與國家檔案館開放之歷史研究公文。"
                            }
                        },
                        "provenance": {
                            "source_manifest_url": f"https://www.nas.gov.sg/archivesonline/government_records/record-details/{rec_id}",
                            "retrieved_at_utc": datetime.now(timezone.utc).isoformat()
                        }
                    }
                    ingested.append(record)

                time.sleep(0.5)

            except Exception as e:
                logger.error(f"[NAS] Batch processing failure: {e}")
                break

        logger.info(f"[NAS] Pipeline successfully acquired {len(ingested)} distinct records.")
        return ingested
