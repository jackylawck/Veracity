"""
NATO Archives Online (NATO Declassified) Production Adapter
符合 BaseAdapter 統一時間窗口，採集北大西洋公約組織理事會 (NAC) 及軍事委員會冷戰解密原件。
"""
import re
import html
import time
import logging
import requests
from typing import List, Dict, Any, Optional, Set
from datetime import datetime, timezone
from adapters.base import BaseAdapter

logger = logging.getLogger("Veracity.Adapters.NATO")

class NatoArchivesIngestionError(Exception):
    pass

class NatoArchivesProductionAdapter(BaseAdapter):
    NAME = "GLOBAL_NATO"
    # NATO Archives Online 公開 REST 檢索端點
    API_URL = "https://archives.nato.int/api/records/search"
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
            return "Untitled NATO Declassified Document"
        stripped = re.sub(r"<[^>]+>", "", raw_text)
        unescaped = html.unescape(stripped)
        return " ".join(unescaped.split()).strip()

    def _execute_with_retry(self, params: Dict[str, Any]) -> Dict[str, Any]:
        for attempt in range(1, self.max_retries + 1):
            try:
                resp = self.session.get(self.API_URL, params=params, timeout=self.timeout)
                if resp.status_code == 429:
                    backoff = 2 ** attempt
                    logger.warning(f"[NATO] Rate limited (429). Retrying in {backoff}s...")
                    time.sleep(backoff)
                    continue
                if resp.status_code in (404, 502, 503):
                    logger.warning(f"[NATO] Archive gateway offline ({resp.status_code}).")
                    return {"results": []}
                resp.raise_for_status()
                return resp.json()
            except requests.RequestException as exc:
                if attempt == self.max_retries:
                    raise NatoArchivesIngestionError(f"NATO Archives API unreachable: {exc}") from exc
                time.sleep(2 ** attempt)
        raise NatoArchivesIngestionError("NATO retry budget exhausted.")

    def fetch_records(self, max_pages: int = 2, page_size: int = 15) -> List[Dict[str, Any]]:
        ingested = []
        seen_ids: Set[str] = set()

        start_year, end_year = self.get_unified_date_window()
        # 北約於 1949 年成立，起始年份設為 1949
        nato_start = max(1949, int(start_year))
        logger.info(f"[NATO] Applying Historical Window: {nato_start} to {end_year}")

        for page_idx in range(max_pages):
            params = {
                "query": "North Atlantic Council Cold War Strategy Nuclear",
                "startYear": str(nato_start),
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
                    doc_id = str(doc.get("referenceCode") or doc.get("id", "")).strip()
                    if not doc_id or doc_id in seen_ids:
                        continue
                    seen_ids.add(doc_id)

                    clean_title = self.clean_text(doc.get("title"))
                    fonds_name = doc.get("fonds", "North Atlantic Council (NAC) Records")
                    call_no = doc.get("referenceCode", f"NATO-DOC-{doc_id}")

                    record: Dict[str, Any] = {
                        "record_id": f"nato:{doc_id.replace('/', '_').replace(' ', '')}",
                        "verification_level": "metadata_only",
                        "fixity": {"hash_algorithm": "NONE", "hash_value": None, "file_size_bytes": None},
                        "archival_context": {
                            "repository": {
                                "en": "NATO Archives / Archives de l'OTAN (Brussels)",
                                "zh": "北大西洋公約組織檔案館 (布魯塞爾)"
                            },
                            "fonds": fonds_name,
                            "series": doc.get("series", "Cold War Military & Strategic Declassified Series"),
                            "call_number": call_no,
                            "title": {
                                "en": clean_title,
                                "zh": None
                            },
                            "covering_dates": doc.get("dateDisplay", f"{nato_start}-{end_year}")
                        },
                        "heuristic_clues": {
                            "phase_2_status": "STUB_ACTIVE"
                        },
                        "rights_statement": {
                            "license_category": "NATO_Public_Disclosure_Policy",
                            "reuse_permitted": True,
                            "legal_disclaimer": {
                                "en": "Declassified and made publicly available under the NATO Public Disclosure Policy.",
                                "zh": "依《北約公共解密揭露政策》（NATO Public Disclosure Policy）解密公開之公文檔案。"
                            }
                        },
                        "provenance": {
                            "source_manifest_url": f"https://archives.nato.int/{doc_id}",
                            "retrieved_at_utc": datetime.now(timezone.utc).isoformat()
                        }
                    }
                    ingested.append(record)

                time.sleep(0.5)

            except Exception as e:
                logger.error(f"[NATO] Batch isolated failure: {e}")
                break

        logger.info(f"[NATO] Pipeline successfully acquired {len(ingested)} distinct records.")
        return ingested
