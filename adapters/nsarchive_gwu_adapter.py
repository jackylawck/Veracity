"""
The National Security Archive (George Washington University) Production Adapter
符合 BaseAdapter 統一時間窗口，採集透過 FOIA 強制解密之美軍、情報機構 (CIA/NSA) 與白宮冷戰原始密檔。
"""
import re
import html
import time
import logging
import requests
from typing import List, Dict, Any, Optional, Set
from datetime import datetime, timezone
from adapters.base import BaseAdapter

logger = logging.getLogger("Veracity.Adapters.NSArchive")

class NsArchiveIngestionError(Exception):
    pass

class NsArchiveProductionAdapter(BaseAdapter):
    NAME = "GLOBAL_NSARCHIVE"
    # GWU National Security Archive 公開解密公文索引 REST 端點
    API_URL = "https://nsarchive.gwu.edu/api/v1/records/search"
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
            return "Untitled FOIA Declassified Intelligence Document"
        stripped = re.sub(r"<[^>]+>", "", raw_text)
        unescaped = html.unescape(stripped)
        return " ".join(unescaped.split()).strip()

    def _execute_with_retry(self, params: Dict[str, Any]) -> Dict[str, Any]:
        for attempt in range(1, self.max_retries + 1):
            try:
                resp = self.session.get(self.API_URL, params=params, timeout=self.timeout)
                if resp.status_code == 429:
                    backoff = 2 ** attempt
                    logger.warning(f"[NSArchive] Rate limited (429). Retrying in {backoff}s...")
                    time.sleep(backoff)
                    continue
                if resp.status_code in (404, 502, 503):
                    logger.warning(f"[NSArchive] Archive gateway offline ({resp.status_code}).")
                    return {"results": []}
                resp.raise_for_status()
                return resp.json()
            except requests.RequestException as exc:
                if attempt == self.max_retries:
                    raise NsArchiveIngestionError(f"NSArchive API unreachable: {exc}") from exc
                time.sleep(2 ** attempt)
        raise NsArchiveIngestionError("NSArchive retry budget exhausted.")

    def fetch_records(self, max_pages: int = 2, page_size: int = 15) -> List[Dict[str, Any]]:
        ingested = []
        seen_ids: Set[str] = set()

        start_year, end_year = self.get_unified_date_window()
        logger.info(f"[NSArchive] Applying Unified Historical Window: {start_year} to {end_year}")

        for page_idx in range(max_pages):
            params = {
                "q": "CIA Intelligence Nuclear Crisis Diplomatic FOIA declassified",
                "startYear": str(start_year),
                "endYear": str(end_year),
                "page": str(page_idx + 1),
                "pageSize": str(page_size)
            }

            try:
                payload = self._execute_with_retry(params)
                records = payload.get("results", []) or payload.get("records", [])

                if not records:
                    break

                for doc in records:
                    doc_id = str(doc.get("id") or doc.get("briefingBookNo", "")).strip()
                    if not doc_id or doc_id in seen_ids:
                        continue
                    seen_ids.add(doc_id)

                    clean_title = self.clean_text(doc.get("title"))
                    source_agency = doc.get("sourceAgency", "CIA / NSA / National Security Council")
                    call_no = doc.get("callNumber", f"NSA-FOIA-{doc_id}")

                    record: Dict[str, Any] = {
                        "record_id": f"nsafoia:{doc_id.replace('/', '_').replace(' ', '')}",
                        "verification_level": "metadata_only",
                        "fixity": {"hash_algorithm": "NONE", "hash_value": None, "file_size_bytes": None},
                        "archival_context": {
                            "repository": {
                                "en": "The National Security Archive, George Washington University (Washington, D.C.)",
                                "zh": "美國國家安全檔案館 / 喬治華盛頓大學 (華盛頓特區)"
                            },
                            "fonds": f"FOIA Declassified Collections ({source_agency})",
                            "series": doc.get("series", "Cold War & Intelligence Policy Briefing Books"),
                            "call_number": call_no,
                            "title": {
                                "en": clean_title,
                                "zh": None
                            },
                            "covering_dates": doc.get("documentDate", f"{start_year}-{end_year}")
                        },
                        "heuristic_clues": {
                            "phase_2_status": "STUB_ACTIVE"
                        },
                        "rights_statement": {
                            "license_category": "US_FOIA_Public_Domain",
                            "reuse_permitted": True,
                            "legal_disclaimer": {
                                "en": "Declassified official government records obtained under Freedom of Information Act (5 U.S.C. 552).",
                                "zh": "依美國《資訊自由法》（FOIA, 5 U.S.C. 552）強制解密之美國聯邦政府情報與外交檔案。"
                            }
                        },
                        "provenance": {
                            "source_manifest_url": f"https://nsarchive.gwu.edu/briefing-book/{doc_id}",
                            "retrieved_at_utc": datetime.now(timezone.utc).isoformat()
                        }
                    }
                    ingested.append(record)

                time.sleep(0.5)

            except Exception as e:
                logger.error(f"[NSArchive] Batch isolated failure: {e}")
                break

        logger.info(f"[NSArchive] Pipeline successfully acquired {len(ingested)} distinct records.")
        return ingested
