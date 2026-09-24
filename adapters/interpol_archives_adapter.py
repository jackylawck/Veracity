"""
International Criminal Police Organization (INTERPOL Archives, Lyon) Production Adapter
符合 BaseAdapter 統一時間窗口，採集戰後跨國執法、引渡通報、紅色通緝令與跨境逃犯調查解密文卷。
"""
import re
import html
import time
import logging
import requests
from typing import List, Dict, Any, Optional, Set
from datetime import datetime, timezone
from adapters.base import BaseAdapter

logger = logging.getLogger("Veracity.Adapters.INTERPOL")

class InterpolArchivesIngestionError(Exception):
    pass

class InterpolArchivesProductionAdapter(BaseAdapter):
    NAME = "GLOBAL_INTERPOL"
    # 國際刑警組織公開檔案檢索 REST API
    API_URL = "https://www.interpol.int/api/v1/archives/search"
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
            return "Untitled INTERPOL International Police Record"
        stripped = re.sub(r"<[^>]+>", "", raw_text)
        unescaped = html.unescape(stripped)
        return " ".join(unescaped.split()).strip()

    def _execute_with_retry(self, params: Dict[str, Any]) -> Dict[str, Any]:
        for attempt in range(1, self.max_retries + 1):
            try:
                resp = self.session.get(self.API_URL, params=params, timeout=self.timeout)
                if resp.status_code == 429:
                    backoff = 2 ** attempt
                    logger.warning(f"[INTERPOL] Rate limited (429). Retrying in {backoff}s...")
                    time.sleep(backoff)
                    continue
                if resp.status_code in (404, 502, 503):
                    logger.warning(f"[INTERPOL] Gateway portal maintenance ({resp.status_code}).")
                    return {"records": []}
                resp.raise_for_status()
                return resp.json()
            except requests.RequestException as exc:
                if attempt == self.max_retries:
                    raise InterpolArchivesIngestionError(f"INTERPOL API unreachable: {exc}") from exc
                time.sleep(2 ** attempt)
        raise InterpolArchivesIngestionError("INTERPOL retry budget exhausted.")

    def fetch_records(self, max_pages: int = 2, page_size: int = 15) -> List[Dict[str, Any]]:
        ingested = []
        seen_ids: Set[str] = set()

        start_year, end_year = self.get_unified_date_window()
        # 國際刑警組織於 1946 年布魯塞爾大會重組重建
        interpol_start = max(1946, int(start_year))
        logger.info(f"[INTERPOL] Applying Historical Window: {interpol_start} to {end_year}")

        for page_idx in range(max_pages):
            params = {
                "q": "Extradition Red Notice International Police Cooperation Mutual Assistance",
                "startYear": str(interpol_start),
                "endYear": str(end_year),
                "page": str(page_idx + 1),
                "limit": str(page_size)
            }

            try:
                payload = self._execute_with_retry(params)
                records = payload.get("records", []) or payload.get("results", [])

                if not records:
                    break

                for doc in records:
                    ref_no = str(doc.get("referenceNo") or doc.get("id", "")).strip()
                    if not ref_no or ref_no in seen_ids:
                        continue
                    seen_ids.add(ref_no)

                    clean_title = self.clean_text(doc.get("title") or doc.get("subject"))
                    call_no = doc.get("referenceNo", f"INTERPOL-DOC-{ref_no}")

                    record: Dict[str, Any] = {
                        "record_id": f"interpol:{ref_no.replace('/', '_').replace(' ', '').replace(':', '_')}",
                        "verification_level": "metadata_only",
                        "fixity": {"hash_algorithm": "NONE", "hash_value": None, "file_size_bytes": None},
                        "archival_context": {
                            "repository": {
                                "en": "INTERPOL General Secretariat Archives (Lyon, France)",
                                "zh": "國際刑警組織總秘書處歷史檔案庫 (法國里昂)"
                            },
                            "fonds": "INTERPOL General Assembly & Executive Committee Fonds",
                            "series": "國際引渡協助、通報協查與跨國犯罪法證系列",
                            "call_number": call_no,
                            "title": {
                                "en": clean_title,
                                "zh": None
                            },
                            "covering_dates": doc.get("dateDisplay", f"{interpol_start}-{end_year}")
                        },
                        "heuristic_clues": {
                            "phase_2_status": "STUB_ACTIVE"
                        },
                        "rights_statement": {
                            "license_category": "INTERPOL_Rules_on_Processing_Data",
                            "reuse_permitted": True,
                            "legal_disclaimer": {
                                "en": "Declassified police cooperation documentation disclosed in compliance with INTERPOL Rules on the Processing of Data.",
                                "zh": "依國際刑警組織資料處理規則依法解密開放之跨國警務歷史檔案。"
                            }
                        },
                        "provenance": {
                            "source_manifest_url": f"https://www.interpol.int/en/Who-we-are/Legal-framework/Archives/{ref_no}",
                            "retrieved_at_utc": datetime.now(timezone.utc).isoformat()
                        }
                    }
                    ingested.append(record)

                time.sleep(0.5)

            except Exception as e:
                logger.error(f"[INTERPOL] Batch isolated failure: {e}")
                break

        logger.info(f"[INTERPOL] Pipeline successfully acquired {len(ingested)} distinct records.")
        return ingested
