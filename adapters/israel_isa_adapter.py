"""
Israel State Archives (ISA) Production Adapter
符合 BaseAdapter 統一時間窗口，採集冷戰中東地緣衝突、摩薩德情報解密與總理辦公室公文。
"""
import re
import html
import time
import logging
import requests
from typing import List, Dict, Any, Optional, Set
from datetime import datetime, timezone
from adapters.base import BaseAdapter

logger = logging.getLogger("Veracity.Adapters.ISA")

class IsaIngestionError(Exception):
    pass

class IsraelIsaProductionAdapter(BaseAdapter):
    NAME = "IL_ISA"
    # 以色列國家檔案館開放目錄檢索 API
    API_URL = "https://www.archives.gov.il/api/v1/records/search"
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
            return "Untitled Israeli State Archival Document"
        stripped = re.sub(r"<[^>]+>", "", raw_text)
        unescaped = html.unescape(stripped)
        return " ".join(unescaped.split()).strip()

    def _execute_with_retry(self, params: Dict[str, Any]) -> Dict[str, Any]:
        for attempt in range(1, self.max_retries + 1):
            try:
                resp = self.session.get(self.API_URL, params=params, timeout=self.timeout)
                if resp.status_code == 429:
                    backoff = 2 ** attempt
                    logger.warning(f"[ISA] Rate limited (429). Retrying in {backoff}s...")
                    time.sleep(backoff)
                    continue
                if resp.status_code in (404, 502, 503):
                    logger.warning(f"[ISA] ISA catalog maintenance ({resp.status_code}).")
                    return {"results": []}
                resp.raise_for_status()
                return resp.json()
            except requests.RequestException as exc:
                if attempt == self.max_retries:
                    raise IsaIngestionError(f"ISA API unreachable: {exc}") from exc
                time.sleep(2 ** attempt)
        raise IsaIngestionError("ISA retry budget exhausted.")

    def fetch_records(self, max_pages: int = 2, page_size: int = 15) -> List[Dict[str, Any]]:
        ingested = []
        seen_ids: Set[str] = set()

        start_year, end_year = self.get_unified_date_window()
        # 以色列於 1948 年建國，基準從 1948 開始
        israel_start = max(1948, int(start_year))
        logger.info(f"[ISA] Applying Historical Window: {israel_start} to {end_year}")

        for page_idx in range(max_pages):
            params = {
                "q": "Foreign Affairs Intelligence Cold War Yom Kippur Six Day War",
                "startYear": str(israel_start),
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
                    doc_id = str(doc.get("id") or doc.get("fileNumber", "")).strip()
                    if not doc_id or doc_id in seen_ids:
                        continue
                    seen_ids.add(doc_id)

                    clean_title = self.clean_text(doc.get("titleEn") or doc.get("title"))
                    fonds_name = doc.get("ministry", "Prime Minister's Office / Ministry of Foreign Affairs")
                    call_no = doc.get("reference", f"ISA-FILE-{doc_id}")

                    record: Dict[str, Any] = {
                        "record_id": f"isa:{doc_id.replace('/', '_').replace(' ', '')}",
                        "verification_level": "metadata_only",
                        "fixity": {"hash_algorithm": "NONE", "hash_value": None, "file_size_bytes": None},
                        "archival_context": {
                            "repository": {
                                "en": "Israel State Archives (Jerusalem)",
                                "zh": "以色列國家檔案館 (耶路撒冷)"
                            },
                            "fonds": fonds_name,
                            "series": doc.get("series", "Declassified Foreign & Security Policy Series"),
                            "call_number": call_no,
                            "title": {
                                "en": clean_title,
                                "zh": None
                            },
                            "covering_dates": doc.get("dateDisplay", f"{israel_start}-{end_year}")
                        },
                        "heuristic_clues": {
                            "phase_2_status": "STUB_ACTIVE"
                        },
                        "rights_statement": {
                            "license_category": "Israel_State_Archives_Open_Access",
                            "reuse_permitted": True,
                            "legal_disclaimer": {
                                "en": "Declassified official records released by the Israel State Archives for historical verification.",
                                "zh": "依以色列檔案法規解密開放之政府歷史檔案，供法證與史學研究。"
                            }
                        },
                        "provenance": {
                            "source_manifest_url": f"https://www.archives.gov.il/en/archives/Archive/{doc_id}",
                            "retrieved_at_utc": datetime.now(timezone.utc).isoformat()
                        }
                    }
                    ingested.append(record)

                time.sleep(0.5)

            except Exception as e:
                logger.error(f"[ISA] Batch isolated failure: {e}")
                break

        logger.info(f"[ISA] Pipeline successfully acquired {len(ingested)} distinct records.")
        return ingested
